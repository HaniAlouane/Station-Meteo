# =================================================================
# 🌡️ PILOTE DU CAPTEUR DE TEMPÉRATURE ANALOGIQUE (LM335 / LM135)
# =================================================================
from machine import ADC
import time

class CapteurTempAnalog:
    """
    Cette classe gère un capteur de température de type LM335.
    Le capteur fournit une tension proportionnelle à la température en Kelvin.
    """
    
    def __init__(self, pin_adc=27, periode_ms=2000, offset_calib=-3.3):
        # 1. INITIALISATION DE L'ADC :
        # On utilise la broche GP27. La Pico convertit la tension (0-3.3V) en 0-65535.
        self.adc = ADC(pin_adc)
        
        # 2. GESTION DU TIMING :
        # Fréquence de rafraîchissement (par défaut toutes les 2 secondes).
        self.periode_ms = periode_ms
        self.dernier_temps = time.ticks_ms()
        
        # 3. VARIABLES DE DONNÉES :
        self.temp_c = 0.0
        self.offset = offset_calib # Correction logicielle pour la précision

    def lire(self):
        """
        Effectue une lecture précise en faisant la moyenne de plusieurs échantillons
        puis convertit le signal électrique en degrés Celsius.
        """
        # A. LISSAGE DU SIGNAL (OVERSAMPLING) :
        # On prend 10 mesures rapides pour éliminer les bruits électriques parasites.
        somme_brute = 0
        for _ in range(10):
            somme_brute += self.adc.read_u16()
            time.sleep_ms(2) # Très courte pause entre chaque échantillon
        
        valeur_moyenne = somme_brute / 10
        
        # B. CONVERSION TENSION (VOLTS) :
        # Formule : (Valeur lue * Tension de référence) / Résolution Max
        tension = (valeur_moyenne * 3.3) / 65535
        
        # C. PHYSIQUE DU CAPTEUR (KELVIN) :
        # Le LM335 produit 10mV par degré Kelvin (0.01V/K). 
        # Donc Tension * 100 = Température en Kelvin.
        temp_kelvin = tension * 100
        
        # D. CONVERSION CELSIUS ET CALIBRAGE :
        # Celsius = Kelvin - 273.15. On ajoute l'offset pour corriger l'erreur du capteur.
        self.temp_c = (temp_kelvin - 273.15) + self.offset
        
        return round(self.temp_c, 2)

    def actualiser(self):
        """
        Gestionnaire de temps non-bloquant. 
        Décide si c'est le moment d'effectuer une nouvelle lecture.
        """
        maintenant = time.ticks_ms()
        
        # Vérification de l'intervalle de temps (2000ms)
        if time.ticks_diff(maintenant, self.dernier_temps) >= self.periode_ms:
            self.dernier_temps = maintenant # On réinitialise le chrono
            
            # On retourne la nouvelle mesure et "True" pour confirmer la mise à jour
            return self.lire(), True
            
        # Sinon, on retourne l'ancienne mesure et "False"
        return self.temp_c, False