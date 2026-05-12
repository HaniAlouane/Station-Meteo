# 📡 Station Météorologique Connectée — Projet L3 SPI

![MicroPython](https://img.shields.io/badge/MicroPython-1.20-blue?style=for-the-badge&logo=python)
![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-Pico%202%20WH-red?style=for-the-badge&logo=raspberrypi)
![MQTT](https://img.shields.io/badge/MQTT-Adafruit%20IO-yellow?style=for-the-badge)
![Node-RED](https://img.shields.io/badge/Node--RED-Dashboard-darkred?style=for-the-badge&logo=nodered)

---

## 🧭 Présentation du projet

Ce dépôt contient le code source et l’architecture logicielle d’une **station météorologique connectée**, réalisée dans le cadre de la **Licence 3 Sciences pour l’Ingénieur (SPI) — spécialité ESR** à l’Université Sorbonne Paris Nord.

Le projet vise à concevoir un système embarqué capable de :
- mesurer plusieurs grandeurs environnementales,
- assurer leur traitement en temps réel,
- et adapter dynamiquement leur transmission selon l’état du réseau.

---

## 🎯 Objectif du système

L’objectif principal est de développer une **chaîne complète d’acquisition et de supervision IoT**, allant :
- de la mesure physique,
- au traitement embarqué,
- jusqu’à la visualisation locale et Cloud.

Le système doit garantir :
- robustesse,
- continuité de service,
- et adaptabilité réseau.

---

## ⚙️ Fonctionnement général

La station repose sur une architecture à **double mode de fonctionnement** :

### 🔌 Mode filaire (nominal)
- Transmission série USB vers un ordinateur
- Interface locale via Node-RED
- Envoi des données au format JSON
- Utilisation en environnement de test ou laboratoire

### 📡 Mode autonome (Wi-Fi / Cloud)
- Activation automatique en l’absence de Node-RED
- Connexion Wi-Fi intégrée (Raspberry Pi Pico 2 WH)
- Transmission via protocole MQTT
- Publication sur Adafruit IO

---

## 📊 Grandeurs mesurées

La station permet la mesure de 5 paramètres physiques :

- 🌡 Température
- 💧 Humidité relative
- 🌬 Pression atmosphérique
- 💡 Luminosité
- 🌪 Vitesse du vent

---

## 🧱 Architecture logicielle

Le programme est structuré en **modules indépendants (POO)** afin de séparer clairement :
- acquisition des capteurs,
- traitement des données,
- communication réseau.

### 📁 Organisation

- `main.py` / `station_meteo.py` → orchestration générale du système  
- `anemometre.py` → mesure de la vitesse du vent  
- `capteur_bme.py` / `bme280.py` → température, pression, humidité  
- `capteur_lux.py` / `veml7700.py` → luminosité  
- `capteur_temp_analog.py` → capteur analogique LM335  
- `flows.json` → configuration Node-RED (pipeline de données)

---

## 🚀 Installation

### 1. Microcontrôleur
- Flasher la **Raspberry Pi Pico 2 WH** avec MicroPython

### 2. Déploiement
- Copier tous les fichiers `.py` sur la carte
- Utiliser un IDE comme **Thonny**

### 3. Configuration utilisateur

Remplacer les identifiants dans le fichier `secrets.py` :

```python
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"

ADAFRUIT_USER = "YOUR_ADAFRUIT_USERNAME"
ADAFRUIT_KEY = "YOUR_ADAFRUIT_IO_KEY"
