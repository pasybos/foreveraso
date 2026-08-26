import os

VPN_NAME = "foreveraso VPN"
BOT_TOKEN = "8917061204:AAGYzu2OVq5NQc8vGwNn4vDrWR94scX7Q7w"
BOT_USERNAME = "ForeverasoVpn_bot"   # имя вашего бота без @

ADMIN_IDS = [5926969950, 8293308280]
CHANNEL_ID = "@Foreveraso_Vpn"
PAYMENT_CONTACT = "@pasybos"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_PATH = os.path.join(BASE_DIR, "logo.jpg")

# Настройки веб-сервера
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = 8080
PUBLIC_URL = "http://89.125.33.130:8080"

# Данные панели 3x-ui
PANEL_URL = "http://89.125.33.130:2053/Cjgo9OTNe2qsekfCkR"
PANEL_USERNAME = "P4Zo2Vjuot"
PANEL_PASSWORD = "CfELWwjjko"
PANEL_INBOUND_ID = 1
API_TOKEN = "eNTuQlMg6jAOBQtk5ShG1turbqWbgQtzAnTzbAFkJ8CNyiS9"
API_BASE_PATH = "/panel/api/"

FREE_HOURS = 24
PAID_DAYS = 30
PAID_PRICE = "300 ₽"

DB_PATH = os.path.join(BASE_DIR, "users.db")
