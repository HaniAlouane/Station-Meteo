"""
main.py — Weather Station firmware for Raspberry Pi Pico W
===========================================================
Collects data from 4 sensors every 12 seconds and routes it
to up to 3 simultaneous output channels:

    1. USB serial  -> Node-RED (wired, highest priority)
    2. Wi-Fi/MQTT  -> Adafruit IO cloud dashboard
    3. SPI         -> micro-SD card (CSV log, always on)

The OLED display (SSD1306 128x32) stays off by default to save
power and wakes up only on button press:
    - Short press  (<1 s)  : slide show of the 5 latest sensor readings
    - Long press   (>=1 s) : system diagnostic page (SD / Wi-Fi / cloud)
    - Extra long   (>=5 s) : sensor error detail page

LED behaviour
-------------
    Blue   GP13  Wi-Fi:       1 x 0.5 s blink every cycle when connected
    Yellow GP14  Node-RED:    1 x 0.5 s blink every cycle when NR active
    White  GP10  Adafruit IO: 1 x 0.5 s blink on successful MQTT publish
    Red    GP15  Errors:      1 x 0.5 s blink when a sensor is out of range
                              or when MQTT publish fails
                              (Wi-Fi absent is NOT an error)

Sensor validity ranges
----------------------
    Temperature  : -20.0 to  60.0 deg C
    Humidity     :   0.0 to 100.0 %
    Pressure     : 870.0 to 1085.0 hPa
    Luminosity   :   0.0 to 120000.0 lux
    Wind speed   :   0.0 to 200.0 km/h

Hardware pin mapping
--------------------
    I2C SDA  GP4    I2C SCL  GP5
    ADC wind GP26   ADC temp GP27
    Button   GP6
    LED blue  GP13   LED yellow GP14
    LED white GP10   LED red    GP15
    SD MISO  GP16   SD CS    GP17   SD SCK GP18   SD MOSI GP19

Author : Hani Alouane
"""

import time
import json
import network
import sys
import uselect
from umqtt.simple import MQTTClient
from machine import Pin, I2C, ADC

from secrets     import secrets
from sd_logger   import SDLogger
from anemometre  import CapteurVent
from capteur_bme import CapteurBME280
from capteur_lux import CapteurLumiere
import ssd1306

# ---------------------------------------------------------------------------
# USB / Node-RED detection
# ---------------------------------------------------------------------------
spoll = uselect.poll()
spoll.register(sys.stdin, uselect.POLLIN)

def node_red_a_repondu():
    return bool(spoll.poll(0))

# ---------------------------------------------------------------------------
# LM335 — lecture temperature (moyenne 50 echantillons)
# ---------------------------------------------------------------------------
_adc_lm335 = ADC(Pin(27))

def lire_temperature_lissee(n=50):
    total = sum(_adc_lm335.read_u16() for _ in range(n))
    tension_v = (total / n / 65535) * 3.3
    return round(tension_v / 0.01 - 273.15, 2)

# ---------------------------------------------------------------------------
# Sensor validity ranges
# ---------------------------------------------------------------------------
# Readings outside these bounds trigger the red LED and are logged as errors.
# Wi-Fi being absent is NOT listed here — it is not an error.
PLAGES_VALIDES = {
    "temperature":  (-20.0,    60.0),
    "humidite":     (  0.0,   100.0),
    "pression":     (870.0,  1085.0),
    "luminosite":   (  0.0, 120000.0),
    "vitesse_vent": (  0.0,   200.0),
}

def valider_payload(payload):
    """Return a list of error strings for any reading outside its valid range."""
    erreurs = []
    for cle, (vmin, vmax) in PLAGES_VALIDES.items():
        val = payload.get(cle)
        if val is None:
            erreurs.append(f"{cle}:no data")
        elif not (vmin <= val <= vmax):
            erreurs.append(f"{cle}={val}")
    return erreurs

# ---------------------------------------------------------------------------
# Initialisation des capteurs
# ---------------------------------------------------------------------------
bus_i2c = I2C(0, scl=Pin(5), sda=Pin(4), freq=100_000)

vent = CapteurVent(pin_adc=26)

try:
    climat  = CapteurBME280(bus_i2c)
    BME_OK  = True
except Exception as _e:
    climat  = None
    BME_OK  = False
    print(f"BME280 introuvable : {_e}")

try:
    lumiere = CapteurLumiere(bus_i2c)
    LUX_OK  = True
except Exception as _e:
    lumiere = None
    LUX_OK  = False
    print(f"VEML7700 introuvable : {_e}")

sd = SDLogger()

try:
    oled = ssd1306.SSD1306_I2C(128, 32, bus_i2c, addr=0x3C)
    OLED_OK = True
    oled.poweroff()
except Exception as _e:
    OLED_OK = False
    print(f"OLED introuvable : {_e}")

W, H = 128, 32

# ---------------------------------------------------------------------------
# Fonctions OLED
# ---------------------------------------------------------------------------
def _oled_allumer():
    if OLED_OK:
        oled.poweron()

def _oled_eteindre():
    if OLED_OK:
        oled.poweroff()

def _dessiner_barre(ratio, y=0, height=3):
    if not OLED_OK:
        return
    largeur = int(W * max(0.0, min(1.0, ratio)))
    oled.fill_rect(0, y, W, height, 0)
    if largeur > 0:
        oled.fill_rect(0, y, largeur, height, 1)

def _afficher_mesure_avec_barre(titre, valeur, duree_ms=2000):
    BARRE_H  = 3
    TEXTE_Y1 = 10
    TEXTE_Y2 = 22
    t_debut = time.ticks_ms()
    while True:
        vent.ecouter()
        elapsed = time.ticks_diff(time.ticks_ms(), t_debut)
        if elapsed >= duree_ms:
            break
        ratio = elapsed / duree_ms
        oled.fill(0)
        _dessiner_barre(ratio, y=0, height=BARRE_H)
        oled.text(titre[:21],  0, TEXTE_Y1)
        oled.text(valeur[:21], 0, TEXTE_Y2)
        oled.show()
        time.sleep_ms(30)

# ---------------------------------------------------------------------------
# Shared sensor cache (used by the OLED carousel)
# ---------------------------------------------------------------------------
_dernier_payload = {
    "vitesse_vent": 0.0,
    "luminosite":   0.0,
    "temperature":  0.0,
    "humidite":     0.0,
    "pression":     0.0,
}

# ---------------------------------------------------------------------------
# OLED screen 1 — sensor carousel  (short press)
# ---------------------------------------------------------------------------
def afficher_donnees():
    _oled_allumer()
    p = _dernier_payload
    slides = [
        ("Temperature",  f"{p['temperature']} C"),
        ("Humidite",     f"{p['humidite']} %"),
        ("Pression",     f"{p['pression']} hPa"),
        ("Luminosite",   f"{p['luminosite']} lux"),
        ("Vitesse vent", f"{p['vitesse_vent']} km/h"),
    ]
    for titre, valeur in slides:
        _afficher_mesure_avec_barre(titre, valeur, duree_ms=2000)
    _oled_eteindre()

# ---------------------------------------------------------------------------
# OLED screen 2 — system diagnostic  (long press >= 1 s)
# ---------------------------------------------------------------------------
def afficher_diagnostic():
    _oled_allumer()
    if _node_red_present:
        mode_txt   = "Mode:Node-RED"
        milieu_lbl = "NR"
        milieu_val = "OK"
    elif wlan.isconnected():
        mode_txt   = "Mode:WiFi/ADA"
        milieu_lbl = "ADA"
        milieu_val = "OK" if adafruit_active else "KO"
    else:
        mode_txt   = "Mode: Aucun"
        milieu_lbl = "---"
        milieu_val = "--"

    sd_val   = "OK" if sd.disponible      else "KO"
    wifi_val = "OK" if wlan.isconnected() else "KO"

    t_debut = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t_debut) < 4000:
        vent.ecouter()
        oled.fill(0)
        oled.text(mode_txt[:21], 0, 0)
        oled.hline(0, 11, W, 1)
        oled.text(f"SD:{sd_val}",               0,  20)
        oled.text(f"{milieu_lbl}:{milieu_val}", 44,  20)
        oled.text(f"Wi:{wifi_val}",             88,  20)
        oled.show()
        time.sleep_ms(30)
    _oled_eteindre()

# ---------------------------------------------------------------------------
# OLED screen 3 — error detail  (extra-long press >= 5 s)
# ---------------------------------------------------------------------------
def afficher_erreurs():
    """Show active sensor errors one by one, or 'All OK' if none."""
    _oled_allumer()
    if not _erreurs_actives:
        # No errors — show confirmation for 3 seconds.
        t = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t) < 3000:
            vent.ecouter()
            oled.fill(0)
            oled.text("All systems OK", 0, 4)
            oled.hline(0, 14, W, 1)
            oled.text("No errors", 28, 20)
            oled.show()
            time.sleep_ms(30)
    else:
        # Show each error message for 2 seconds.
        for err in _erreurs_actives:
            t = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), t) < 2000:
                vent.ecouter()
                oled.fill(0)
                oled.text("! ERROR", 0, 0)
                oled.hline(0, 10, W, 1)
                oled.text(err[:21], 0, 14)
                if len(err) > 21:
                    oled.text(err[21:42], 0, 23)
                oled.show()
                time.sleep_ms(30)
    _oled_eteindre()

# ---------------------------------------------------------------------------
# Bouton poussoir — GP6
# ---------------------------------------------------------------------------
bouton             = Pin(6, Pin.IN, Pin.PULL_UP)
_btn_appuye_depuis = None
SEUIL_LONG_MS      = 1000   # >= 1 s -> long press
SEUIL_EXTRA_MS     = 5000   # >= 5 s -> extra-long press (error screen)

def lire_bouton():
    """Return 'court', 'long', 'extra', or '' (no event yet)."""
    global _btn_appuye_depuis
    if bouton.value() == 0:                         # pressed
        if _btn_appuye_depuis is None:
            _btn_appuye_depuis = time.ticks_ms()
    else:                                           # released
        if _btn_appuye_depuis is not None:
            duree = time.ticks_diff(time.ticks_ms(), _btn_appuye_depuis)
            _btn_appuye_depuis = None
            if duree >= SEUIL_EXTRA_MS:
                return 'extra'
            elif duree >= SEUIL_LONG_MS:
                return 'long'
            else:
                return 'court'
    return ''

# ---------------------------------------------------------------------------
# LEDs
# ---------------------------------------------------------------------------
# GP13  blue   Wi-Fi connected     : 1 blink (0.5 s) each 12-s cycle
# GP14  yellow Node-RED active     : 1 blink (0.5 s) each 12-s cycle
# GP10  white  Adafruit IO success : 1 blink (0.5 s) on successful publish
# GP15  red    Sensor error        : 1 blink (0.5 s) on out-of-range value
#                                    or MQTT publish failure
#                                    Wi-Fi absent is NOT an error

led_bleue   = Pin(13, Pin.OUT)
led_jaune   = Pin(14, Pin.OUT)
led_blanche = Pin(10, Pin.OUT)
led_rouge   = Pin(15, Pin.OUT)

def _blink(led):
    """Single 0.5 s blink — same duration for every LED."""
    led.on()
    time.sleep(0.5)
    led.off()

# ---------------------------------------------------------------------------
# Error state
# ---------------------------------------------------------------------------
_erreurs_actives = []   # reset each 12-second cycle

# ---------------------------------------------------------------------------
# Wi-Fi
# ---------------------------------------------------------------------------
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(secrets["ssid"], secrets["pw"])

_dernier_retry_wifi   = time.ticks_ms()
INTERVALLE_RETRY_WIFI = 3_000

def _maintenir_wifi():
    global _dernier_retry_wifi
    now = time.ticks_ms()
    if not wlan.isconnected():
        if time.ticks_diff(now, _dernier_retry_wifi) >= INTERVALLE_RETRY_WIFI:
            _dernier_retry_wifi = now
            print(f"Wi-Fi : tentative vers {secrets['ssid']}...")
            wlan.connect(secrets["ssid"], secrets["pw"])

# ---------------------------------------------------------------------------
# MQTT — Adafruit IO
# ---------------------------------------------------------------------------
_mqtt = None

def _publier_adafruit(payload):
    global _mqtt, adafruit_active
    # Wi-Fi absent is handled silently — not an error, no red LED.
    if not wlan.isconnected():
        _mqtt = None
        adafruit_active = False
        print("Wi-Fi absent — Adafruit IO skipped")
        return
    if _mqtt is None:
        try:
            print("MQTT : connexion...")
            _mqtt = MQTTClient(
                "pico", "io.adafruit.com",
                user=secrets["ada_user"],
                password=secrets["ada_key"],
                port=1883
            )
            _mqtt.connect()
            print("MQTT OK")
        except Exception as e:
            print(f"MQTT connexion echouee : {e}")
            adafruit_active = False
            _mqtt = None
            # MQTT connection failure -> red LED blink + log error
            _erreurs_actives.append(f"MQTT conn:{e}")
            _blink(led_rouge)
            return
    try:
        for cle, valeur in payload.items():
            topic = f"{secrets['ada_user']}/feeds/{cle.replace('_', '-')}"
            _mqtt.publish(topic, str(valeur))
        adafruit_active = True
        print("Adafruit OK")
        _blink(led_blanche)     # White LED: publish succeeded
    except Exception as e:
        print(f"MQTT publish echoue : {e}")
        try:
            _mqtt.disconnect()
        except:
            pass
        _mqtt = None
        adafruit_active = False
        # Publish failure -> red LED blink + log error
        _erreurs_actives.append(f"MQTT pub:{e}")
        _blink(led_rouge)

# ---------------------------------------------------------------------------
# Main loop state
# ---------------------------------------------------------------------------
_dernier_envoi    = time.ticks_ms()
_node_red_present = False
_nr_etait_actif   = False   # True when Node-RED was active on the previous cycle
adafruit_active   = False

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
while True:

    # 0 — Anemometre (priorite maximale, chaque iteration)
    vent.ecouter()

    # 1 — Bouton
    evt = lire_bouton()
    if evt == 'court':
        afficher_donnees()          # short press  : sensor carousel
    elif evt == 'long':
        afficher_diagnostic()       # long press   : system status
    elif evt == 'extra':
        afficher_erreurs()          # extra-long   : error detail

    # 2 — Detection Node-RED
    if node_red_a_repondu():
        sys.stdin.read(1)
        _node_red_present = True
    else:
        if _node_red_present:
            try:
                if _mqtt:
                    _mqtt.disconnect()
            except:
                pass
            adafruit_active   = False
            _mqtt             = None

    # 3 — Maintien Wi-Fi
    _maintenir_wifi()

    # 4 — Acquisition et envoi toutes les 12 secondes
    now = time.ticks_ms()
    if time.ticks_diff(now, _dernier_envoi) >= 12_000:

        # Reset error list for this cycle
        _erreurs_actives.clear()

        # --- Lecture des capteurs ---
        try:
            v_inst, _ = vent.lire_vitesse()
        except Exception as e:
            v_inst = 0.0
            _erreurs_actives.append(f"Vent:{e}")

        try:
            t_lissee = lire_temperature_lissee(50)
        except Exception as e:
            t_lissee = 0.0
            _erreurs_actives.append(f"LM335:{e}")

        if LUX_OK:
            try:
                lux = lumiere.lire()
            except Exception as e:
                lux = 0.0
                _erreurs_actives.append(f"Lux:{e}")
        else:
            lux = 0.0
            _erreurs_actives.append("VEML7700:non connecte")

        if BME_OK:
            try:
                _, press_str, hum_str = climat.lire()
                pression = float(str(press_str).replace('hPa', ''))
                humidite = float(str(hum_str).replace('%', ''))
            except Exception as e:
                pression = 0.0
                humidite = 0.0
                _erreurs_actives.append(f"BME280:{e}")
        else:
            pression = 0.0
            humidite = 0.0
            if "BME280:non connecte" not in _erreurs_actives:
                _erreurs_actives.append("BME280:non connecte")

        payload = {
            "vitesse_vent": round(v_inst, 2),
            "luminosite":   round(lux, 1),
            "temperature":  t_lissee,
            "humidite":     humidite,
            "pression":     pression,
        }

        # --- Validation des plages ---
        # Skip validation for sensors that are already flagged as disconnected
        # to avoid double-counting the same hardware fault.
        cles_a_ignorer = set()
        if not BME_OK:
            cles_a_ignorer.update(["pression", "humidite"])
        if not LUX_OK:
            cles_a_ignorer.add("luminosite")

        for err in valider_payload(payload):
            # err format is "cle=valeur" or "cle:msg" -- extract the key
            cle = err.split("=")[0].split(":")[0]
            if cle not in cles_a_ignorer:
                _erreurs_actives.append(err)

        # Red LED: blink once if any sensor error this cycle
        if _erreurs_actives:
            _blink(led_rouge)

        # Cache for OLED carousel
        _dernier_payload.update(payload)

        # Canal 1 : SD
        sd.enregistrer(payload)

        # Canal 2 : USB -> Node-RED
        # JSON is always printed so Node-RED can read it.
        # Node-RED is "active" only when its heartbeat was received this cycle.
        # If the heartbeat was previously active but is now missing, the red
        # LED blinks to signal the unexpected loss of the connection.
        print(json.dumps(payload))
        if _node_red_present:
            print("Donnees envoyees a Node-RED.")
            _blink(led_jaune)           # Yellow: Node-RED ACK confirmed
        else:
            # Flag as error only if Node-RED was previously active (unexpected loss).
            if _nr_etait_actif:
                _erreurs_actives.append("Node-RED: no ACK")
                _blink(led_rouge)
                print("[ERROR] Node-RED: heartbeat lost")

        # Blue LED: blinks once whenever Wi-Fi is connected, regardless of
        # which output channel is active.
        if wlan.isconnected():
            _blink(led_bleue)

        # Canal 3 : Wi-Fi -> Adafruit IO
        # Skipped entirely when Node-RED is active (Node-RED has priority).
        if _node_red_present:
            adafruit_active = False
            print("Node-RED active — Adafruit IO skipped")
        elif wlan.isconnected():
            _publier_adafruit(payload)
        else:
            adafruit_active = False
            print("Wi-Fi absent — Adafruit IO skipped")

        print(
            f"SD:{'OK' if sd.disponible else 'KO'} "
            f"NR:{'OK' if _node_red_present else '...'} "
            f"WiFi:{'OK' if wlan.isconnected() else '...'} "
            f"ADA:{'OK' if adafruit_active else '...'} "
            f"Errors:{len(_erreurs_actives)}"
        )

        # Track whether Node-RED was active this cycle so we can detect
        # an unexpected loss on the next cycle and blink the red LED.
        _nr_etait_actif   = _node_red_present
        _node_red_present = False
        _dernier_envoi    = now
