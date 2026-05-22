"""
sd_logger.py
============
Append-only CSV data logger backed by a FAT32 micro-SD card connected to
the Raspberry Pi Pico W over SPI bus 0.

Architecture
------------
The class is designed around a "fail-silent" philosophy: every method that
touches the SD card wraps its operations in a try/except block and swallows
all exceptions internally.  This means ``main.py`` can call
``sd.enregistrer(payload)`` unconditionally on every acquisition cycle
without needing any error-handling logic of its own.  If the card is absent,
full, or corrupted, the firmware simply continues running and routes data to
the other output channels (USB / Wi-Fi).

If a write fails, the class automatically attempts to remount the card before
returning, so a briefly disconnected card can recover on the next cycle.

SPI wiring (Pico W, bus 0)
--------------------------
    SD MISO  ->  GP16   (pin 21)
    SD CS    ->  GP17   (pin 22)
    SD SCK   ->  GP18   (pin 24)
    SD MOSI  ->  GP19   (pin 25)
    SD VCC   ->  3.3 V
    SD GND   ->  GND

SPI parameters: baudrate = 4 MHz, mode 0 (polarity=0, phase=0), MSB first,
8 bits per transfer.

Output file format
------------------
The logger creates a single file ``/sd/meteo.csv`` on the card.  A header
row is written automatically the first time the file is created:

    timestamp,vitesse_vent,luminosite,temperature,humidite,pression

Each subsequent row is appended once per 12-second acquisition cycle:

    42,2.45,320.1,21.3,58.0,1013.2

The ``timestamp`` column is the number of seconds elapsed since the Pico
last booted, derived from ``time.ticks_ms() // 1000``.  It is not a
wall-clock timestamp because the Pico W has no real-time clock (RTC) by
default.  Add an RTC module or an NTP sync if absolute timestamps are needed.

Dependencies
------------
    sdcard.py   Official MicroPython SPI SD-card block driver.
                Must be copied to the Pico filesystem.
                Source: https://github.com/micropython/micropython-lib/blob/
                        master/micropython/drivers/storage/sdcard/sdcard.py

Author : Hani AL
"""

import os
import time

# Guard import: sdcard.py and the machine module are only available on the
# Pico.  The _SD_DISPONIBLE flag lets the class fail gracefully when the
# driver file is missing, rather than crashing at import time.
try:
    from machine import SPI, Pin
    import sdcard
    _SD_DISPONIBLE = True
except ImportError:
    _SD_DISPONIBLE = False


class SDLogger:
    """Append-only CSV logger backed by a FAT32 micro-SD card over SPI.

    All public methods are safe to call unconditionally: they return silently
    when the card is absent or after an unrecoverable error, so the calling
    code never needs to wrap them in try/except.

    Example::

        sd = SDLogger()

        # In the main loop (every 12 seconds):
        sd.enregistrer({
            "vitesse_vent": 2.45,
            "luminosite":   320.1,
            "temperature":  21.3,
            "humidite":     58.0,
            "pression":     1013.2,
        })

        if sd.disponible:
            print("SD card is healthy")
    """

    # Filesystem mount point for the SD card.
    CHEMIN_MONTAGE = "/sd"

    # Name of the CSV log file created on the card.
    NOM_FICHIER = "meteo.csv"

    # Header row written once when the file is first created.
    EN_TETE_CSV = "timestamp,vitesse_vent,luminosite,temperature,humidite,pression\n"

    # SPI clock frequency in Hz.  4 MHz is a conservative but reliable
    # speed for most SD cards over breadboard wires.
    SPI_BAUDRATE = 4_000_000

    def __init__(self):
        """Initialise the logger and attempt to mount the SD card.

        If the card is not present or the mount fails, ``_montee`` is set to
        False and all subsequent calls to ``enregistrer()`` return immediately
        without raising an exception.
        """
        self._montee         = False
        self._chemin_complet = f"{self.CHEMIN_MONTAGE}/{self.NOM_FICHIER}"
        self._tenter_montage()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _tenter_montage(self):
        """Initialise the SPI bus, mount the FAT filesystem, and create the log file.

        Called once at construction time and again automatically after a
        failed write (to recover from a card that was briefly disconnected).

        All errors are caught and printed to the serial console.  The method
        never raises an exception to the caller.
        """
        if not _SD_DISPONIBLE:
            print("[SD] sdcard.py not found - SD logging disabled")
            return

        try:
            # Configure SPI bus 0 with the pins defined in the wiring table.
            # Mode 0 (polarity=0, phase=0) is required by the SD card spec.
            spi = SPI(
                0,
                baudrate  = self.SPI_BAUDRATE,
                polarity  = 0,
                phase     = 0,
                bits      = 8,
                firstbit  = SPI.MSB,
                sck       = Pin(18),
                mosi      = Pin(19),
                miso      = Pin(16),
            )

            # Chip-select pin: active LOW, driven by the SDCard driver.
            cs = Pin(17, Pin.OUT)

            # Instantiate the block device and wrap it in a FAT filesystem.
            sd  = sdcard.SDCard(spi, cs)
            vfs = os.VfsFat(sd)

            # Mount the filesystem at CHEMIN_MONTAGE so standard file I/O
            # calls (open, os.stat, etc.) work transparently.
            os.mount(vfs, self.CHEMIN_MONTAGE)
            self._montee = True
            print("[SD] Card mounted successfully")

            # Create the CSV file with its header row if it does not yet exist.
            self._creer_en_tete_si_absent()

        except Exception as e:
            self._montee = False
            print(f"[SD] Mount failed: {e}")

    def _creer_en_tete_si_absent(self):
        """Write the CSV header row if the log file does not yet exist.

        Uses ``os.stat()`` to check for the file's existence.  A missing file
        raises ``OSError``, which we catch to trigger the creation.  This
        avoids opening the file in append mode and checking its size, which
        would be slower and less reliable on FAT filesystems.
        """
        try:
            os.stat(self._chemin_complet)       # Raises OSError if file is absent
        except OSError:
            # File does not exist yet: create it and write the header.
            with open(self._chemin_complet, "w") as f:
                f.write(self.EN_TETE_CSV)
            print(f"[SD] New log file created: {self._chemin_complet}")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def enregistrer(self, payload: dict):
        """Append one CSV row to the log file.

        The row contains a boot-relative timestamp (seconds) followed by the
        five sensor readings.  Missing keys in ``payload`` are replaced with 0.

        If the write fails (e.g. the card was removed), the method sets
        ``_montee`` to False and immediately calls ``_tenter_montage()`` to
        attempt an automatic recovery.  The failed row is lost, but subsequent
        calls will succeed once the card is remounted.

        Args:
            payload (dict): Sensor readings with the following keys:
                            ``vitesse_vent``, ``luminosite``, ``temperature``,
                            ``humidite``, ``pression``.
                            Extra keys are ignored; missing keys default to 0.
        """
        # Return silently if the card is not available.
        if not self._montee:
            return

        # Build the timestamp: seconds elapsed since the Pico last booted.
        # ticks_ms() rolls over after ~49 days; integer division to seconds
        # keeps the value human-readable in the CSV.
        ts = time.ticks_ms() // 1000

        ligne = (
            f"{ts},"
            f"{payload.get('vitesse_vent', 0)},"
            f"{payload.get('luminosite',   0)},"
            f"{payload.get('temperature',  0)},"
            f"{payload.get('humidite',     0)},"
            f"{payload.get('pression',     0)}\n"
        )

        try:
            # Open in append mode so each call adds exactly one row without
            # loading the entire file into RAM (important on an embedded target).
            with open(self._chemin_complet, "a") as f:
                f.write(ligne)
            print(f"[SD] Row written: {ligne.strip()}")

        except Exception as e:
            print(f"[SD] Write error: {e}")
            # Mark the card as unavailable and try to remount it so the next
            # call to enregistrer() can succeed if the card is still present.
            self._montee = False
            self._tenter_montage()

    @property
    def disponible(self) -> bool:
        """True if the SD card is mounted and ready for writing.

        This property is polled by ``main.py`` to decide what to display on
        the OLED diagnostic screen and in the serial status line.
        """
        return self._montee
