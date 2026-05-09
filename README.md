# Station Météorologique Connectée - Projet L3 SPI

![MicroPython](https://img.shields.io/badge/MicroPython-1.20-blue?style=for-the-badge&logo=python)
![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-Pico%202%20WH-red?style=for-the-badge&logo=raspberrypi)
![MQTT](https://img.shields.io/badge/MQTT-Adafruit%20IO-yellow?style=for-the-badge)
![Node-RED](https://img.shields.io/badge/Node--RED-Dashboard-darkred?style=for-the-badge&logo=nodered)

Ce dépôt contient le code source et l'architecture logicielle d'une station météorologique connectée, développée dans le cadre d'une 3e année de Licence Sciences pour l'Ingénieur (Spécialité ESR) à l'Université Sorbonne Paris Nord.

L'objectif de ce projet est de proposer un système d'acquisition robuste capable de mesurer 5 grandeurs physiques et d'adapter sa transmission de données selon son environnement énergétique et réseau.

---

## Fonctionnalités principales

L'architecture logicielle repose sur deux modes de fonctionnement :

* **Mode Filaire (Nominal) :** Transmission série asynchrone vers un ordinateur local exécutant Node-RED. Les données sont envoyées sous forme de trames JSON.
* **Mode Autonome (Secours/Extérieur) :** En l'absence de Node-RED (détectée via un mécanisme de *heartbeat*), la station bascule automatiquement sur son interface Wi-Fi intégrée pour publier ses mesures sur le broker MQTT Adafruit IO.

Le programme intègre également une gestion des micro-coupures réseau avec tentative de reconnexion automatique.

## Architecture du dépôt

L'architecture logicielle repose sur la Programmation Orientée Objet (POO) pour séparer la logique d'acquisition de la logique de transmission. Voici le détail des fichiers présents :

* `main.py` & `station_meteo.py` : Scripts principaux non-bloquants gérant l'acquisition temps réel et le routage réseau.
* `anemometre.py` : Détection impulsionnelle matérielle et calcul de la vitesse du vent.
* `capteur_bme.py` & `bme280.py` : Classes et librairies I2C pour la température, l'humidité et la pression.
* `capteur_lux.py`, `capteur_lumiere_analog.py` & `veml7700.py` : Pilotes et traitement de la luminosité ambiante.
* `capteur_temp_analog.py` : Conditionnement et oversampling pour le capteur analogique LM335.
* `flows.json` : Fichier de configuration de l'architecture Node-RED (décodage, traitement et passerelle MQTT).

## Instructions d'installation

1. Flasher la Raspberry Pi Pico 2 WH avec l'environnement **MicroPython**.
2. Transférer l'ensemble des scripts `.py` à la racine du microcontrôleur via un IDE comme Thonny.
3. Avant l'exécution, renseigner les identifiants locaux dans les scripts :
    ```python
    WIFI_SSID = "NOM_DU_RESEAU"
    WIFI_PASSWORD = "MOT_DE_PASSE"
    ADAFRUIT_USER = "IDENTIFIANT_AIO"
    ADAFRUIT_KEY = "CLE_AIO"
    ```
4. Importer le fichier `flows.json` dans un environnement Node-RED local pour visualiser le tableau de bord et multiplexer les flux.
