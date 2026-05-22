"""
anemometre.py
=============
Driver for a cup anemometer connected to the Raspberry Pi Pico W via an
analogue ADC pin.

Working principle
-----------------
The anemometer rotor carries a small permanent magnet.  As the cups spin,
the magnet passes a Hall-effect or reed sensor once per revolution (or once
per pole if multiple magnets are fitted).  Each pass produces a brief voltage
spike on the analogue output line.

The driver detects these spikes by threshold comparison and records the
timestamp of each one.  Wind speed is then derived from the time interval
between two consecutive spikes:

    dt          = time between two pulses           [seconds]
    t_rev       = dt * nb_aimants                   [seconds per revolution]
    f           = 1 / t_rev                         [revolutions per second]
    v_tip       = 2 * pi * R * f                    [m/s, tip speed of cups]
    v_wind      = v_tip * 3.6 * k                   [km/h, corrected]

The correction factor k compensates for mechanical friction in the bearing
and the aerodynamic inefficiency of the cup geometry.  Its value (default
2.8) was determined empirically by comparison with a reference anemometer.

ADC detection thresholds
------------------------
At rest the sensor output sits in the quiescent band (roughly 28 000-38 000
on a 16-bit scale at 3.3 V).  A magnet pass pulls the output out of this
band:

    value < 20 000  or  value > 42 500  ->  magnet detected (pulse start)
    28 000 < value < 38 000             ->  quiescent (pulse end)

The hysteresis gap between these two zones prevents spurious re-triggering
on a noisy signal.

Usage
-----
    from anemometre import CapteurVent

    vent = CapteurVent(pin_adc=26)

    while True:
        vent.ecouter()          # Call as often as possible

    speed_kmh, _ = vent.lire_vitesse()   # Call once per reporting cycle

Author : Hani AL
"""

from machine import ADC
import time
import math


class CapteurVent:
    """Pulse-interval wind speed sensor driver for the Raspberry Pi Pico W.

    The class separates two concerns deliberately:

    ``ecouter()``
        Must be called on every main loop iteration.  It samples the ADC,
        detects magnet passes by threshold comparison, and records the
        inter-pulse interval.  Calling it less frequently risks missing
        pulses at high wind speeds.

    ``lire_vitesse()``
        Called once per reporting cycle (e.g. every 12 seconds).  It
        converts the last measured interval into km/h and applies the
        2-second stall timeout.
    """

    # Pulse detection thresholds (16-bit ADC values, 0-65535).
    # The sensor quiescent level sits between SEUIL_BAS and SEUIL_HAUT.
    # A magnet pass pulls the reading outside this band.
    SEUIL_BAS  = 20_000     # Below this  -> magnet detected
    SEUIL_HAUT = 42_500     # Above this  -> magnet detected
    NEUTRE_BAS = 28_000     # Lower bound of the quiescent zone
    NEUTRE_HAUT = 38_000    # Upper bound of the quiescent zone

    # If no pulse is received within this window the rotor is considered
    # stationary and speed is set to 0.0 km/h.
    TIMEOUT_ARRET_MS = 2_000

    def __init__(
        self,
        pin_adc:   int   = 26,
        rayon_m:   float = 0.17,
        nb_aimants: int  = 2,
        coeff_k:   float = 2.8,
    ):
        """Initialise the anemometer driver.

        Args:
            pin_adc    (int):   GPIO number of the ADC input pin.
                                Must be one of GP26, GP27, or GP28.
                                Default: 26 (ADC0).
            rayon_m    (float): Arm radius of the anemometer head in metres.
                                Measured from the rotation axis to the centre
                                of a cup.  Default: 0.17 m.
            nb_aimants (int):   Number of magnets mounted on the rotor.
                                Each full revolution generates this many
                                pulses.  Default: 2.
            coeff_k    (float): Empirical correction factor applied to the
                                final speed value to account for bearing
                                friction and cup aerodynamics.  Default: 2.8.
        """
        # ADC object bound to the chosen GPIO pin.
        self.capteur = ADC(pin_adc)

        # Physical parameters of the anemometer head.
        self.rayon      = rayon_m       # Cup arm radius [m]
        self.nb_aimants = nb_aimants    # Pulses per revolution
        self.coeff_k    = coeff_k       # Empirical correction factor

        # Debounce flag: True while the magnet is still inside the
        # detection zone.  Prevents counting the same pass multiple times.
        self.aimant_present = False

        # Timing state.
        self.dernier_temps_aimant = 0   # ticks_ms() of the last pulse
        self.intervalle_ms        = 0   # Duration between the last two pulses [ms]
        self.vitesse_exacte       = 0.0 # Most recent computed speed [km/h]

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def ecouter(self):
        """Sample the ADC and update the pulse timing state.

        This method implements a two-zone threshold detector with hysteresis:

        * **Leading edge** – when the ADC reading leaves the quiescent band
          (value < SEUIL_BAS or value > SEUIL_HAUT) and ``aimant_present``
          is False, a new pulse is recorded.  The inter-pulse interval is
          computed and stored, and the debounce flag is set to True.

        * **Trailing edge** – when the ADC reading returns to the quiescent
          band (NEUTRE_BAS < value < NEUTRE_HAUT) and ``aimant_present`` is
          True, the debounce flag is cleared, making the detector ready for
          the next pulse.

        This method must be called as frequently as possible.  At a wind
        speed of 60 km/h with the default geometry, pulses arrive roughly
        every 115 ms, so any call interval well below that is acceptable.
        """
        valeur = self.capteur.read_u16()    # Raw 16-bit ADC reading (0-65535)

        # --- Leading edge: magnet entering the detection zone ---
        if (valeur < self.SEUIL_BAS or valeur > self.SEUIL_HAUT) \
                and not self.aimant_present:

            maintenant = time.ticks_ms()

            # Compute the interval only after the first pulse has been seen,
            # otherwise dernier_temps_aimant is still 0 (boot value).
            if self.dernier_temps_aimant > 0:
                self.intervalle_ms = time.ticks_diff(
                    maintenant, self.dernier_temps_aimant
                )

            self.dernier_temps_aimant = maintenant
            self.aimant_present = True      # Lock out further leading-edge events

        # --- Trailing edge: signal returned to the quiescent zone ---
        elif (self.NEUTRE_BAS < valeur < self.NEUTRE_HAUT) \
                and self.aimant_present:
            self.aimant_present = False     # Ready to detect the next pulse

    def lire_vitesse(self):
        """Compute the current wind speed from the last recorded pulse interval.

        If no pulse has been received within TIMEOUT_ARRET_MS milliseconds,
        the rotor is assumed to be stationary and the speed is set to 0.0.

        The physics:
            dt      = intervalle_ms / 1000              [seconds]
            t_rev   = dt * nb_aimants                   [s / revolution]
            f       = 1 / t_rev                         [Hz]
            v_ms    = 2 * pi * rayon * f                [m/s]
            v_kmh   = v_ms * 3.6 * coeff_k             [km/h]

        Returns:
            tuple[float, bool]: ``(speed_kmh, True)``.
                The boolean is always True and exists for compatibility
                with callers that unpack two values.
        """
        maintenant = time.ticks_ms()

        # Stall detection: no pulse in the last TIMEOUT_ARRET_MS ms.
        if time.ticks_diff(maintenant, self.dernier_temps_aimant) \
                > self.TIMEOUT_ARRET_MS:
            self.vitesse_exacte = 0.0
            self.intervalle_ms  = 0

        # Normal case: compute speed from the last inter-pulse interval.
        elif self.intervalle_ms > 0:
            dt_secondes   = self.intervalle_ms / 1000.0    # [s]
            temps_un_tour = dt_secondes * self.nb_aimants  # [s/rev]
            frequence_hz  = 1.0 / temps_un_tour            # [rev/s]
            vitesse_m_s   = 2 * math.pi * self.rayon * frequence_hz  # [m/s]
            self.vitesse_exacte = vitesse_m_s * 3.6 * self.coeff_k   # [km/h]

        return self.vitesse_exacte, True
