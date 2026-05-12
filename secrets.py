"""
secrets.py — Credentials file
=============================================

This file is used to store Wi-Fi and Adafruit IO credentials.

It must be created locally on your device (Pico filesystem).

If you share this project, you should create a secrets.example.py file
containing only template values (no real credentials).

IMPORTANT:
- The values below are NOT my real credentials.
- They are placeholders / example values.
- You must replace them with your own credentials for the code to work.

Example format:

    secrets = {
        "ssid":     "YOUR_WIFI_SSID",
        "pw":       "YOUR_WIFI_PASSWORD",
        "ada_user": "YOUR_ADAFRUIT_USERNAME",
        "ada_key":  "YOUR_ADAFRUIT_IO_KEY",
    }
"""

secrets = {
    # Wi-Fi network → Réseau Wi-Fi
    "ssid":     "YOUR_WIFI_SSID",
    "pw":       "YOUR_WIFI_PASSWORD",

    # Adafruit IO — https://io.adafruit.com
    "ada_user": "YOUR_ADAFRUIT_USERNAME",
    "ada_key":  "YOUR_ADAFRUIT_IO_KEY",
}