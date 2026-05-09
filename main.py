# =================================================================
# 📂 IMPORTATION DES BIBLIOTHÈQUES ET PILOTES
# =================================================================
import time
import json
import network
import sys
import uselect
from umqtt.simple import MQTTClient
from machine import Pin, I2C

# Importation des classes spécifiques à chaque capteur (fichiers .py sur la Pico)
from anemometre import CapteurVent
from capteur_bme import CapteurBME280
from capteur_lux import CapteurLumiere
from capteur_temp_analog import CapteurTempAnalog

# =================================================================
# 🛠️ CONFIGURATION DE LA SURVEILLANCE USB (HEARTBEAT)
# =================================================================
# On crée un objet "poll" pour surveiller si Node-RED nous envoie un message
spoll = uselect.poll()
spoll.register(sys.stdin, uselect.POLLIN)

def node_red_a_repondu():
    """Vérifie si Node-RED a envoyé un caractère sur le port USB"""
    # On vérifie s'il y a des données (timeout 0 = non bloquant)
    return spoll.poll(0)

# =================================================================
# ⚙️ CONFIGURATION RÉSEAU ET IDENTIFIANTS CLOUD (WIFI / ADAFRUIT)
# =================================================================
# Identifiants WIFI
WIFI_SSID = "NOM_DU_RESEAU_WIFI"
WIFI_PASSWORD = "MOT_DE_PASSE_WIFI"
# Identifiants Adafruit IO
ADAFRUIT_USER = "IDENTIFIANT"
ADAFRUIT_KEY = "CLE_AIO"

# =================================================================
# 🔌 INITIALISATION MATÉRIELLE (CAPTEURS ET BROCHES)
# =================================================================
# Configuration du bus I2C pour le BME280 et le capteur de lumière
bus_i2c = I2C(0, scl=Pin(5), sda=Pin(4), freq=100000)

# Création des objets capteurs avec leurs broches respectives
vent = CapteurVent(pin_adc=26)            # Anémomètre sur GP26
temp_analog = CapteurTempAnalog(pin_adc=27)        # LM135 sur GP27
climat = CapteurBME280(bus_i2c)           # BME280 sur I2C
lumiere = CapteurLumiere(bus_i2c)         # Capteur LUX sur I2C

# Activation de l'interface Wi-Fi
wlan = network.WLAN(network.STA_IF)
wlan.active(True)

# Variables de contrôle de la boucle
client = None
dernier_envoi = time.ticks_ms()
node_red_present = False

# =================================================================
# 🔄 BOUCLE PRINCIPALE (SURVEILLANCE ET TRANSMISSION)
# =================================================================
while True:
    # PRIORITÉ : Écouter l'anémomètre en continu pour ne rater aucun tour
    vent.ecouter()
    
    # 1. DÉTECTION DE LA PRÉSENCE DE NODE-RED
    # Si des données arrivent par USB, on sait que Node-RED écoute et répond
    if node_red_a_repondu():
        sys.stdin.read(1)           # On vide le tampon pour la prochaine test
        node_red_present = True           # On active le drapeau de présence
    
    maintenant = time.ticks_ms()
    
    # 2. DÉCLENCHEMENT DU CYCLE DE TRANSMISSION (Toutes les 12 secondes)
    if time.ticks_diff(maintenant, dernier_envoi) >= 12000:
        
        # --- PHASE D'ACQUISITION DES DONNÉES ---
        v_inst, _ = vent.lire_vitesse()          # Vitesse du vent
        t_analog = temp_analog.lire()            # Température (LM135)
        lux = lumiere.lire()                     # Luminosité (LUX)
        _, press_str, hum_str = climat.lire()    # Pression et Humidité (BME280)
        
        # --- NETTOYAGE ET FORMATAGE DES DONNÉES ---
        # On transforme les textes (ex: "33%") en nombres réels (33.0)
        payload = {
            "vitesse_vent": round(v_inst, 2),
            "luminosite": round(lux, 1),
            "temperature": round(t_analog, 2),
            "humidite": float(str(hum_str).replace('%', '')),
            "pression": float(str(press_str).replace('hPa', ''))
        }

        # 1. TRANSMISSION FILAIRE USB (Toujours le JSON pour Node-RED)
        
        # On envoie toujours le JSON. Node-RED le traitera s'il est allumé.
        print(json.dumps(payload))
        
        # --- LOGIQUE DE SECOURS (WIFI / CLOUD) ---
        # Si Node-RED n'a pas répondu (pas de PC), on bascule sur le Wi-Fi (il ne s'exécute QUE si Node-RED n'a pas répondu au Heartbeat)
        if not node_red_present:
            print("-----------------------------------------")
            print("⚠️ Node-RED est indisponible.")
            print("📡 Passage en mode autonome (Wi-Fi)...")
            
            # Tentative de connexion Wi-Fi si non connecté
            if not wlan.isconnected():
                print(f"🔗 Recherche du réseau : {WIFI_SSID}...")
                wlan.connect(WIFI_SSID, WIFI_PASSWORD)
                for _ in range(5):      # Attente de 5 secondes maximum
                    if wlan.isconnected(): break
                    time.sleep(1)
                
                if wlan.isconnected():
                    print("✅ Wi-Fi connecté !")
                    # FORCE LE RESET : Puisque le Wi-Fi vient de revenir, 
                    # On force la Pico à recréer une connexion MQTT propre (un nouveau client MQTT).
                    client = None
                else:
                    print("❌ Échec de connexion Wi-Fi.")
            
            # --- Envoi vers Adafruit ---
            if wlan.isconnected():
                try:
                    # Initialisation ou reconnexion du client MQTT
                    # Si le client est None (premier envoi ou reconnexion), on connecte
                    if client is None:
                        print("🔌 Ouverture du tunnel MQTT vers Adafruit...")
                        client = MQTTClient("pico", "io.adafruit.com", user=ADAFRUIT_USER, password=ADAFRUIT_KEY, port=1883)
                        client.connect()
                    
                    # Publication de chaque donnée vers son flux (feed) respectif
                    # On boucle sur le dictionnaire pour envoyer chaque donnée
                    for k, v in payload.items():
                        # replace('_','-') car Adafruit utilise des tirets au lieu des underscores
                        feed_path = f"{ADAFRUIT_USER}/feeds/{k.replace('_','-')}"
                        # Utilisation du QoS 1 pour garantir la réception par le serveur
                        # La Pico va maintenant attendre la confirmation d'Adafruit
                        client.publish(feed_path, str(v), qos=1)
                    
                    print("🚀 Données envoyées directement et confirmées par Adafruit IO.")
                except Exception as e:
                    client = None # Reset du client pour la prochaine tentative en cas d'erreur
                    print(f"❌ Erreur de transmission : {e}")
            print("-----------------------------------------")

        # 3. RÉINITIALISATION POUR LE PROCHAIN CYCLE
        # On remet le test Node-RED à False pour recommencer la surveillance ; Si Node-RED répond entre temps, ça repassera à True.
        node_red_present = False
        dernier_envoi = maintenant