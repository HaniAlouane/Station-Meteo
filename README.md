# Station Météorologique Connectée - Projet L3 SPI

Ce dépôt contient le code source et l'architecture logicielle d'une station météorologique connectée, développée dans le cadre de ma 3ème année de Licence Sciences pour l'Ingénieur (Spécialité ESR) à l'Université Sorbonne Paris Nord.

L'objectif de ce projet est de proposer un système d'acquisition robuste capable de mesurer 5 grandeurs physiques et d'adapter sa transmission de données selon son environnement énergétique et réseau.

---

## Fonctionnalités principales

L'architecture logicielle repose sur deux modes de fonctionnement :

* **Mode Filaire (Nominal) :** Transmission série asynchrone vers un ordinateur local exécutant Node-RED. Les données sont envoyées sous forme de trames JSON.
* **Mode Autonome (Secours) :** En l'absence de Node-RED (détectée via un mécanisme de polling/heartbeat), la station bascule sur son interface Wi-Fi pour publier ses mesures sur le broker MQTT Adafruit IO.

Le programme intègre également une gestion des micro-coupures réseau avec tentative de reconnexion automatique.

## Matériel et Capteurs

Le système est architecturé autour d'une **Raspberry Pi Pico 2 WH** programmée en MicroPython, interfacée avec les composants suivants :

* **BME280 (Bus I2C) :** Mesure de la température, humidité et pression atmosphérique.
* **VEML7700 (Bus I2C) :** Mesure de la luminosité ambiante.
* **LM335 (Analogique) :** Mesure de la température avec conditionnement et oversampling logiciel (10 échantillons).
* **Anémomètre à coupelles :** Mesure de la vitesse du vent par détection impulsionnelle (capteur à effet Hall et trigger de Schmitt logiciel).
* **Alimentation :** Module LiPo Rider Plus + Accumulateur Li-Ion 18650 (2600 mAh).

## Structure du dépôt

* `main.py` : Boucle principale non-bloquante gérant l'acquisition temps réel et le routage des données.
* `capteur_bme.py`, `anemometre.py`, etc. : Classes encapsulant la configuration et la lecture de chaque capteur (Programmation Orientée Objet).
* `flows.json` : Fichier de configuration de l'architecture Node-RED (traitement, multiplexage et passerelle MQTT).

## Instructions d'installation

1. Flasher la Raspberry Pi Pico 2 WH avec l'environnement MicroPython.
2. Transférer les scripts `.py` à la racine du microcontrôleur.
3. Avant l'exécution, renseigner les identifiants locaux dans le fichier `main.py` :
    ```python
    WIFI_SSID = "NOM_DU_RESEAU"
    WIFI_PASSWORD = "MOT_DE_PASSE"
    ADAFRUIT_USER = "IDENTIFIANT_AIO"
    ADAFRUIT_KEY = "CLE_AIO"
    ```
4. Importer le fichier `flows.json` dans un environnement Node-RED local.

---

**Auteur :** Hani ALOUANE
