import os
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# Location
HOME_LAT = float(os.getenv("HOME_LAT", 0.0))
HOME_LON = float(os.getenv("HOME_LON", 0.0))

# Network & Hardware
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")
TARGET_NODE_ID = os.getenv("TARGET_NODE_ID", "")
TARGET_MAC = os.getenv("TARGET_MAC", "")

# Notifications
PUSHOVER_API_TOKEN = os.getenv("PUSHOVER_API_TOKEN")
USER1_KEY = os.getenv("USER1_KEY")
USER2_KEY = os.getenv("USER2_KEY")

# Display
PET_NAME = os.getenv("PET_NAME", "Pet")

# System Thresholds & Timers
PROX_TIMEOUT = int(os.getenv("PROX_TIMEOUT", 45))
SAFE_RADIUS = int(os.getenv("SAFE_RADIUS", 75))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 5))
ESCALATION_DELAY = int(os.getenv("ESCALATION_DELAY", 120))
BREADCRUMB_DELAY = int(os.getenv("BREADCRUMB_DELAY", 300))
SEND_BREADCRUMBS_USER1 = os.getenv("SEND_BREADCRUMBS_USER1", "True").lower() == "true"
SEND_BREADCRUMBS_USER2 = os.getenv("SEND_BREADCRUMBS_USER2", "False").lower() == "true"
