# 📡 Connected Weather Station — L3 SPI Project

![MicroPython](https://img.shields.io/badge/MicroPython-1.20-blue?style=for-the-badge&logo=python)
![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-Pico%202%20WH-red?style=for-the-badge&logo=raspberrypi)
![MQTT](https://img.shields.io/badge/MQTT-Adafruit%20IO-yellow?style=for-the-badge)
![Node-RED](https://img.shields.io/badge/Node--RED-Dashboard-darkred?style=for-the-badge&logo=nodered)

---

## 🧭 Project Overview

This repository contains the source code and software architecture of a **connected weather station**, developed as part of the **3rd year of a Bachelor’s degree in Engineering Sciences (SPI) — ESR specialization** at Sorbonne Paris Nord University.

The goal of this project is to design an embedded system capable of:
- measuring environmental parameters,
- processing data in real time,
- and dynamically adapting data transmission depending on network conditions.

---

## 🎯 System Objective

The main objective is to build a **complete IoT acquisition and monitoring chain**, going from:
- physical measurement,
- embedded processing,
- to local and cloud visualization.

The system must ensure:
- robustness,
- service continuity,
- and network adaptability.

---

## ⚙️ System Operation

The station is based on a **dual operating mode architecture**:

### 🔌 Wired mode (default)
- USB serial communication to a computer
- Local interface using Node-RED
- Data sent in JSON format
- Used for testing and lab environments

### 📡 Autonomous mode (Wi-Fi / Cloud)
- Automatically activated when Node-RED is not available
- Built-in Wi-Fi connection (Raspberry Pi Pico 2 WH)
- MQTT communication protocol
- Data published to Adafruit IO

---

## 📊 Measured Parameters

The station measures 5 environmental variables:

- 🌡 Temperature  
- 💧 Relative humidity  
- 🌬 Atmospheric pressure  
- 💡 Light intensity  
- 🌪 Wind speed  

---

## 🧱 Software Architecture

The program is structured using a **modular OOP approach**, separating:
- sensor acquisition,
- data processing,
- network communication.

### 📁 Project structure

- `main.py` / `station_meteo.py` → main system control  
- `anemometre.py` → wind speed measurement  
- `capteur_bme.py` / `bme280.py` → temperature, pressure, humidity  
- `capteur_lux.py` / `veml7700.py` → light sensor  
- `capteur_temp_analog.py` → LM335 analog temperature sensor  
- `flows.json` → Node-RED configuration (data pipeline)

---

## 🚀 Installation

### 1. Microcontroller setup
- Flash the **Raspberry Pi Pico 2 WH** with MicroPython

### 2. Deployment
- Copy all `.py` files to the board
- Use an IDE such as **Thonny**

### 3. User configuration

Replace credentials in `secrets.py`:

```python
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"

ADAFRUIT_USER = "YOUR_ADAFRUIT_USERNAME"
ADAFRUIT_KEY = "YOUR_ADAFRUIT_IO_KEY"
