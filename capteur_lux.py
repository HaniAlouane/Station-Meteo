from machine import Pin, I2C
import time
import veml7700

class CapteurLumiere:
    """
    Cette classe gère le capteur VEML7700 via le bus I2C.
    Elle permet d'obtenir une mesure précise de la luminosité en Lux.
    """
    
    def __init__(self, i2c_objet, periode_ms=2000):
        self.i2c = i2c_objet
        
        self.capteur = veml7700.VEML7700(i2c=self.i2c)

        self.periode_ms = periode_ms
        self.dernier_temps = time.ticks_ms()
        
        self.lux = 0.0

    def lire(self):
        """
        Interroge le capteur pour obtenir la luminosité actuelle.
        Retourne la valeur en Lux (unité internationale).
        """
        
        self.lux = self.capteur.read_lux()
        return self.lux

    def actualiser(self):
        """
        Gestionnaire de temps non-bloquant.
        Permet à la Pico de continuer d'autres tâches (comme surveiller le vent)
        pendant que le délai de 2 secondes s'écoule.
        """
        maintenant = time.ticks_ms()
        
        if time.ticks_diff(maintenant, self.dernier_temps) >= self.periode_ms:
            self.dernier_temps = maintenant
            
            valeur = self.lire()
            
            # Renvoie la valeur et "True" pour signaler qu'une mise à jour a eu lieu
            return valeur, True
            
        # Sinon, renvoie la dernière valeur connue et "False"
        return self.lux, False
