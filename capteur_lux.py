"""
capteur_lux.py — VEML7700 ambient light sensor wrapper
=======================================================
Thin convenience layer around the veml7700.py driver.
Returns calibrated lux values directly from the sensor's built-in
gain and integration-time compensation tables.

The VEML7700 communicates over I2C at address 0x10 and supports a
dynamic range of approximately 0 – 120 000 lux, making it suitable
for both indoor and full-sunlight outdoor measurements.
"""
from machine import Pin, I2C
import time
import veml7700 # Importation de la bibliothèque spécifique au capteur

class CapteurLumiere:


    """Non-blocking wrapper for the Vishay VEML7700 lux sensor."""
    def __init__(self, i2c_objet, periode_ms=2000):

        self.i2c = i2c_objet
        """
        Args:
            i2c_objet:  An already-initialised machine.I2C instance
                        shared with other devices on the same bus.
            periode_ms: Minimum time between two consecutive readings
                        when using actualiser() (default 2000 ms).
        """
        self.capteur = veml7700.VEML7700(i2c=self.i2c)

        self.periode_ms = periode_ms
        self.dernier_temps = time.ticks_ms()

        self.lux = 0.0
        """
        Read the current illuminance from the sensor.

        The veml7700 driver applies the gain and integration-time
        correction internally, so the returned value is directly in lux.

        Returns:
            Illuminance as a float (lux).
        """
    def lire(self):

        """
        Read the sensor only if periode_ms has elapsed since the last read.

        Returns:
            Tuple (lux: float, updated: bool).
            updated is True when a fresh measurement was taken.
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
        
        # Si le temps écoulé dépasse la période définie (2000ms)
        if time.ticks_diff(maintenant, self.dernier_temps) >= self.periode_ms:
            self.dernier_temps = maintenant # Mise à jour du chronomètre interne
            
            # Déclenchement de la lecture physique
            valeur = self.lire()
            
            # Renvoie la valeur et "True" pour signaler qu'une mise à jour a eu lieu
            return valeur, True
            
        # Sinon, renvoie la dernière valeur connue et "False"
        return self.lux, False
