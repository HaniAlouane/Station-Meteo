# =================================================================
# 💡 PILOTE DU CAPTEUR DE LUMIÈRE NUMÉRIQUE (VEML7700)
# =================================================================
from machine import Pin, I2C
import time
import veml7700 # Importation de la bibliothèque spécifique au capteur

class CapteurLumiere:
    """
    Cette classe gère le capteur VEML7700 via le bus I2C.
    Elle permet d'obtenir une mesure précise de la luminosité en Lux.
    """
    
    def __init__(self, i2c_objet, periode_ms=2000):
        # 1. RÉCUPÉRATION DU BUS I2C :
        # On utilise l'objet I2C déjà initialisé dans le fichier principal.
        self.i2c = i2c_objet
        
        # 2. INITIALISATION DU CAPTEUR :
        # La bibliothèque veml7700 établit la communication avec l'adresse 
        # matérielle du capteur (généralement 0x10).
        self.capteur = veml7700.VEML7700(i2c=self.i2c)

        # 3. GESTION DU TIMING :
        # On définit la fréquence de lecture (toutes les 2 secondes par défaut).
        self.periode_ms = periode_ms
        self.dernier_temps = time.ticks_ms()
        
        # 4. STOCKAGE : Variable pour conserver la dernière valeur de Lux lue.
        self.lux = 0.0

    def lire(self):
        """
        Interroge le capteur pour obtenir la luminosité actuelle.
        Retourne la valeur en Lux (unité internationale).
        """
        # On utilise la méthode de la bibliothèque pour lire la valeur convertie.
        # Le capteur gère lui-même les gains et le temps d'intégration en interne.
        self.lux = self.capteur.read_lux()
        return self.lux

    def actualiser(self):
        """
        Gestionnaire de temps non-bloquant.
        Permet à la Pico de continuer d'autres tâches (comme surveiller le vent)
        pendant que le délai de 2 secondes s'écoule.
        """
        maintenant = time.ticks_ms()
        
        # Si le temps écoulé dépasse la période définie (2000ms)
        if time.ticks_diff(maintenant, self.dernier_temps) >= self.periode_ms:
            self.dernier_temps = maintenant # Mise à jour du chronomètre interne
            
            # Déclenchement de la lecture physique
            valeur = self.lire()
            
            # Renvoie la valeur et "True" pour signaler qu'une mise à jour a eu lieu
            return valeur, True
            
        # Sinon, renvoie la dernière valeur connue et "False"
        return self.lux, False