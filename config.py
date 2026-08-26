import os

VPN_NAME = "foreveraso VPN"
BOT_TOKEN = "8917061204:AAGYzu2OVq5NQc8vGwNn4vDrWR94scX7Q7w"
BOT_USERNAME = "ForeverasoVpn_bot"

ADMIN_IDS = [5926969950, 8293308280]
CHANNEL_ID = "@Foreveraso_Vpn"
PAYMENT_CONTACT = "@pasybos"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_PATH = os.path.join(BASE_DIR, "logo.jpg")

FREE_HOURS = 24
DB_PATH = os.path.join(BASE_DIR, "users.db")

# Тарифы для Telegram Stars
TARIFFS = {
    "week": {"days": 7, "price_stars": 25},
    "month": {"days": 30, "price_stars": 50},
    "halfyear": {"days": 180, "price_stars": 299},
    "year": {"days": 365, "price_stars": 549},
    "forever": {"days": 3650, "price_stars": 1350},
}
TARIFF_NAMES = {
    "week": "Неделя",
    "month": "Месяц",
    "halfyear": "Полгода",
    "year": "Год",
    "forever": "Навсегда"
}
