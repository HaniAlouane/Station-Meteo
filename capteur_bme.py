"""
capteur_bme.py — BME280 sensor wrapper (pressure, humidity)
============================================================
Thin convenience layer around the low-level bme280.py driver.
Provides a simple lire() method that returns the three measured
quantities as a tuple and an optional non-blocking actualiser()
method for use in poll-driven architectures.

The temperature output of the BME280 is intentionally ignored in
this project because a dedicated LM335 analogue sensor (read in
main.py) provides a more accurate outdoor temperature reading.

I2C address
-----------
    0x76 — standard address for the blue/violet BME280 modules.
    Change to 0x77 if your module has the SDO pin tied high.
"""
from machine import Pin, I2C
import time
import bme280

class CapteurBME280:


    """Non-blocking wrapper for the Bosch BME280 environmental sensor."""
    def __init__(self, i2c_objet, periode_ms=2000):

        self.i2c = i2c_objet
        """
        Args:
            i2c_objet:  An already-initialised machine.I2C instance
                        shared with other devices on the same bus.
            periode_ms: Minimum time between two consecutive readings
                        when using actualiser() (default 2000 ms).
        """
        self.capteur = bme280.BME280(i2c=self.i2c, address=0x76)

        self.periode_ms = periode_ms
        self.dernier_temps = time.ticks_ms() # Enregistre le moment du démarrage

        self.temperature = None
        self.pression = None
        self.humidite = None

    def lire(self):
        """
        Read all three quantities from the sensor immediately.

        Returns:
            Tuple (temperature, pression, humidite) where values are
            numbers (floats/ints depending on the bme280 driver).
        """

        valeurs = self.capteur.values
        """
        Read the sensor only if periode_ms has elapsed since the last read.

        Useful for rate-limiting sensor access in a busy loop without
        using time.sleep().

        Returns:
            Tuple ((temperature, pression, humidite), updated: bool).
            updated is True when a new measurement was performed.
        """
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
