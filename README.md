# 🌦️ Station Météo Connectée — Raspberry Pi Pico W

> A fully autonomous connected weather station built from scratch on the Raspberry Pi Pico W.
> Measures wind speed, temperature, pressure, humidity and ambient light — logged to SD card,
> streamed to Node-RED, and published live to the Adafruit IO cloud dashboard.

<br>

![MicroPython](https://img.shields.io/badge/MicroPython-1.23-2b5ea7?style=for-the-badge&logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%20Pico%20W-c51a4a?style=for-the-badge&logo=raspberrypi&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Active-22c55e?style=for-the-badge)

---

## 📑 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Hardware](#-hardware)
- [Wiring](#-wiring)
- [Software Architecture](#-software-architecture)
- [Getting Started](#-getting-started)
- [Output Channels](#-output-channels)
- [File Structure](#-file-structure)
- [Third-Party Libraries](#-third-party-libraries)
- [Author](#-author)

---

## 🔭 Overview

This project is an L3 SPI academic project consisting of a fully autonomous
outdoor weather station based on the **Raspberry Pi Pico W** microcontroller
and programmed in **MicroPython**.

The station acquires five meteorological measurements every 12 seconds and
routes the data simultaneously to three independent output channels, selected
automatically based on what is currently available:

| Priority | Channel | Condition |
|----------|---------|-----------|
| 1 | USB serial → Node-RED | USB cable connected and Node-RED active |
| 2 | Wi-Fi → Adafruit IO MQTT | Wi-Fi available, Node-RED absent |
| 3 | SPI → micro-SD card CSV | Always active, unconditional |

The SSD1306 OLED display stays powered off by default to minimise current
draw and wakes up only on button press.

---

## ✨ Features

- **5 sensors** — wind speed, outdoor temperature, pressure, humidity, ambient light
- **3 simultaneous output channels** — SD card, Node-RED, Adafruit IO cloud
- **Automatic channel switching** — falls back from USB to Wi-Fi seamlessly
- **Non-blocking main loop** — anemometer is sampled on every iteration, no missed pulses
- **OLED display** — powers on demand only, with animated progress bar
- **3 status LEDs** — real-time feedback on SD, Wi-Fi and cloud status
- **Auto SD remount** — recovers silently if the card is briefly disconnected
- **50-sample ADC oversampling** — reduces LM335 noise by a factor of √50 ≈ 7×
- **Fail-silent design** — any missing peripheral is gracefully skipped

---

## 🔩 Hardware

### Bill of Materials

| Component | Model | Interface | Notes |
|-----------|-------|-----------|-------|
| Microcontroller | Raspberry Pi Pico W | — | Wi-Fi onboard |
| Pressure / Humidity | BME280 | I2C `0x76` | Blue/violet breakout |
| Ambient light | VEML7700 | I2C `0x10` | STEMMA QT port |
| OLED display | SSD1306 128×32 | I2C `0x3C` | 4-wire Dupont |
| Temperature | LM335 (TO-92) | ADC GP27 | 2.2 kΩ pull-up to 5 V |
| Wind speed | Cup anemometer | ADC GP26 | Hall / reed sensor |
| SD card module | FAT32 micro-SD | SPI bus 0 | 3.3 V compatible |
| Push button | Tactile 4-pin | GP6 | Internal pull-up |
| LED blue | 5 mm standard | GP13 | 220 Ω series resistor |
| LED yellow | 5 mm standard | GP14 | 220 Ω series resistor |
| LED red | 5 mm standard | GP15 | 220 Ω series resistor |
| Resistor | 2.2 kΩ | — | LM335 bias |
| Resistors | 220 Ω × 3 | — | LED current limiting |

---

## 🔌 Wiring

### I2C Bus (GP4 / GP5)

All three I2C devices share a single bus at 100 kHz.

```
Pico W  ──── JST-SH STEMMA cable ──►  VEML7700 (0x10)
                                            │
                                   JST-SH STEMMA QT cable
                                            │
                                            ▼
                                       BME280 (0x76)

Pico W  ──── 4× Dupont M-F ──────────►  SSD1306 OLED (0x3C)
              GP4 → SDA
              GP5 → SCL
              3V3 → VCC
              GND → GND
```

### LM335 Temperature Sensor (ADC1 / GP27)

```
5V (VBUS) ──── [2.2 kΩ] ──── node A ──── patte(+) LM335 ──── GND
                                  │
                                 GP27
```

> The ADJ (centre) pin is left unconnected. Only the (+) anode and (−) cathode are wired.

### SPI — micro-SD Card (Bus 0)

| SD pin | Pico W pin | GPIO |
|--------|-----------|------|
| MISO | Pin 21 | GP16 |
| CS | Pin 22 | GP17 |
| SCK | Pin 24 | GP18 |
| MOSI | Pin 25 | GP19 |
| VCC | 3.3 V | — |
| GND | GND | — |

### GPIO — LEDs and Button

| Component | GPIO | Pin | Mode | Role |
|-----------|------|-----|------|------|
| LED blue | GP13 | 17 | OUT | Adafruit IO: 1 blink = OK, 2 = error |
| LED yellow | GP14 | 19 | OUT | Node-RED: blinks on each transmission |
| LED red | GP15 | 20 | OUT | Wi-Fi / MQTT error (stays on) |
| Push button | GP6 | 9 | IN + pull-up | Short / long press detection |

> Each LED is wired: GPIO → 220 Ω → anode (+) → cathode (−) → GND.
> The button is wired between GP6 and GND. No external resistor needed.

### Power

| Rail | Source | Pin |
|------|--------|-----|
| 5 V | VBUS (USB) | Pin 40 |
| 3.3 V | 3V3(OUT) regulator | Pin 36 |
| GND | GND | Pins 3 & 38 |

---

## 🏗️ Software Architecture

```
main.py
├── USB / Node-RED heartbeat detection     (uselect.poll, non-blocking)
├── LM335 temperature                      (ADC oversampling, 50 samples)
├── Sensor initialisation
│   ├── CapteurVent       ← anemometre.py
│   ├── CapteurBME280     ← capteur_bme.py  →  bme280.py
│   ├── CapteurLumiere    ← capteur_lux.py  →  veml7700.py
│   └── SDLogger          ← sd_logger.py    →  sdcard.py
├── OLED display (SSD1306)                 ← ssd1306.py
├── Push button state machine              (non-blocking, ticks_diff)
├── Status LEDs
├── Wi-Fi persistent connection            (non-blocking retry every 3 s)
├── MQTT / Adafruit IO publisher           (lazy connect, auto-reconnect)
└── Main loop  (12-second acquisition cycle)
    ├── Step 0  Wind sensor polling        (every iteration, highest priority)
    ├── Step 1  Button event handling
    ├── Step 2  Node-RED heartbeat check
    ├── Step 3  Wi-Fi maintenance
    └── Step 4  Sensor read + publish      (every 12 s)
```

### Main Loop Design

The loop runs as fast as possible with **no global `sleep()`** call. All
time-based tasks use `ticks_diff()` comparisons so they never block the
anemometer polling. At high wind speeds, pulses arrive every ~100 ms; missing
even one causes a wrong speed reading.

### OLED Button Behaviour

| Press | Duration | Action |
|-------|----------|--------|
| Short | < 1 s | 5-slide sensor carousel, 2 s per slide, animated progress bar |
| Long | ≥ 1 s | System diagnostic screen: SD / Node-RED / Wi-Fi status, 4 s |

---

## 🚀 Getting Started

### 1. Flash MicroPython

Download the latest **Raspberry Pi Pico W** MicroPython firmware from
[micropython.org/download/RPI_PICO_W](https://micropython.org/download/RPI_PICO_W/)
and flash it using Thonny or `picotool`.

### 2. Clone this repository

```bash
git clone https://github.com/HaniAlouane/Station-Meteo.git
```

### 3. Create your credentials file

Copy the template and fill in your credentials:

```bash
cp secrets.example.py secrets.py
```

Edit `secrets.py`:

```python
secrets = {
    "ssid":     "YourWifiName",
    "pw":       "YourWifiPassword",
    "ada_user": "YourAdafruitUsername",
    "ada_key":  "YourAdafruitIOKey",
}
```

> ⚠️ **Never commit `secrets.py` to Git.** It is excluded by `.gitignore`.

### 4. Copy files to the Pico

Using **Thonny** (File → Save as → Raspberry Pi Pico), copy all `.py` files
to the root of the Pico filesystem:

```
main.py
secrets.py              ← your real credentials (not on GitHub)
anemometre.py
capteur_bme.py
capteur_lux.py
capteur_temp_analog.py
sd_logger.py
bme280.py
veml7700.py
ssd1306.py
sdcard.py
```

### 5. Format the SD card

Format your micro-SD card as **FAT32** and insert it into the module.
The logger creates `meteo.csv` automatically on first boot.

### 6. Run

Open `main.py` in Thonny and press **Run** (F5), or rename it to `main.py`
on the Pico so it launches automatically at power-on.

The serial console will show:

```
[SD] Card mounted successfully
[SD] New log file created: /sd/meteo.csv
[Wi-Fi] Connecting to YourWifiName ...
{"vitesse_vent": 2.45, "luminosite": 320.1, "temperature": 21.3, "humidite": 58.0, "pression": 1013.2}
[STATUS] SD:OK  NR:--  WiFi:OK  ADA:OK
```

---

## 📡 Output Channels

### Channel 1 — micro-SD card (CSV)

Always active. One row appended every 12 seconds to `/sd/meteo.csv`.

```csv
timestamp,vitesse_vent,luminosite,temperature,humidite,pression
42,2.45,320.1,21.3,58.0,1013.2
```

> `timestamp` = seconds since last boot (no RTC — add an RTC module for wall-clock timestamps).

### Channel 2 — Node-RED (USB serial)

Connect the Pico via USB to a PC running Node-RED. The station prints a JSON
object every 12 seconds on stdout. Node-RED detects the connection by sending
a single heartbeat byte; the station switches automatically to Wi-Fi/Adafruit
IO when the USB link drops.

### Channel 3 — Adafruit IO (Wi-Fi / MQTT)

Publishes to five individual feeds over MQTT (port 1883):

| Feed slug | Measurement | Unit |
|-----------|-------------|------|
| `vitesse-vent` | Wind speed | km/h |
| `luminosite` | Illuminance | lux |
| `temperature` | Air temperature | °C |
| `humidite` | Relative humidity | % |
| `pression` | Atmospheric pressure | hPa |

---

## 📁 File Structure

```
Station-Meteo/
│
├── main.py                  # Main firmware — acquisition loop and routing
├── anemometre.py            # Cup anemometer pulse driver
├── capteur_bme.py           # BME280 pressure/humidity wrapper
├── capteur_lux.py           # VEML7700 ambient light wrapper
├── capteur_temp_analog.py   # LM335 analogue temperature driver
├── sd_logger.py             # Append-only CSV logger (FAT32 SD card)
│
├── bme280.py                # ↳ Third-party: Bosch BME280 I2C driver
├── veml7700.py              # ↳ Third-party: Vishay VEML7700 I2C driver
├── ssd1306.py               # ↳ Third-party: SSD1306 OLED driver
├── sdcard.py                # ↳ Third-party: MicroPython SPI SD driver
│
├── secrets.example.py       # Credentials template (safe to commit)
├── secrets.py               # Your real credentials (excluded by .gitignore)
├── .gitignore               # Prevents secrets.py from being committed
└── README.md                # This file
```

---

## 📦 Third-Party Libraries

These drivers are included in the repository for ease of deployment on the
Pico.  They are not modified from their original versions.

| File | Author | Source |
|------|--------|--------|
| `bme280.py` | Paul Cunnane, Peter Dahlberg (2016) | [micropython-bme280](https://github.com/dafvid/micropython-bme280) |
| `veml7700.py` | Joseph Hopfmüller, Christophe Rousseau (2019) | [veml7700](https://github.com/palouf34/veml7700) |
| `ssd1306.py` | MicroPython contributors | [micropython-lib](https://github.com/micropython/micropython-lib) |
| `sdcard.py` | MicroPython contributors | [micropython-lib](https://github.com/micropython/micropython-lib) |

---

## 👤 Author

**Hani Alouane**
L3 SPI — Connected Weather Station Project

[![GitHub](https://img.shields.io/badge/GitHub-HaniAlouane-181717?style=for-the-badge&logo=github)](https://github.com/HaniAlouane)
[![Adafruit IO](https://img.shields.io/badge/Adafruit%20IO-HaniAL-000000?style=for-the-badge&logo=adafruit&logoColor=white)](https://io.adafruit.com/HaniAL)

---

*Built with MicroPython on a Raspberry Pi Pico W — 2025*
