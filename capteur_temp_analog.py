from machine import ADC
import time

class CapteurTempAnalog:
    """
    Cette classe gère un capteur de température de type LM335.
    Le capteur fournit une tension proportionnelle à la température en Kelvin.
    """
    
    def __init__(self, pin_adc=27, periode_ms=2000, offset_calib=-3.3):

        self.adc = ADC(pin_adc)
        
        self.periode_ms = periode_ms
        self.dernier_temps = time.ticks_ms()
        
        self.temp_c = 0.0
        self.offset = offset_calib # Correction logicielle pour la précision

    def lire(self):
        """
        Effectue une lecture précise en faisant la moyenne de plusieurs échantillons
        puis convertit le signal électrique en degrés Celsius.
        """

        somme_brute = 0
        for _ in range(10):
            somme_brute += self.adc.read_u16()
            time.sleep_ms(2) # Très courte pause entre chaque échantillon
        
        valeur_moyenne = somme_brute / 10
        
        tension = (valeur_moyenne * 3.3) / 65535
        
        temp_kelvin = tension * 100
        
        self.temp_c = (temp_kelvin - 273.15) + self.offset
        
        return round(self.temp_c, 2)

    def actualiser(self):
        """
        Gestionnaire de temps non-bloquant. 
        Décide si c'est le moment d'effectuer une nouvelle lecture.
        """
        maintenant = time.ticks_ms()
        
        if time.ticks_diff(maintenant, self.dernier_temps) >= self.periode_ms:
            self.dernier_temps = maintenant # On réinitialise le chrono
            
            return self.lire(), True
            
        return self.temp_c, False
