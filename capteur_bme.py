"""
capteur_bme.py
==============
Convenience wrapper around the low-level ``bme280.py`` driver for the
Bosch BME280 environmental sensor.

Responsibility
--------------
This module sits between ``main.py`` and the raw ``bme280.py`` driver.
Its job is to:

* Hold a reference to the shared I2C bus (created once in ``main.py``).
* Expose a simple ``lire()`` method that returns a clean (temp, pressure,
  humidity) tuple without the caller needing to know anything about the
  BME280 register map.
* Provide a non-blocking ``actualiser()`` method that rate-limits sensor
  reads to once per ``periode_ms`` milliseconds, so ``main.py`` can call
  it freely on every loop iteration without hammering the I2C bus.

Design note — temperature
--------------------------
The BME280 measures temperature internally, but the value returned by
``lire()`` is intentionally discarded by ``main.py``.  The station uses a
dedicated LM335 analogue sensor mounted outdoors for temperature, which is
more accurate and avoids the self-heating bias that affects the BME280 when
it is close to the Pico W's processor.

The first element of the tuple is kept in the return value so that
``actualiser()`` can be used generically, but callers should unpack it with
an underscore: ``_, pressure, humidity = capteur.lire()``.

I2C addressing
--------------
The standard I2C address for the blue/violet BME280 breakout modules is
``0x76`` (SDO pin pulled LOW).  If your module has SDO tied HIGH, change
the address to ``0x77`` in the constructor call below.

Dependencies
------------
    bme280.py   Low-level Bosch BME280 driver (included in this project).
                Original authors: Paul Cunnane, Peter Dahlberg (2016).

Author : Hani AL
"""

from machine import Pin, I2C
import time
import bme280


class CapteurBME280:
    """Non-blocking wrapper for the Bosch BME280 pressure and humidity sensor.

    The sensor communicates over I2C and shares the bus with the VEML7700
    light sensor and the SSD1306 OLED display.  The I2C object must be
    created externally (in ``main.py``) and passed in, so all three devices
    use the same bus instance.

    Example::

        bus = I2C(0, scl=Pin(5), sda=Pin(4), freq=100_000)
        capteur = CapteurBME280(bus)

        # In the main loop:
        (temp, pression, humidite), updated = capteur.actualiser()
    """

    # Default I2C address for blue/violet BME280 breakout modules (SDO = LOW).
    ADRESSE_I2C = 0x76

    def __init__(self, i2c_objet: I2C, periode_ms: int = 2000):
        """Initialise the BME280 wrapper.

        Args:
            i2c_objet  (I2C): An already-initialised ``machine.I2C`` instance
                              shared with the other I2C devices on the bus.
                              Creating a second I2C object on the same pins
                              would cause bus contention.
            periode_ms (int): Minimum time between two consecutive physical
                              sensor reads when using ``actualiser()``.
                              Default is 2000 ms (2 seconds).
        """
        # Keep a reference to the shared bus; do not re-initialise it here.
        self.i2c = i2c_objet

        # Instantiate the low-level driver at the standard I2C address.
        # This sends the initialisation sequence to the BME280 and loads
        # the factory calibration coefficients stored in the sensor's ROM.
        self.capteur = bme280.BME280(i2c=self.i2c, address=self.ADRESSE_I2C)

        # Rate-limiting state for the non-blocking actualiser() method.
        self.periode_ms    = periode_ms
        self.dernier_temps = time.ticks_ms()   # Timestamp of the last read

        # Cached sensor values, initialised to None until the first read.
        # None is used instead of 0 so that callers can distinguish
        # "not yet measured" from a genuine zero reading.
        self.temperature = None
        self.pression    = None
        self.humidite    = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def lire(self) -> tuple:
        """Read all three quantities from the BME280 immediately.

        This is a blocking call: it triggers a forced-mode measurement on
        the sensor, waits for the conversion to complete (a few ms), then
        reads back the compensated values.  The results are cached in the
        instance attributes and returned as a tuple.

        The ``bme280.py`` driver returns the values already converted to
        human-readable units via its ``values`` property:
            - temperature in degrees Celsius  (float)
            - pressure    in hPa              (int or float)
            - humidity    in percent RH       (int or float)

        Note: the temperature value is returned for completeness but is
        not used by ``main.py``.  See the module docstring for the reason.

        Returns:
            tuple: ``(temperature, pression, humidite)``
        """
        valeurs = self.capteur.values   # Triggers a measurement on the chip

        # Unpack and cache the three readings.
        self.temperature = valeurs[0]   # Degrees Celsius  (not used by main.py)
        self.pression    = valeurs[1]   # Hectopascals
        self.humidite    = valeurs[2]   # Percent relative humidity

        return self.temperature, self.pression, self.humidite

    def actualiser(self) -> tuple:
        """Read the sensor only if ``periode_ms`` has elapsed since the last read.

        This is the recommended method to use inside a fast polling loop.
        It checks the elapsed time with ``ticks_diff()`` (which handles the
        32-bit millisecond counter rollover correctly) and only triggers a
        physical sensor read when the interval has expired.

        When the interval has not yet elapsed, the method returns the cached
        values from the previous read instead of blocking.  The boolean flag
        in the return value lets the caller know whether the data is fresh.

        Returns:
            tuple: ``((temperature, pression, humidite), updated)`` where
                   ``updated`` is True when a new measurement was taken,
                   or False when the cached values were returned unchanged.
        """
        maintenant = time.ticks_ms()

        if time.ticks_diff(maintenant, self.dernier_temps) >= self.periode_ms:
            # Enough time has passed: take a fresh reading.
            self.dernier_temps = maintenant     # Reset the timer
            valeurs = self.lire()
            return valeurs, True                # Signal: data is fresh

        # Not enough time has passed: return the last known values.
        return (self.temperature, self.pression, self.humidite), False
