# 🌤️ Station Météorologique Connectée - Projet L3 SPI

![MicroPython](https://img.shields.io/badge/MicroPython-1.20-blue?style=for-the-badge&logo=python)
![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-Pico%202%20WH-red?style=for-the-badge&logo=raspberrypi)
![MQTT](https://img.shields.io/badge/MQTT-Adafruit%20IO-yellow?style=for-the-badge)
![Node-RED](https://img.shields.io/badge/Node--RED-Dashboard-darkred?style=for-the-badge&logo=nodered)

Bienvenue sur le dépôt officiel de notre projet d'ingénierie ! 🎓 
Ce projet a été réalisé dans le cadre de notre 3ème année de Licence Sciences pour l'Ingénieur (Spécialité ESR) à l'Université Sorbonne Paris Nord.

Notre objectif ? Concevoir de A à Z une station météo robuste, capable de mesurer 5 grandeurs physiques et de transmettre ses données intelligemment, que ce soit sur un banc de test ou en totale autonomie en extérieur.

---

## ✨ Fonctionnalités principales

Notre station ne se contente pas de lire des capteurs, elle s'adapte à son environnement réseau grâce à une architecture hybride :

* 🔌 **Mode Filaire (Nominal) :** Transmission série asynchrone vers un ordinateur local faisant tourner Node-RED (envoi au format JSON).
* 📡 **Mode Autonome (Secours/Extérieur) :** Si Node-RED n'est pas détecté (mécanisme de *Heartbeat*), la station bascule automatiquement sur sa puce Wi-Fi pour envoyer ses données vers le Cloud Adafruit IO via le protocole MQTT.
* 🛡️ **Résilience :** Gestion automatique des micro-coupures Wi-Fi et reconnexion autonome.

## 🛠️ Matériel & Capteurs

La station s'articule autour d'une **Raspberry Pi Pico 2 WH** et exploite différents protocoles d'acquisition :

* **BME280 (I2C) :** Température numérique, Humidité et Pression atmosphérique.
* **VEML7700 (I2C) :** Luminosité ambiante (en Lux).
* **LM335 (Analogique - ADC) :** Température analogique avec filtrage par suréchantillonnage (*oversampling*).
* **Anémomètre 3D (Impulsionnel) :** Vitesse du vent calculée par détection de période via un capteur à effet Hall (trigger de Schmitt logiciel).
* **Alimentation :** Module LiPo Rider Plus + Accu 18650 (2600 mAh) pour le mode autonome.

## 📂 Architecture du dépôt

* 📁 `/` (Racine) : Contient le script principal `main.py` qui orchestre l'acquisition et la transmission.
* 📄 `capteur_bme.py`, `anemometre.py`... : Pilotes orientés objet pour chaque capteur encapsulant la complexité matérielle.
* 📄 `flows.json` : Fichier d'export de notre architecture Node-RED (à importer directement dans votre interface logicielle).

## 🚀 Installation et Utilisation

1.  Flashez votre Raspberry Pi Pico 2 avec le firmware **MicroPython**.
2.  Déposez l'ensemble des scripts `.py` à la racine de la carte via Thonny IDE.
3.  ⚠️ **Important :** Avant de lancer le script, ouvrez `main.py` et modifiez les constantes réseaux avec vos propres identifiants. Ne publiez jamais vos clés secrètes en ligne !
    ```python
    WIFI_SSID = "VOTRE_RESEAU_WIFI"
    WIFI_PASSWORD = "VOTRE_MOT_DE_PASSE"
    ADAFRUIT_USER = "VOTRE_IDENTIFIANT_AIO"
    ADAFRUIT_KEY = "VOTRE_CLE_SECRETE"
    ```
4.  Importez `flows.json` dans votre Node-RED local pour visualiser le tableau de bord.

---

## 👥 L'Équipe Projet

Ce prototype est le fruit d'un travail collectif mêlant impression 3D, câblage électronique et développement logiciel. 

* **Hani ALOUANE**
* **Mayssa AIT OUAZZOU**
* **Mohammed CHERIF**
* **Andy MBA MEBIAME**
