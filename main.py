"""
main.py
=======
Core firmware for a DIY weather station built on the Raspberry Pi Pico W.

Every 12 seconds, the station reads four sensors and pushes the data to up
to three simultaneous output channels, chosen automatically based on what
is currently available:

    1. USB serial   ->  Node-RED dashboard (highest priority, wired)
    2. Wi-Fi / MQTT ->  Adafruit IO cloud  (fallback when USB is absent)
    3. SPI          ->  micro-SD card CSV  (always active, unconditional)

The SSD1306 OLED display (128x32 px) stays powered off by default to
minimise current draw.  It wakes up on button press and powers itself
off again after the animation finishes:

    Short press  (<1 s)  ->  5-slide sensor carousel, 2 s per slide,
                              with an animated progress bar at the top.
    Long press   (>=1 s) ->  single diagnostic screen showing the state
                              of the SD card, the Node-RED link, and Wi-Fi.

Hardware wiring summary
-----------------------
    I2C bus 0   SDA  -> GP4   |   SCL  -> GP5      (BME280, VEML7700, OLED)
    Anemometer  ADC0 -> GP26
    LM335 temp  ADC1 -> GP27  (pull-up resistor 2.2 kOhm to 5 V)
    Push button       -> GP6   (internal pull-up, active LOW)
    LED blue          -> GP13  (Adafruit IO status)
    LED yellow        -> GP14  (Node-RED status)
    LED red           -> GP15  (Wi-Fi / MQTT error)
    SD MISO           -> GP16  |   SD CS   -> GP17
    SD SCK            -> GP18  |   SD MOSI -> GP19

Dependencies
------------
    ssd1306.py       Official MicroPython SSD1306 OLED driver
    sdcard.py        Official MicroPython SPI SD-card driver
    secrets.py       Wi-Fi and Adafruit IO credentials  (not committed)
    sd_logger.py     Append-only CSV logger             (this project)
    anemometre.py    Cup anemometer pulse driver         (this project)
    capteur_bme.py   BME280 wrapper                     (this project)
    capteur_lux.py   VEML7700 lux wrapper               (this project)

Author : Hani AL
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
# USB / Node-RED heartbeat detection
# ---------------------------------------------------------------------------
# Node-RED periodically sends a single byte over the USB-serial link as a
# heartbeat signal.  We register stdin with uselect.poll() so we can check
# for incoming bytes without ever blocking the main loop.  A blocking read
# (e.g. sys.stdin.read()) would stall the anemometer polling and cause
# missed wind pulses.

spoll = uselect.poll()
spoll.register(sys.stdin, uselect.POLLIN)


def node_red_a_repondu() -> bool:
    """Return True if Node-RED sent at least one byte on the USB link.

    The poll timeout is 0 ms, so this call always returns immediately.
    It does NOT consume the byte; the caller must call sys.stdin.read(1)
    to drain it from the buffer.
    """
    return bool(spoll.poll(0))


# ---------------------------------------------------------------------------
# LM335 analogue temperature sensor  (GP27 / ADC1)
# ---------------------------------------------------------------------------
# The LM335 outputs exactly 10 mV per kelvin, so:
#
#       V_adc   = (raw_u16 / 65535) * 3.3          [volts]
#       T_kelvin = V_adc / 0.01                     [kelvin]
#       T_celsius = T_kelvin - 273.15               [degrees C]
#
# Note: the sensor is powered from the 5 V VBUS rail through a 2.2 kOhm
# pull-up resistor.  The reading point (junction of resistor and sensor
# anode) is connected to GP27.  Because the Pico ADC reference is 3.3 V,
# the formula above uses 3.3 V as the reference even though the supply
# rail is 5 V.  This is correct: the ADC saturates at 3.3 V, and the
# operating point of the LM335 at room temperature (~300 K) gives roughly
# 3.0 V, which stays safely within range.
#
# Noise reduction: the Pico W ADC is affected by switching noise from the
# on-board voltage regulator and the Wi-Fi radio.  Averaging N samples
# reduces the standard deviation by a factor of sqrt(N).  We use N=50,
# which gives a noise reduction of ~x7 compared with a single sample,
# at a cost of roughly 2-3 ms of CPU time.

_adc_lm335 = ADC(Pin(27))


def lire_temperature_lissee(n: int = 50) -> float:
    """Read the LM335 temperature sensor and return an averaged result.

    Accumulates `n` raw 16-bit ADC samples, converts the average voltage
    to degrees Celsius using the LM335 transfer function, and returns the
    result rounded to two decimal places.

    Args:
        n (int): Number of ADC samples to average.  Default is 50.

    Returns:
        float: Temperature in degrees Celsius, rounded to 2 d.p.
    """
    total = sum(_adc_lm335.read_u16() for _ in range(n))
    tension_v = (total / n / 65535) * 3.3
    return round(tension_v / 0.01 - 273.15, 2)


# ---------------------------------------------------------------------------
# Sensor and peripheral initialisation
# ---------------------------------------------------------------------------
# All three I2C devices (BME280, VEML7700, OLED) share a single I2C bus
# running at 100 kHz.  This is well below the 400 kHz fast-mode limit but
# is stable across long breadboard wires and mixed supply voltages.

bus_i2c = I2C(0, scl=Pin(5), sda=Pin(4), freq=100_000)

# Wind speed sensor: reads analogue pulses on ADC0 (GP26).
vent = CapteurVent(pin_adc=26)

# BME280: pressure and relative humidity over I2C at address 0x76.
# Temperature from this sensor is intentionally discarded in favour of
# the more accurate LM335 outdoor reading.
climat = CapteurBME280(bus_i2c)

# VEML7700: ambient light sensor over I2C at address 0x10.
lumiere = CapteurLumiere(bus_i2c)

# SD card logger: mounts a FAT32 micro-SD card over SPI and writes a
# CSV row every acquisition cycle.  Failures are handled silently inside
# SDLogger so the rest of the firmware is unaffected if the card is absent.
sd = SDLogger()


# ---------------------------------------------------------------------------
# OLED display  (SSD1306 128x32, I2C address 0x3C)
# ---------------------------------------------------------------------------
# The display is initialised at boot but immediately powered off to save
# energy.  OLED_OK acts as a guard flag: if initialisation fails (e.g. the
# display is not connected), every drawing function checks this flag and
# returns early so the firmware keeps running without the screen.

try:
    oled = ssd1306.SSD1306_I2C(128, 32, bus_i2c, addr=0x3C)
    OLED_OK = True
    oled.poweroff()                     # Screen off immediately after init
except Exception as _e:
    OLED_OK = False
    print(f"OLED not found: {_e}")

# Screen dimensions in pixels, used throughout drawing functions.
W, H = 128, 32


def _oled_allumer():
    """Power on the OLED panel (pixels active)."""
    if OLED_OK:
        oled.poweron()


def _oled_eteindre():
    """Power off the OLED panel (zero current draw from the display)."""
    if OLED_OK:
        oled.poweroff()


def _dessiner_barre(ratio: float, y: int = 0, height: int = 3):
    """Draw a horizontal progress bar across the full screen width.

    The bar fills from left to right proportionally to `ratio`.
    The background region is always cleared first so the bar can shrink
    as well as grow (useful if this function is called in a loop).

    Args:
        ratio  (float): Fill fraction in [0.0, 1.0].
        y      (int):   Top-left Y coordinate of the bar in pixels.
        height (int):   Thickness of the bar in pixels.
    """
    if not OLED_OK:
        return
    # Clamp ratio to [0, 1] and convert to pixel width.
    largeur = int(W * max(0.0, min(1.0, ratio)))
    oled.fill_rect(0, y, W, height, 0)     # Clear the bar background
    if largeur > 0:
        oled.fill_rect(0, y, largeur, height, 1)   # Draw filled portion


def _afficher_mesure_avec_barre(titre: str, valeur: str, duree_ms: int = 2000):
    """Display one sensor slide with a live progress bar for `duree_ms` ms.

    The slide layout on the 128x32 screen is:

        y=0   [========= progress bar (3 px) =========]
        y=10  titre   (e.g. "Temperature")
        y=22  valeur  (e.g. "21.4 C")

    The anemometer is polled on every frame (~33 fps) so no wind pulse
    is missed while the display is being refreshed.

    Args:
        titre    (str): Sensor label, truncated to 21 characters if needed.
        valeur   (str): Sensor value string, truncated to 21 characters.
        duree_ms (int): Slide display duration in milliseconds.
    """
    BARRE_H  = 3    # Progress bar height in pixels
    TEXTE_Y1 = 10   # Y position of the label row
    TEXTE_Y2 = 22   # Y position of the value row

    t_debut = time.ticks_ms()
    while True:
        vent.ecouter()                              # Keep sampling the wind sensor
        elapsed = time.ticks_diff(time.ticks_ms(), t_debut)
        if elapsed >= duree_ms:
            break

        ratio = elapsed / duree_ms                  # Progress: 0.0 -> 1.0

        oled.fill(0)
        _dessiner_barre(ratio, y=0, height=BARRE_H)
        oled.text(titre[:21],  0, TEXTE_Y1)
        oled.text(valeur[:21], 0, TEXTE_Y2)
        oled.show()

        time.sleep_ms(30)                           # ~33 fps refresh rate


# ---------------------------------------------------------------------------
# OLED screen 1 — sensor carousel  (short button press)
# ---------------------------------------------------------------------------

# Shared dict updated every 12-second acquisition cycle.
# Initialised to zero so the display always has valid data to show,
# even before the first measurement completes.
_dernier_payload = {
    "vitesse_vent": 0.0,
    "luminosite":   0.0,
    "temperature":  0.0,
    "humidite":     0.0,
    "pression":     0.0,
}


def afficher_donnees():
    """Wake the OLED and cycle through all five sensor readings.

    Each slide is displayed for 2 seconds with an animated progress bar.
    The display is powered off automatically at the end of the carousel.
    """
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
# OLED screen 2 — system diagnostic  (long button press)
# ---------------------------------------------------------------------------

def afficher_diagnostic():
    """Wake the OLED and show the system status screen for 4 seconds.

    Screen layout (128x32 px):

        +------------------------------+
        |  Mode:Node-RED               |  <- active channel label  (y=0)
        |  ----------------------------+  <- separator line         (y=11)
        |  SD:OK    NR:OK    Wi:OK    |  <- three status columns   (y=20)
        +------------------------------+

    Column positions:
        x=0   SD card status
        x=44  Node-RED (NR) or Adafruit IO (ADA) status
        x=88  Wi-Fi (Wi) status

    The active channel label changes depending on what is reachable:
        'Mode:Node-RED'  when the USB heartbeat is present
        'Mode:WiFi/ADA'  when only Wi-Fi is available
        'Mode: Aucun'    when neither channel is reachable
    """
    _oled_allumer()

    # Determine which data channel is currently active.
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

    sd_val   = "OK" if sd.disponible      else "KO"
    wifi_val = "OK" if wlan.isconnected() else "KO"

    # Hold the diagnostic screen for 4 seconds while still polling the wind sensor.
    t_debut = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t_debut) < 4000:
        vent.ecouter()

        oled.fill(0)
        oled.text(mode_txt[:21], 0, 0)
        oled.hline(0, 11, W, 1)                             # Horizontal separator
        oled.text(f"SD:{sd_val}",                0, 20)
        oled.text(f"{milieu_lbl}:{milieu_val}", 44, 20)
        oled.text(f"Wi:{wifi_val}",             88, 20)
        oled.show()
        time.sleep_ms(30)

    _oled_eteindre()


# ---------------------------------------------------------------------------
# Push button  (GP6, internal pull-up, pressed = LOW)
# ---------------------------------------------------------------------------
# A state machine tracks how long the button has been held down.
# The event is only reported on the *rising edge* (button release), which
# avoids triggering both a short and a long event during the same press.

bouton             = Pin(6, Pin.IN, Pin.PULL_UP)
_btn_appuye_depuis = None           # ticks_ms() timestamp of the press start
SEUIL_LONG_MS      = 1000           # Threshold between short and long press (ms)


def lire_bouton() -> str:
    """Non-blocking button state machine.

    Must be called on every main loop iteration to achieve accurate timing.

    Returns:
        str: 'court' on a short press release,
             'long'  on a long press release  (>= SEUIL_LONG_MS),
             ''      when no complete press event has occurred yet.
    """
    global _btn_appuye_depuis
    if bouton.value() == 0:                         # Button is pressed (LOW)
        if _btn_appuye_depuis is None:
            _btn_appuye_depuis = time.ticks_ms()    # Record start of press
    else:                                           # Button released (HIGH)
        if _btn_appuye_depuis is not None:
            duree = time.ticks_diff(time.ticks_ms(), _btn_appuye_depuis)
            _btn_appuye_depuis = None
            return 'long' if duree >= SEUIL_LONG_MS else 'court'
    return ''


# ---------------------------------------------------------------------------
# Status LEDs
# ---------------------------------------------------------------------------
# GP13  blue   - Adafruit IO: 1 blink = publish OK, 2 blinks = error
# GP14  yellow - Node-RED:    blinks once per successful USB transmission
# GP15  red    - Wi-Fi/MQTT error: stays ON until the next successful cycle

led_bleue = Pin(13, Pin.OUT)
led_jaune = Pin(14, Pin.OUT)
led_rouge = Pin(15, Pin.OUT)


def led_bleue_ok():
    """Single 100 ms blue blink: Adafruit IO publish succeeded."""
    led_bleue.on()
    time.sleep(0.1)
    led_bleue.off()


def led_bleue_erreur():
    """Double 100 ms blue blink: Wi-Fi connection or MQTT publish failed."""
    for _ in range(2):
        led_bleue.on()
        time.sleep(0.1)
        led_bleue.off()
        time.sleep(0.1)


# ---------------------------------------------------------------------------
# Wi-Fi  (persistent background connection)
# ---------------------------------------------------------------------------
# wlan.connect() on the Pico W is non-blocking: it starts the association
# process and returns immediately.  _maintenir_wifi() is called on every
# main loop iteration and retries every INTERVALLE_RETRY_WIFI ms whenever
# the link is down, so the station reconnects automatically after a dropout
# without ever halting the sensor acquisition loop.

wlan = network.WLAN(network.STA_IF)
wlan.active(True)

_dernier_retry_wifi   = time.ticks_ms()
INTERVALLE_RETRY_WIFI = 3_000       # Retry interval in ms when disconnected


def _maintenir_wifi():
    """Attempt a reconnection if the Wi-Fi link has dropped.

    This function is non-blocking: it returns immediately regardless of
    whether the connection attempt succeeds.  Retries are throttled to
    once per INTERVALLE_RETRY_WIFI milliseconds.
    """
    global _dernier_retry_wifi
    now = time.ticks_ms()
    if not wlan.isconnected():
        if time.ticks_diff(now, _dernier_retry_wifi) >= INTERVALLE_RETRY_WIFI:
            _dernier_retry_wifi = now
            print(f"[Wi-Fi] Connecting to {secrets['ssid']} ...")
            wlan.connect(secrets["ssid"], secrets["pw"])


# Trigger an immediate connection attempt at boot so we don't have to wait
# for the first INTERVALLE_RETRY_WIFI timeout to expire.
wlan.connect(secrets["ssid"], secrets["pw"])


# ---------------------------------------------------------------------------
# MQTT / Adafruit IO cloud publishing
# ---------------------------------------------------------------------------
# The MQTTClient object is created lazily on the first publish call and is
# reset to None on any error.  This means the next call to
# _publier_adafruit() will reconnect automatically without any explicit
# retry logic in the main loop.
#
# Feed naming convention: dict keys use underscores (e.g. 'vitesse_vent'),
# but Adafruit IO feed slugs use hyphens.  The replace() call handles this.

_mqtt = None


def _publier_adafruit(payload: dict):
    """Publish all sensor readings to the corresponding Adafruit IO feeds.

    If the Wi-Fi link is down the function returns early and signals the
    error via the LEDs.  If the MQTT client is not connected it is created
    and connected first.  Any exception during publishing resets the client
    to None so that the next call reconnects from scratch.

    Args:
        payload (dict): Sensor readings keyed by feed name
                        (e.g. {'vitesse_vent': 2.3, 'temperature': 21.4, ...}).
    """
    global _mqtt, adafruit_active

    # Guard: no Wi-Fi, no MQTT.
    if not wlan.isconnected():
        _mqtt = None
        print("[MQTT] Wi-Fi not connected")
        led_bleue_erreur()
        led_rouge.on()
        return

    # Lazily create and connect the MQTT client if needed.
    if _mqtt is None:
        try:
            print("[MQTT] Connecting to Adafruit IO ...")
            _mqtt = MQTTClient(
                "pico",
                "io.adafruit.com",
                user=secrets["ada_user"],
                password=secrets["ada_key"],
                port=1883,
            )
            _mqtt.connect()
            print("[MQTT] Connected")
        except Exception as e:
            print(f"[MQTT] Connection failed: {e}")
            adafruit_active = False
            _mqtt = None
            led_bleue_erreur()
            led_rouge.on()
            return

    # Publish each key-value pair to its individual feed.
    try:
        for cle, valeur in payload.items():
            topic = f"{secrets['ada_user']}/feeds/{cle.replace('_', '-')}"
            _mqtt.publish(topic, str(valeur))
        adafruit_active = True
        print("[MQTT] Publish OK")
        led_bleue_ok()
    except Exception as e:
        print(f"[MQTT] Publish failed: {e}")
        try:
            _mqtt.disconnect()
        except Exception:
            pass
        _mqtt = None


# ---------------------------------------------------------------------------
# Main loop state
# ---------------------------------------------------------------------------

_dernier_envoi    = time.ticks_ms()    # Timestamp of the last 12-second cycle
_node_red_present = False              # True when USB heartbeat is active
adafruit_active   = False              # True after a successful MQTT publish


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
# The loop runs as fast as possible (no global sleep) so that:
#   - The anemometer is sampled on every iteration (wind pulses must not
#     be missed, especially at high wind speeds).
#   - The button state machine has millisecond-level timing accuracy.
#   - The Node-RED heartbeat is detected without delay.
#
# Time-based tasks (sensor acquisition, Wi-Fi retry) use ticks_diff()
# comparisons instead of sleep() calls so they never block the loop.

while True:

    # Step 0 — Wind sensor (highest priority, every iteration)
    # -------------------------------------------------------------------------
    # ecouter() reads the ADC and updates the internal pulse timestamp.
    # Missing a call here can cause a wrong speed reading on the next cycle.
    vent.ecouter()

    # Step 1 — Button event
    # -------------------------------------------------------------------------
    # lire_bouton() is a non-blocking state machine.  It only returns a
    # non-empty string on the rising edge (button release), never during
    # the press itself.
    evt = lire_bouton()
    if evt == 'court':
        afficher_donnees()          # Short press: sensor carousel
    elif evt == 'long':
        afficher_diagnostic()       # Long press: system status screen

    # Step 2 — Node-RED heartbeat detection
    # -------------------------------------------------------------------------
    # Node-RED sends one byte per cycle as a keep-alive.  If the flag was
    # True on the previous iteration but no byte arrived this time, the USB
    # link has dropped: reset the MQTT client so Adafruit IO takes over as
    # the active output channel.
    if node_red_a_repondu():
        sys.stdin.read(1)           # Drain the heartbeat byte from the buffer
        _node_red_present = True
    else:
        if _node_red_present:
            try:
                if _mqtt:
                    _mqtt.disconnect()
            except Exception:
                pass
            adafruit_active   = False
            _mqtt             = None

    # Step 3 — Wi-Fi maintenance
    # -------------------------------------------------------------------------
    _maintenir_wifi()

    # Step 4 — 12-second acquisition and publishing cycle
    # -------------------------------------------------------------------------
    now = time.ticks_ms()
    if time.ticks_diff(now, _dernier_envoi) >= 12_000:

        # --- Read all sensors ---
        v_inst, _             = vent.lire_vitesse()
        t_lissee              = lire_temperature_lissee(50)
        lux                   = lumiere.lire()
        _, press_str, hum_str = climat.lire()

        # Build the unified payload dict shared by all output channels.
        # BME280 returns strings with units ('hPa', '%'); strip them here.
        payload = {
            "vitesse_vent": round(v_inst, 2),
            "luminosite":   round(lux, 1),
            "temperature":  t_lissee,
            "humidite":     float(str(hum_str).replace('%',   '')),
            "pression":     float(str(press_str).replace('hPa', '')),
        }

        # Cache the payload so the OLED carousel always has fresh data.
        _dernier_payload.update(payload)

        # Channel 1: SD card (always attempted, failure is silently swallowed)
        sd.enregistrer(payload)

        # Channel 2: USB serial -> Node-RED
        # The JSON is always printed so Node-RED can parse it.
        # The yellow LED blinks only when Node-RED has confirmed its presence
        # via the heartbeat mechanism.
        print(json.dumps(payload))
        if _node_red_present:
            print("[USB] Data forwarded to Node-RED")
            led_jaune.on()
            time.sleep(0.05)
            led_jaune.off()

        # Channel 3: Wi-Fi -> Adafruit IO MQTT
        if wlan.isconnected():
            _publier_adafruit(payload)
        else:
            adafruit_active = False
            print("[Wi-Fi] Not connected, will retry in 3 s")

        # Print a one-line status summary for serial monitoring.
        print(
            f"[STATUS] "
            f"SD:{'OK' if sd.disponible else 'KO'}  "
            f"NR:{'OK' if _node_red_present else '--'}  "
            f"WiFi:{'OK' if wlan.isconnected() else '--'}  "
            f"ADA:{'OK' if adafruit_active else '--'}"
        )

        # Reset the Node-RED flag: it must be refreshed every cycle by a
        # fresh heartbeat byte, otherwise the station falls back to Wi-Fi.
        _node_red_present = False
        _dernier_envoi    = now
