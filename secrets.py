"""
secrets.py
==========
Local credentials file for the weather station firmware.

This file is imported by ``main.py`` at boot time::

    from secrets import secrets

    wlan.connect(secrets["ssid"], secrets["pw"])

Setup instructions
------------------
1. Copy this file to your Pico W filesystem and rename it ``secrets.py``.
2. Replace every placeholder value with your actual credentials.
3. Never commit the real ``secrets.py`` to version control.

The ``.gitignore`` file in this repository is configured to exclude
``secrets.py`` automatically.  Only this template (``secrets.example.py``)
is tracked by Git.

Obtaining your Adafruit IO key
-------------------------------
1. Create a free account at https://io.adafruit.com
2. Click the key icon (top-right) to reveal your active key.
3. Paste the key string into the ``ada_key`` field below.

Author : Hani AL
"""

secrets = {
    # ------------------------------------------------------------------
    # Wi-Fi network credentials
    # ------------------------------------------------------------------
    "ssid": "YOUR_WIFI_NETWORK_NAME",      # e.g. "MyHomeWifi"
    "pw":   "YOUR_WIFI_PASSWORD",          # e.g. "MyPassword123"

    # ------------------------------------------------------------------
    # Adafruit IO credentials
    # https://io.adafruit.com
    # ------------------------------------------------------------------
    "ada_user": "YOUR_ADAFRUIT_USERNAME",  # e.g. "john_doe"
    "ada_key":  "YOUR_ADAFRUIT_IO_KEY",   # e.g. "aio_xxxxxxxxxxxxxxxxxxxx"
}
