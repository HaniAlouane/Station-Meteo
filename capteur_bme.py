# =================================================================
# 🌡️ PILOTE DU CAPTEUR BME280 (TEMPÉRATURE, PRESSION, HUMIDITÉ)
# =================================================================
from machine import Pin, I2C
import time
import bme280

class CapteurBME280:
    """
    Cette classe gère la communication avec le capteur Bosch BME280 via le bus I2C.
    Elle inclut un gestionnaire de temps pour ne pas lire le capteur trop souvent.
    """
    
    def __init__(self, i2c_objet, periode_ms=2000):
        # 1. RÉCUPÉRATION DU BUS I2C : On utilise la connexion déjà créée dans le main.py
        self.i2c = i2c_objet
        
        # 2. INITIALISATION DU CAPTEUR :
        # L'adresse 0x76 est l'adresse matérielle standard pour les modules BME280 violets/bleus.
        # Cette ligne établit la liaison série entre la Pico et la puce Bosch.
        self.capteur = bme280.BME280(i2c=self.i2c, address=0x76)

        # 3. GESTION DU TIMING :
        # periode_ms définit la fréquence de lecture (ici toutes les 2 secondes par défaut)
        self.periode_ms = periode_ms
        self.dernier_temps = time.ticks_ms() # Enregistre le moment du démarrage

        # 4. MÉMOIRE DES VALEURS : On initialise les variables à "None" (vide)
        self.temperature = None
        self.pression = None
        self.humidite = None

    def lire(self):
        """
        Demande au capteur ses mesures brutes et les stocke dans l'objet.
        Retourne un tuple contenant les 3 valeurs.
        """
        # On récupère les valeurs du capteur (souvent renvoyées sous forme de texte/tuple)
        valeurs = self.capteur.values
        
        # valeurs[0] = Température, [1] = Pression, [2] = Humidité
        self.temperature = valeurs[0]
        self.pression = valeurs[1]
        self.humidite = valeurs[2]
        
        return self.temperature, self.pression, self.humidite

    def actualiser(self):
        """
        Vérifie si le temps défini (periode_ms) est écoulé.
        - Si oui : elle lit le capteur et renvoie True.
        - Si non : elle ne fait rien et renvoie False (pour ne pas bloquer le processeur).
        """
        maintenant = time.ticks_ms()
        
        # Calcul de la différence entre maintenant et la dernière lecture
        if time.ticks_diff(maintenant, self.dernier_temps) >= self.periode_ms:
            self.dernier_temps = maintenant # Mise à jour du chrono pour le prochain tour
            
            # Appel de la fonction de lecture physique
            valeurs = self.lire()
            return valeurs, True # Indique au programme principal qu'une nouvelle donnée est prête
            
        # Si le temps n'est pas écoulé, on renvoie les anciennes valeurs
        return (self.temperature, self.pression, self.humidite), False