"""
capteur_temp_analog.py — LM335 analogue temperature sensor driver
=================================================================
Reads a Texas Instruments LM335 (or LM135) precision temperature
sensor connected to a Pico ADC pin and converts the raw voltage to
degrees Celsius.

Sensor physics
--------------
The LM335 outputs a voltage proportional to absolute temperature:

    V_out = 10 mV / K  →  T_kelvin = V_out / 0.01

Conversion to Celsius:

    T_celsius = T_kelvin - 273.15 + offset_calib

An optional calibration offset (default −3.3 °C) compensates for
component tolerance and PCB self-heating.

Noise reduction
---------------
The ADC on the Pico W is susceptible to high-frequency noise from
the switching regulator and the Wi-Fi radio.  This driver averages
10 consecutive samples to reduce the standard deviation of the reading
by a factor of sqrt(10) ≈ 3.2.

Note: main.py uses a higher-resolution version (50 samples) implemented
directly with a generator expression for even smoother results.
"""
from machine import ADC
import time

class CapteurTempAnalog:


    """10-sample averaging driver for LM335 / LM135 analogue temperature sensors."""
    def __init__(self, pin_adc=27, periode_ms=2000, offset_calib=-3.3):

        self.adc = ADC(pin_adc)
        """
        Args:
            pin_adc:       GPIO number of the ADC input (default GP27).
            periode_ms:    Minimum time between readings in actualiser()
                           (default 2000 ms).
            offset_calib:  Fixed calibration offset in °C applied after
                           conversion (default −3.3 °C).
        """
        self.periode_ms = periode_ms
        self.dernier_temps = time.ticks_ms()

        self.temp_c = 0.0
        self.offset = offset_calib # Correction logicielle pour la précision
        """
        Average 10 ADC samples and convert to degrees Celsius.

        A 2 ms delay between samples allows the ADC input stage to
        settle and avoids aliasing from the Wi-Fi switching noise.

        Returns:
            Temperature in °C, rounded to 2 decimal places.
        """
    def lire(self):


        somme_brute = 0
        for _ in range(10):
            somme_brute += self.adc.read_u16()
            time.sleep_ms(2) # Très courte pause entre chaque échantillon
        """
        Read the sensor only if periode_ms has elapsed since the last read.

        Returns:
            Tuple (temp_celsius: float, updated: bool).
            updated is True when a fresh measurement was taken.
        """
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
