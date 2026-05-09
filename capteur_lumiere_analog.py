# =================================================================
# ☀️ PILOTE DU CAPTEUR DE LUMIÈRE ANALOGIQUE (LDR / PHOTORÉSISTANCE)
# =================================================================
from machine import ADC
import time

class CapteurLumiereAnalog:
    """
    Cette classe gère la lecture d'un capteur de luminosité analogique.
    Elle transforme une tension électrique en une valeur exploitable (pourcentage).
    """
    
    def __init__(self, pin_adc=28, periode_ms=2000):
        # 1. INITIALISATION DE L'ADC :
        # On configure la broche GP28 pour lire des tensions analogiques.
        # Sur la Pico, l'ADC a une résolution de 16 bits (0 à 65535).
        self.adc = ADC(pin_adc)
        
        # 2. GESTION DU TIMING :
        # On définit l'intervalle entre chaque mesure (2 secondes par défaut).
        self.periode_ms = periode_ms
        self.dernier_temps = time.ticks_ms()
        
        # 3. STOCKAGE : Variable pour conserver la dernière mesure calculée.
        self.pourcentage_lumiere = 0.0

    def lire(self):
        """
        Effectue la lecture physique et convertit le signal électrique en donnée météo.
        """
        # 1. LECTURE BRUTE (0-65535) :
        # Le capteur renvoie une tension (0V à 3.3V) convertie en un nombre entier.
        valeur_brute = self.adc.read_u16()
        
        # 2. CONVERSION EN POURCENTAGE :
        # On applique un produit en croix pour transformer la valeur 16 bits en %.
        # Formule : (Valeur lue / Valeur Max) * 100
        # On considère que 65535 (3.3V) correspond à 100% de luminosité.
        self.pourcentage_lumiere = (valeur_brute / 65535) * 100
        
        return self.pourcentage_lumiere

    def actualiser(self):
        """
        Gestionnaire de temps non-bloquant.
        Permet de ne déclencher la lecture que si la période est écoulée.
        """
        maintenant = time.ticks_ms()
        
        # Si la différence de temps est supérieure ou égale à 2000ms
        if time.ticks_diff(maintenant, self.dernier_temps) >= self.periode_ms:
            self.dernier_temps = maintenant # On remet le chrono à zéro
            
            # On lance la lecture et on renvoie True pour signaler une mise à jour
            return self.lire(), True
            
        # Sinon, on renvoie l'ancienne valeur et False (pas de mise à jour)
        return self.pourcentage_lumiere, False