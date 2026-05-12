"""
sd_logger.py — CSV data logger for micro-SD card
=================================================
Mounts a FAT32-formatted micro-SD card over SPI and appends one CSV
row per call to enregistrer().  All failures are caught internally so
the caller (main.py) never has to handle SD-related exceptions.

Wiring (SPI bus 0)
------------------
    SD MISO  → GP16
    SD CS    → GP17
    SD SCK   → GP18
    SD MOSI  → GP19
    SD VCC   → 3.3 V
    SD GND   → GND

Requires sdcard.py (official MicroPython SPI SD driver) on the Pico.
Source: https://github.com/micropython/micropython-lib/blob/master/micropython/drivers/storage/sdcard/sdcard.py

Output format
-------------
    meteo.csv — one header row, then one data row every 12 seconds:

    timestamp,vitesse_vent,luminosite,temperature,humidite,pression
    42,2.45,320.1,21.3,58.0,1013.2
"""
import os
import time

try:
    from machine import SPI, Pin
    import sdcard
    _SD_DISPONIBLE = True
except ImportError:
    _SD_DISPONIBLE = False

class SDLogger:


    """Append-only CSV logger backed by a FAT32 micro-SD card."""
    CHEMIN_MONTAGE = "/sd"
    NOM_FICHIER    = "meteo.csv"
    EN_TETE_CSV    = "timestamp,vitesse_vent,luminosite,temperature,humidite,pression\n"

    def __init__(self):
        self._montee = False
        self._chemin_complet = f"{self.CHEMIN_MONTAGE}/{self.NOM_FICHIER}"
        self._tenter_montage()

    def _tenter_montage(self):

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

        if not _SD_DISPONIBLE:
            print("⚠️  [SD] sdcard.py introuvable — journalisation SD désactivée.")
            return
        try:
            spi = SPI(0,
                      baudrate=4_000_000,
                      polarity=0,
                      phase=0,
                      bits=8,
                      firstbit=SPI.MSB,
                      sck=Pin(18),
                      mosi=Pin(19),
                      miso=Pin(16))
            cs  = Pin(17, Pin.OUT)
            sd  = sdcard.SDCard(spi, cs)
        """
        Initialise the SPI bus, mount the SD card as a FAT filesystem
        at /sd, and create the CSV file with its header if it does not
        already exist.  All errors are printed but swallowed so the
        rest of the firmware continues to run without a card.
        """
            vfs = os.VfsFat(sd)
            os.mount(vfs, self.CHEMIN_MONTAGE)
            self._montee = True
            print("✅ [SD] Carte SD montée avec succès.")
            self._creer_en_tete_si_absent()
        except Exception as e:
            self._montee = False
            print(f"❌ [SD] Impossible de monter la carte SD : {e}")

    def _creer_en_tete_si_absent(self):
        """Write the CSV header row if the log file does not yet exist."""
        try:
            os.stat(self._chemin_complet)          # Lève OSError si absent
        except OSError:
            with open(self._chemin_complet, "w") as f:
                f.write(self.EN_TETE_CSV)
            print(f"📄 [SD] Nouveau fichier créé : {self._chemin_complet}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enregistrer(self, payload: dict):
        """
        Append one CSV row to the log file.

        The timestamp column contains the number of seconds elapsed
        since the Pico last booted (derived from time.ticks_ms()).

        If the write fails (e.g. card removed), the method attempts
        an automatic remount before returning.

        Args:
            payload: Dict with keys vitesse_vent, luminosite,
                     temperature, humidite, pression.
        """
        if not self._montee:
            return  # Pas de SD → on ne fait rien (pas d'exception)

        ts = time.ticks_ms() // 1000

        ligne = (
            f"{ts},"
            f"{payload.get('vitesse_vent', 0)},"
            f"{payload.get('luminosite', 0)},"
            f"{payload.get('temperature', 0)},"
            f"{payload.get('humidite', 0)},"
            f"{payload.get('pression', 0)}\n"
        )

        try:
            with open(self._chemin_complet, "a") as f:
                f.write(ligne)
            print(f"💾 [SD] Données écrites → {ligne.strip()}")
        except Exception as e:
            print(f"❌ [SD] Erreur d'écriture : {e}")
        """True if the SD card is mounted and ready for writing."""
            self._montee = False
            self._tenter_montage()

    # ------------------------------------------------------------------
    # UTILITAIRES
    # ------------------------------------------------------------------
    @property
    def disponible(self) -> bool:
        """Retourne True si la carte SD est opérationnelle."""
        return self._montee
