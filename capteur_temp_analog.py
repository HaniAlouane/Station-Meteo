"""
capteur_temp_analog.py
======================
Driver for the Texas Instruments LM335 (and pin-compatible LM135) precision
analogue temperature sensor connected to a Raspberry Pi Pico W ADC pin.

Sensor physics
--------------
The LM335 is a two-terminal Zener-like device whose breakdown voltage tracks
absolute temperature at exactly 10 mV per kelvin:

    V_out = 10 mV/K  =>  T_kelvin = V_out / 0.01

Converting to Celsius:

    T_celsius = T_kelvin - 273.15 + offset_calib

At room temperature (~300 K) the output is approximately 3.0 V, which fits
comfortably within the Pico ADC input range of 0–3.3 V.

Wiring (this project)
---------------------
The sensor is biased through a 2.2 kΩ pull-up resistor connected to the
5 V VBUS rail.  Only two of its three legs are used:

    VBUS (5 V) --> [2.2 kΩ] --> node A --> patte (+) LM335 --> GND
                                    |
                                   GP27 (ADC1)

The ADC reads the voltage at node A.  Because the Pico ADC reference is
3.3 V, the conversion formula uses 3.3 V even though the supply is 5 V:
the ADC saturates at 3.3 V and the LM335 operating point at ambient
temperatures stays safely below that ceiling.

The ADJ (adjust) pin is left unconnected; only the (+) and (−) pins are wired.

Noise reduction — oversampling
-------------------------------
The Pico W ADC is affected by switching noise from the on-board 3.3 V
regulator and the Wi-Fi radio.  A single raw sample can have a standard
deviation of several hundred LSBs.  This driver averages 10 consecutive
samples with a 2 ms gap between each one, which:

* Reduces the random noise standard deviation by sqrt(10) ≈ 3.2×.
* Allows the ADC input stage to settle between samples.
* Avoids aliasing from the Wi-Fi switching frequency.

``main.py`` uses a higher-resolution variant (50 samples) implemented
directly with a generator expression for even smoother results when
latency is not critical.

Calibration offset
------------------
An optional ``offset_calib`` parameter (default −3.3 °C) compensates for:

* Component-to-component tolerance of the LM335 (±1 °C typical).
* Resistor tolerance affecting the bias current.
* PCB self-heating when the sensor is mounted near the Pico.

Adjust this value by comparing the sensor output against a calibrated
reference thermometer at a known stable temperature.

Author : Hani AL
"""

from machine import ADC
import time


class CapteurTempAnalog:
    """10-sample oversampling driver for the LM335 / LM135 analogue temperature sensor.

    The class exposes two reading modes:

    ``lire()``
        Immediate blocking read.  Takes 10 ADC samples, averages them, and
        returns the converted temperature in degrees Celsius.  Takes roughly
        20–25 ms due to the 2 ms inter-sample delay.

    ``actualiser()``
        Non-blocking rate-limited read.  Returns cached data until
        ``periode_ms`` milliseconds have elapsed, then triggers a fresh
        ``lire()`` call.  Safe to call on every main loop iteration.

    Example::

        capteur = CapteurTempAnalog(pin_adc=27, offset_calib=-3.3)

        # In the main loop:
        temp, updated = capteur.actualiser()
    """

    # Number of ADC samples averaged per measurement.
    # Increasing this value reduces noise but increases blocking time.
    N_ECHANTILLONS = 10

    # Delay between consecutive samples in milliseconds.
    # 2 ms is enough for the ADC input stage to settle.
    DELAI_ECHANTILLON_MS = 2

    # ADC full-scale value for a 16-bit conversion (2^16 - 1).
    ADC_MAX = 65535

    # Pico ADC reference voltage in volts.
    # This is the 3.3 V rail, not the 5 V supply used to bias the sensor.
    VREF = 3.3

    # LM335 transfer function: 10 mV per kelvin -> 100 K per volt.
    LM335_K_PAR_VOLT = 100.0

    # Offset from kelvin to Celsius (0 °C = 273.15 K).
    KELVIN_OFFSET = 273.15

    def __init__(
        self,
        pin_adc:      int   = 27,
        periode_ms:   int   = 2000,
        offset_calib: float = -3.3,
    ):
        """Initialise the LM335 analogue temperature driver.

        Args:
            pin_adc      (int):   GPIO number of the ADC input pin connected
                                  to the junction of the pull-up resistor and
                                  the LM335 anode (+).  Default: 27 (ADC1).
            periode_ms   (int):   Minimum interval between physical sensor
                                  reads when using ``actualiser()``.
                                  Default: 2000 ms.
            offset_calib (float): Fixed calibration offset in degrees Celsius
                                  added after the kelvin-to-Celsius conversion.
                                  Compensates for component tolerance and
                                  self-heating.  Default: -3.3 °C.
        """
        # Bind the ADC peripheral to the chosen GPIO pin.
        self.adc = ADC(pin_adc)

        # Rate-limiting state for actualiser().
        self.periode_ms    = periode_ms
        self.dernier_temps = time.ticks_ms()

        # Last computed temperature, returned by actualiser() when the
        # interval has not yet elapsed.
        self.temp_c = 0.0

        # Calibration offset applied after the physics conversion.
        self.offset = offset_calib

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def lire(self) -> float:
        """Take an oversampled ADC reading and return the temperature in °C.

        Acquisition pipeline:

        1. **Oversampling** – read the ADC ``N_ECHANTILLONS`` times with a
           ``DELAI_ECHANTILLON_MS`` gap between samples and compute the mean.
        2. **Voltage conversion** – scale the 16-bit mean to volts using the
           3.3 V ADC reference.
        3. **Kelvin conversion** – apply the LM335 transfer function
           (10 mV/K  ->  V * 100 = T_kelvin).
        4. **Celsius conversion and offset** – subtract 273.15 K and add the
           calibration offset.

        Returns:
            float: Temperature in degrees Celsius, rounded to 2 decimal places.
        """
        # Step 1 — Oversampling: accumulate N raw 16-bit ADC readings.
        somme_brute = 0
        for _ in range(self.N_ECHANTILLONS):
            somme_brute += self.adc.read_u16()
            time.sleep_ms(self.DELAI_ECHANTILLON_MS)

        valeur_moyenne = somme_brute / self.N_ECHANTILLONS

        # Step 2 — Convert the averaged raw count to volts.
        # Formula: V = (raw / ADC_MAX) * VREF
        tension = (valeur_moyenne * self.VREF) / self.ADC_MAX

        # Step 3 — Apply the LM335 transfer function to get kelvin.
        # The sensor outputs 10 mV per kelvin, so 1 V = 100 K.
        temp_kelvin = tension * self.LM335_K_PAR_VOLT

        # Step 4 — Convert kelvin to Celsius and apply the calibration offset.
        self.temp_c = (temp_kelvin - self.KELVIN_OFFSET) + self.offset

        return round(self.temp_c, 2)

    def actualiser(self) -> tuple:
        """Return a temperature reading without blocking the main loop.

        Checks whether ``periode_ms`` milliseconds have elapsed since the last
        physical read.  If so, calls ``lire()`` and returns the fresh value.
        Otherwise, returns the cached value from the previous read immediately.

        ``ticks_diff()`` is used instead of plain subtraction to handle the
        32-bit millisecond counter rollover correctly (wraps after ~49 days).

        Returns:
            tuple: ``(temperature_celsius, updated)`` where ``updated`` is
                   True when a new measurement was taken, False otherwise.
        """
        maintenant = time.ticks_ms()

        if time.ticks_diff(maintenant, self.dernier_temps) >= self.periode_ms:
            self.dernier_temps = maintenant     # Reset the interval timer
            return self.lire(), True            # Fresh measurement

        # Interval not yet elapsed: return the last known value.
        return self.temp_c, False
