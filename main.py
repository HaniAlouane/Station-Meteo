"""
main.py — Weather Station firmware for Raspberry Pi Pico W
===========================================================
Collects data from 4 sensors every 12 seconds and routes it
to up to 3 simultaneous output channels:

    1. USB serial  → Node-RED (wired, highest priority)
    2. Wi-Fi/MQTT  → Adafruit IO cloud dashboard
    3. SPI         → micro-SD card (CSV log, always on)

The OLED display (SSD1306 128×32) stays off by default to save
power and wakes up only on button press:
    - Short press  : slide show of the 5 latest sensor readings
    - Long press   : single diagnostic page (SD / Wi-Fi / cloud status)

Hardware pin mapping
--------------------
    I2C SDA  GP4    I2C SCL  GP5
    ADC wind GP26   ADC temp GP27
    Button   GP6
    LED blue GP13   LED yellow GP14   LED red GP15
    SD MISO  GP16   SD CS    GP17   SD SCK GP18   SD MOSI GP19

Dependencies (must be present on the Pico filesystem)
------------------------------------------------------
    ssd1306.py      MicroPython SSD1306 OLED driver
    sdcard.py       MicroPython SD card SPI driver
    secrets.py      Wi-Fi and Adafruit IO credentials (not committed)
    sd_logger.py    CSV logging helper (this project)
    anemometre.py   Wind speed driver (this project)
    capteur_bme.py  BME280 wrapper (this project)
    capteur_lux.py  VEML7700 wrapper (this project)
"""
import time
import json
import network
import sys
import uselect
from umqtt.simple import MQTTClient
from machine import Pin, I2C, ADC

from secrets   import secrets
from sd_logger import SDLogger

from anemometre  import CapteurVent
from capteur_bme import CapteurBME280
from capteur_lux import CapteurLumiere

import ssd1306

spoll = uselect.poll()
spoll.register(sys.stdin, uselect.POLLIN)


# ---------------------------------------------------------------------------
# USB heartbeat — non-blocking Node-RED detection
# ---------------------------------------------------------------------------
# Register stdin with the poll object so we can check for incoming bytes
# without ever blocking the main loop.
def node_red_a_repondu() -> bool:
    return bool(spoll.poll(0))

_adc_lm335 = ADC(Pin(27))
    """Return True if Node-RED sent at least one byte on USB (non-blocking)."""
def lire_temperature_lissee(n: int = 50) -> float:
    total = sum(_adc_lm335.read_u16() for _ in range(n))
    tension_v = (total / n / 65535) * 3.3
    return round(tension_v / 0.01 - 273.15, 2)


# ---------------------------------------------------------------------------
# LM335 analog temperature — 50-sample moving average
# ---------------------------------------------------------------------------
# Reading a single ADC sample is noisy. Averaging 50 samples takes ~2 ms
# and reduces random electrical noise by a factor of sqrt(50) ≈ 7.
bus_i2c = I2C(0, scl=Pin(5), sda=Pin(4), freq=100_000)
vent    = CapteurVent(pin_adc=26)
climat  = CapteurBME280(bus_i2c)
lumiere = CapteurLumiere(bus_i2c)
sd      = SDLogger()

try:
    oled   = ssd1306.SSD1306_I2C(128, 32, bus_i2c, addr=0x3C)
    OLED_OK = True
    oled.poweroff()          # Éteint dès le départ
except Exception as _e:
    OLED_OK = False
    print(f"⚠️  OLED : {_e}")
    """
    Read the LM335 sensor n times, average the raw ADC values, then
    convert to Celsius.

    LM335 outputs 10 mV per Kelvin, so:
        V = (avg_u16 / 65535) * 3.3
        T_kelvin = V / 0.01
        T_celsius = T_kelvin - 273.15

    Args:
        n: Number of ADC samples to average (default 50).

    Returns:
        Temperature in degrees Celsius, rounded to 2 decimal places.
    """
W, H = 128, 32              # dimensions de l'écran


# ---------------------------------------------------------------------------
# Sensor initialisation
# ---------------------------------------------------------------------------
# All I2C devices share a single bus (BME280 @ 0x76, VEML7700 @ 0x10, OLED @ 0x3C).
def _oled_allumer():
    if OLED_OK: oled.poweron()


# ---------------------------------------------------------------------------
# OLED display — SSD1306 128×32 on I2C
# ---------------------------------------------------------------------------
# The display is powered off immediately after init to save energy.
# It is turned on only during afficher_donnees() and afficher_diagnostic(),
# then powered off again automatically.
def _oled_eteindre():
    if OLED_OK: oled.poweroff()

def _dessiner_barre(ratio: float, y: int = 0, height: int = 3):
    if not OLED_OK: return
    largeur = int(W * max(0.0, min(1.0, ratio)))

    oled.fill_rect(0, y, W, height, 0)
    """Power on the OLED panel."""
    if largeur > 0:
        oled.fill_rect(0, y, largeur, height, 1)

def _afficher_mesure_avec_barre(titre: str, valeur: str, duree_ms: int = 2000):
    BARRE_H = 3       # hauteur barre (px)
    TEXTE_Y1 = 10     # 1re ligne de texte
    TEXTE_Y2 = 22     # 2e ligne de texte (valeur)
    """Power off the OLED panel (pixels off, zero current draw)."""
    t_debut = time.ticks_ms()
    while True:
        vent.ecouter()
        elapsed = time.ticks_diff(time.ticks_ms(), t_debut)
        if elapsed >= duree_ms:
            break


        ratio = elapsed / duree_ms
    """
    Draw a horizontal progress bar across the full screen width.

    Args:
        ratio:  Fill fraction in [0.0, 1.0]. 0 = empty, 1 = full.
        y:      Top-left Y coordinate of the bar in pixels.
        height: Bar thickness in pixels.
    """
        oled.fill(0)
        _dessiner_barre(ratio, y=0, height=BARRE_H)
        oled.text(titre[:21],  0, TEXTE_Y1)
        oled.text(valeur[:21], 0, TEXTE_Y2)
        oled.show()


        time.sleep_ms(30)   # ~33 fps — non bloquant sur le vent (ecouter() en tête)
    """
    Display one sensor slide for duree_ms milliseconds with an animated
    progress bar that fills from left to right as time elapses.

    The anemometer is polled on every frame so no wind pulse is lost
    even while the screen is being updated.

    Layout (128×32 px):
        [===progress bar (3 px)===]   y=0
        titre                         y=10
        valeur                        y=22

    Args:
        titre:    Label text, e.g. "Temperature".
        valeur:   Value text, e.g. "21.4 C".
        duree_ms: Slide display duration in milliseconds.
    """
bouton = Pin(6, Pin.IN, Pin.PULL_UP)
_btn_appuye_depuis = None
SEUIL_LONG_MS      = 1000

def lire_bouton() -> str:

    global _btn_appuye_depuis
    if bouton.value() == 0:                     # appuyé
        if _btn_appuye_depuis is None:
            _btn_appuye_depuis = time.ticks_ms()
    else:                                        # relâché
        if _btn_appuye_depuis is not None:
            duree = time.ticks_diff(time.ticks_ms(), _btn_appuye_depuis)
            _btn_appuye_depuis = None
            return 'long' if duree >= SEUIL_LONG_MS else 'court'
    return ''

_dernier_payload = {
    "vitesse_vent": 0.0, "luminosite": 0.0,
    "temperature":  0.0, "humidite":   0.0, "pression": 0.0,
}


# ---------------------------------------------------------------------------
# Push button — GP6, internal pull-up (pressed = LOW)
# ---------------------------------------------------------------------------
def afficher_donnees():
    _oled_allumer()
    p = _dernier_payload
    slides = [
        ("Temperature",          f"{p['temperature']} C"),
        ("Humidite",             f"{p['humidite']} %"),
        ("Pression",             f"{p['pression']} hPa"),
        ("Luminosite",           f"{p['luminosite']} lux"),
        ("Vitesse vent",         f"{p['vitesse_vent']} km/h"),
    ]
    for titre, valeur in slides:
        _afficher_mesure_avec_barre(titre, valeur, duree_ms=2000)
    _oled_eteindre()

def afficher_diagnostic():
    _oled_allumer()
    """
    Non-blocking button state machine.

    Detects rising edge (release) and classifies the press duration:
        - 'court' : press shorter than SEUIL_LONG_MS
        - 'long'  : press equal to or longer than SEUIL_LONG_MS
        - ''      : no complete press event yet

    Returns:
        One of the three strings above.
    """
    if _node_red_present:
        mode_txt   = "Mode:Node-RED"
        milieu_lbl = "NR"
        milieu_val = "OK" if _node_red_present else "KO"
    elif wlan.isconnected():
        mode_txt   = "Mode:WiFi/ADA"
        milieu_lbl = "ADA"
        milieu_val = "OK" if adafruit_active else "KO"
    else:
        mode_txt   = "Mode: Aucun"
        milieu_lbl = "---"
        milieu_val = "--"


# ---------------------------------------------------------------------------
# Short press — sensor slide show (5 slides × 2 s each)
# ---------------------------------------------------------------------------
# Holds the most recent sensor readings so the display can be updated
# independently from the 12-second acquisition cycle.
    sd_val   = "OK" if sd.disponible        else "KO"
    wifi_val = "OK" if wlan.isconnected()   else "KO"

    t_debut = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t_debut) < 4000:
        vent.ecouter()
    """
    Wake the OLED, cycle through all 5 sensor readings (2 s per slide),
    then power the display off again.
    """
        oled.fill(0)


# ---------------------------------------------------------------------------
# Long press — system diagnostic page (single screen, 4 s)
# ---------------------------------------------------------------------------
# Screen layout (128×32):
#
#   ┌──────────────────────────────┐
#   │ Mode:Node-RED                │  ← active transmission mode   y=0
#   │ ────────────────────────     │  ← separator line             y=11
#   │ SD:OK     NR:OK     Wi:OK   │  ← three status columns       y=20
#   └──────────────────────────────┘
#
# Column positions:   SD x=0   |   NR/ADA x=44   |   Wi-Fi x=88

        oled.text(mode_txt[:21], 0, 0)
    """
    Wake the OLED, display connection status for 4 seconds, then power off.

    Top row shows the active data channel:
        - 'Mode:Node-RED' when USB serial is active
        - 'Mode:WiFi/ADA' when only Wi-Fi is available
        - 'Mode: Aucun'   when neither channel is reachable

    Bottom row shows three independent status flags:
        - SD    : micro-SD card mounted and writable
        - NR/ADA: Node-RED reception confirmed  OR  Adafruit IO last publish status
        - Wi    : Wi-Fi association state
    """
        oled.hline(0, 11, W, 1)

    # Determine which channel label to show in the middle column
        oled.text(f"SD:{sd_val}",          0,  20)
        oled.text(f"{milieu_lbl}:{milieu_val}", 44, 20)
        oled.text(f"Wi:{wifi_val}",        88, 20)

        oled.show()
        time.sleep_ms(30)

    _oled_eteindre()

led_bleue = Pin(13, Pin.OUT)
led_jaune = Pin(14, Pin.OUT)
led_rouge = Pin(15, Pin.OUT)

def led_bleue_ok():
    led_bleue.on(); time.sleep(0.1); led_bleue.off()


# ---------------------------------------------------------------------------
# Status LEDs
# ---------------------------------------------------------------------------
# GP13 blue  — Adafruit IO publish OK (single blink) / error (double blink)
# GP14 yellow — Node-RED data forwarded
# GP15 red    — Wi-Fi or MQTT connection failure (stays on until next cycle)
def led_bleue_erreur():
    for _ in range(2):
        led_bleue.on(); time.sleep(0.1)
        led_bleue.off(); time.sleep(0.1)

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
    """Single 100 ms blue blink — Adafruit publish succeeded."""
_dernier_retry_wifi   = time.ticks_ms()
INTERVALLE_RETRY_WIFI = 3_000

def _maintenir_wifi():
    global _dernier_retry_wifi
    now = time.ticks_ms()
    if not wlan.isconnected():
        if time.ticks_diff(now, _dernier_retry_wifi) >= INTERVALLE_RETRY_WIFI:
            _dernier_retry_wifi = now
            print(f"🔗 [Wi-Fi] Tentative vers {secrets['ssid']} …")
            wlan.connect(secrets["ssid"], secrets["pw"])
    """Double 100 ms blue blink — Wi-Fi or MQTT failure."""
wlan.connect(secrets["ssid"], secrets["pw"])


# ---------------------------------------------------------------------------
# Wi-Fi — persistent background connection
# ---------------------------------------------------------------------------
# wlan.connect() is non-blocking on the Pico W: it starts the association
# process and returns immediately. _maintenir_wifi() is called on every loop
# iteration and retries every INTERVALLE_RETRY_WIFI ms when disconnected,
# so the station never waits idle for a network.
_mqtt = None

def _publier_adafruit(payload: dict):
    global _mqtt, adafruit_active
    if not wlan.isconnected():
        _mqtt = None
        print("📶 Wi-Fi absent")
        led_bleue_erreur(); led_rouge.on()
        return
    if _mqtt is None:
        try:
            print("🔌 [MQTT] connexion...")
            _mqtt = MQTTClient(
                "pico", "io.adafruit.com",
                user=secrets["ada_user"],
                password=secrets["ada_key"],
                port=1883
            )
            _mqtt.connect()
            print("✅ MQTT OK")
        except Exception as e:
            print("❌ MQTT connect :", e)
            adafruit_active = False; _mqtt = None
            led_bleue_erreur(); led_rouge.on()
            return
    try:
        for cle, valeur in payload.items():
            topic = f"{secrets['ada_user']}/feeds/{cle.replace('_','-')}"
            _mqtt.publish(topic, str(valeur))
        adafruit_active = True
        print("🚀 Adafruit OK")
        led_bleue_ok()
    except Exception as e:
        print("❌ MQTT publish :", e)
        try: _mqtt.disconnect()
        except: pass
        _mqtt = None

_dernier_envoi    = time.ticks_ms()
_node_red_present = False
adafruit_active   = False
    """
    Attempt to (re)connect to the configured SSID if the link is down.
    Called on every main loop iteration; never blocks.
    """
while True:

# Trigger an immediate connection attempt at boot
    vent.ecouter()


# ---------------------------------------------------------------------------
# MQTT — Adafruit IO cloud publishing
# ---------------------------------------------------------------------------
# The client object is created lazily on first use and reset to None on any
# error, so the next call to _publier_adafruit() will reconnect automatically.
    evt = lire_bouton()
    if evt == 'court':
        afficher_donnees()          # écran s'allume puis s'éteint seul
    elif evt == 'long':
        afficher_diagnostic()       # idem

    if node_red_a_repondu():
        sys.stdin.read(1)
        _node_red_present = True
    else:
        if _node_red_present:
            try:
                if _mqtt: _mqtt.disconnect()
            except: pass
            adafruit_active   = False
            _mqtt             = None
    """
    Publish every key in payload to its corresponding Adafruit IO feed.

    Feed naming convention: underscores in dict keys are replaced with
    hyphens to match Adafruit IO feed slugs (e.g. 'vitesse_vent' →
    '<user>/feeds/vitesse-vent').

    Sets the module-level adafruit_active flag to True on success,
    or resets _mqtt to None on failure so the next call reconnects.

    Args:
        payload: Dict of {feed_name: numeric_value} to publish.
    """
    _maintenir_wifi()

    now = time.ticks_ms()
    if time.ticks_diff(now, _dernier_envoi) >= 12_000:

    # (Re)create the MQTT client if it was never created or was reset after an error
        v_inst, _             = vent.lire_vitesse()
        t_lissee              = lire_temperature_lissee(50)
        lux                   = lumiere.lire()
        _, press_str, hum_str = climat.lire()

        payload = {
            "vitesse_vent": round(v_inst, 2),
            "luminosite":   round(lux, 1),
            "temperature":  t_lissee,
            "humidite":     float(str(hum_str).replace('%',   '')),
            "pression":     float(str(press_str).replace('hPa', '')),
        }


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
        _dernier_payload.update(payload)

        sd.enregistrer(payload)

    # 0 — WIND PULSE COUNTER (highest priority, called on every iteration)
    #     Must never be skipped; missing a pulse causes a wrong speed reading.
        print(json.dumps(payload))
        if _node_red_present:
            print("📨 [USB] Données reçues par Node-RED.")
            led_jaune.on(); time.sleep(0.05); led_jaune.off()

    # 1 — BUTTON
    #     lire_bouton() is a non-blocking state machine; it only returns a
    #     non-empty string on the rising edge (button release).
        if wlan.isconnected():
            _publier_adafruit(payload)
        else:
            adafruit_active = False
            print("📶 [Adafruit] Wi-Fi absent — prochain essai dans 3 s.")

    # 2 — NODE-RED DETECTION (continuous, non-blocking)
    #     Node-RED periodically sends a single byte as a heartbeat.
    #     If the flag was True but no byte arrives this iteration,
    #     the USB link has dropped: reset MQTT so Adafruit IO takes over.
        print(
            f"📊 SD:{'✅' if sd.disponible else '❌'} "
            f"NR:{'✅' if _node_red_present else '⏳'} "
            f"WiFi:{'✅' if wlan.isconnected() else '⏳'} "
            f"ADA:{'✅' if adafruit_active else '⏳'}"
        )

    # 3 — WI-FI MAINTENANCE (non-blocking, retries every 3 s)
        _node_red_present = False
        _dernier_envoi    = now
