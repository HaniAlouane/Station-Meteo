"""
capteur_lux.py
==============
Convenience wrapper around the low-level ``veml7700.py`` driver for the
Vishay VEML7700 ambient light sensor.

Sensor overview
---------------
The VEML7700 is a high-accuracy ambient light sensor that communicates over
I2C at the fixed address ``0x10``.  It supports a wide dynamic range of
approximately 0 to 120 000 lux, making it suitable for both indoor
environments (a few hundred lux) and full-sunlight outdoor measurements
(up to ~100 000 lux on a clear day).

The sensor applies gain and integration-time compensation internally.  The
``read_lux()`` method in ``veml7700.py`` already returns a calibrated value
in lux, so this wrapper does not need to perform any additional scaling.

Integration time and gain
--------------------------
The ``veml7700.py`` driver is initialised with default parameters
(integration time = 25 ms, gain = 1/8).  These settings favour a wide
dynamic range over maximum sensitivity in low-light conditions.  If the
station is deployed indoors or in a shaded location, consider increasing
the integration time (e.g. to 100 or 200 ms) and the gain when
instantiating the ``VEML7700`` object to improve resolution at low lux.

I2C bus sharing
---------------
The VEML7700 shares the I2C bus (GP4 / GP5) with the BME280 pressure
sensor (address ``0x76``) and the SSD1306 OLED display (address ``0x3C``).
The I2C object must be created once in ``main.py`` and passed to all three
wrappers so they use the same underlying bus instance.

Responsibility of this module
------------------------------
* Hold a reference to the shared I2C bus.
* Expose a simple ``lire()`` method that returns the current lux value.
* Provide a non-blocking ``actualiser()`` method that rate-limits sensor
  reads so ``main.py`` can call it freely on every loop iteration.

Dependencies
------------
    veml7700.py   Low-level VEML7700 I2C driver (included in this project).
                  Original author: Joseph Hopfmüller (fork of C. Rousseau, 2019).

Author : Hani AL
"""

from machine import Pin, I2C
import time
import veml7700


class CapteurLumiere:
    """Non-blocking wrapper for the Vishay VEML7700 ambient light sensor.

    The class exposes two reading modes:

    ``lire()``
        Immediate blocking read.  Queries the sensor and returns the current
        illuminance in lux.  The ``veml7700.py`` driver inserts a short
        internal delay (~40 ms) to ensure the integration period is complete
        before reading the result register.

    ``actualiser()``
        Non-blocking rate-limited read.  Returns the cached lux value until
        ``periode_ms`` milliseconds have elapsed, then triggers a fresh
        ``lire()`` call.  Safe to call on every main loop iteration without
        slowing down the anemometer polling.

    Example::

        bus     = I2C(0, scl=Pin(5), sda=Pin(4), freq=100_000)
        lumiere = CapteurLumiere(bus)

        # In the main loop:
        lux, updated = lumiere.actualiser()
    """

    # Fixed I2C address of the VEML7700 (not configurable on the hardware).
    ADRESSE_I2C = 0x10

    def __init__(self, i2c_objet: I2C, periode_ms: int = 2000):
        """Initialise the VEML7700 wrapper.

        Args:
            i2c_objet  (I2C): An already-initialised ``machine.I2C`` instance
                              shared with the BME280 and OLED on the same bus.
                              Do not create a second I2C object on the same
                              pins; it would cause bus contention.
            periode_ms (int): Minimum interval between two physical sensor
                              reads when using ``actualiser()``.
                              Default: 2000 ms.
                              Note: the VEML7700 itself needs ~40 ms per
                              conversion, so values below 50 ms are not useful.
        """
        # Keep a reference to the shared bus; do not re-initialise it here.
        self.i2c = i2c_objet

        # Instantiate the low-level driver.  The constructor sends the
        # configuration registers to the sensor (gain, integration time,
        # interrupt thresholds, and power-save mode).
        self.capteur = veml7700.VEML7700(i2c=self.i2c)

        # Rate-limiting state for the non-blocking actualiser() method.
        self.periode_ms    = periode_ms
        self.dernier_temps = time.ticks_ms()

        # Cache for the last lux reading returned by lire().
        # Initialised to 0.0 so actualiser() always has a valid value
        # to return before the first physical read occurs.
        self.lux = 0.0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def lire(self) -> float:
        """Read the current illuminance from the VEML7700 sensor.

        Delegates to ``veml7700.VEML7700.read_lux()``, which:

        1. Waits 40 ms for the current integration period to finish.
        2. Reads the raw ALS (Ambient Light Sensor) register over I2C.
        3. Multiplies the raw count by the gain/integration-time factor
           stored in the driver to produce a calibrated lux value.

        The result is cached in ``self.lux`` so ``actualiser()`` can return
        it without re-querying the sensor when the interval has not elapsed.

        Returns:
            float: Illuminance in lux (rounded to the nearest integer by the
                   underlying driver).
        """
        self.lux = self.capteur.read_lux()
        return self.lux

    def actualiser(self) -> tuple:
        """Return a lux reading without blocking the main loop.

        Checks whether ``periode_ms`` milliseconds have elapsed since the last
        physical read using ``ticks_diff()``, which handles the 32-bit
        millisecond counter rollover correctly (~49-day wrap-around).

        When the interval has not yet elapsed, the cached value from the
        previous read is returned immediately.  The boolean flag lets the
        caller know whether the data is fresh.

        Returns:
            tuple: ``(lux, updated)`` where ``lux`` is the illuminance in lux
                   and ``updated`` is True when a new measurement was taken,
                   False when the cached value was returned.
        """
        maintenant = time.ticks_ms()

        if time.ticks_diff(maintenant, self.dernier_temps) >= self.periode_ms:
            # Enough time has elapsed: take a fresh reading.
            self.dernier_temps = maintenant     # Reset the interval timer
            valeur = self.lire()
            return valeur, True                 # Signal: data is fresh

        # Interval not yet elapsed: return the last known lux value.
        return self.lux, False
