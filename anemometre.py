"""
anemometre.py — Cup anemometer driver for Raspberry Pi Pico
============================================================
Measures wind speed by timing the interval between successive
magnetic pulses produced by magnets attached to the rotating cups.

The class is designed around two separate concerns:

    ecouter()       Must be called on every main loop iteration.
                    It detects rising/falling edges on the ADC signal
                    and records the timestamp of each magnet pass.

    lire_vitesse()  Called once per reporting cycle (e.g. every 12 s).
                    It converts the last measured interval into km/h
                    using the physical geometry of the anemometer head.

Physics
-------
    One full revolution produces nb_aimants pulses.
    If the interval between two consecutive pulses is dt seconds, then:

        t_tour   = dt * nb_aimants          [seconds per revolution]
        f        = 1 / t_tour               [revolutions per second]
        v_ms     = 2 * pi * R * f           [m/s, tip speed of the cups]
        v_kmh    = v_ms * 3.6 * k           [km/h with empirical correction]

    The correction factor k compensates for mechanical friction and
    the non-ideal aerodynamics of the cup geometry.

Hardware
--------
    The sensor output is read as an analogue voltage on an ADC pin.
    A magnet passing the Hall / reed sensor produces a voltage spike
    that is detected by threshold comparison against the quiescent value.
"""
from machine import ADC
import time
import math

class CapteurVent:


    """Pulse-counting wind speed sensor with timed interval measurement."""
    def __init__(self, pin_adc=26, rayon_m=0.17, nb_aimants=2, coeff_k=2.8):

        self.capteur = ADC(pin_adc)
        """
        Args:
            pin_adc:    GPIO number of the ADC input (default GP26).
            rayon_m:    Arm radius of the anemometer head in metres.
            nb_aimants: Number of magnets on the rotor (pulses per revolution).
            coeff_k:    Empirical correction factor for friction and cup drag.
        """
        self.rayon = rayon_m        # Rayon des bras de l'anémomètre (en mètres)
        self.nb_aimants = nb_aimants # Nombre d'aimants fixés sur l'axe
        self.coeff_k = coeff_k      # Facteur de correction (frottements/aérodynamisme)

        self.aimant_present = False

        self.dernier_temps_aimant = 0  # Timestamp du dernier passage (ms)
        self.intervalle_ms = 0         # Durée écoulée entre deux passages (ms)
        self.vitesse_exacte = 0.0      # Résultat final en km/h
        """
        Sample the ADC and update timing state.

        Must be called as frequently as possible (every main loop
        iteration) to avoid missing pulses at high wind speeds.

        Detection thresholds:
            < 20 000  or  > 42 500  → magnet present  (leading edge)
            28 000 – 38 000         → quiescent value  (trailing edge)
        """
    def ecouter(self):

        # Leading edge: magnet detected for the first time
        valeur = self.capteur.read_u16() # Lecture brute (0 à 65535)

        # Trailing edge: signal returned to quiescent range, ready for next pulse
        if (valeur < 20000 or valeur > 42500) and not self.aimant_present:
            maintenant = time.ticks_ms() # On prend l'heure précise

            if self.dernier_temps_aimant > 0:
                self.intervalle_ms = time.ticks_diff(maintenant, self.dernier_temps_aimant)
        """
        Compute the current wind speed from the last pulse interval.

        A 2-second timeout is applied: if no pulse has been received
        within that window, the rotor is assumed to be stationary and
        speed is set to 0.0 km/h.

        Returns:
            Tuple (speed_kmh: float, valid: bool).
            valid is always True for compatibility with legacy callers.
        """
            self.dernier_temps_aimant = maintenant
            self.aimant_present = True # On marque l'aimant comme "déjà vu"

        # No pulse in the last 2 s → anemometer stopped
        elif (28000 < valeur < 38000) and self.aimant_present:
            self.aimant_present = False

    def lire_vitesse(self):

        maintenant = time.ticks_ms()
        
        # SÉCURITÉ : Si aucun aimant n'est passé depuis plus de 2 secondes,
        # cela signifie que l'anémomètre s'est arrêté.
        if time.ticks_diff(maintenant, self.dernier_temps_aimant) > 2000:
            self.vitesse_exacte = 0.0
            self.intervalle_ms = 0
            
        # CALCUL MATHÉMATIQUE
        elif self.intervalle_ms > 0:
            # 1. Conversion de l'intervalle en secondes
            dt_secondes = self.intervalle_ms / 1000.0
            
            # 2. Temps nécessaire pour une rotation complète (360°)
            temps_un_tour = dt_secondes * self.nb_aimants
            
            # 3. Calcul de la fréquence de rotation (tours par seconde)
            frequence_hz = 1.0 / temps_un_tour
            
            # 4. Formule de la vitesse linéaire : V = 2 * pi * R * f
            # Résultat en mètres par seconde (m/s)
            vitesse_m_s = 2 * math.pi * self.rayon * frequence_hz
            
            # 5. Conversion en km/h (x 3.6) et application du coefficient de correction (k)
            self.vitesse_exacte = vitesse_m_s * 3.6 * self.coeff_k
            
        return self.vitesse_exacte, True
