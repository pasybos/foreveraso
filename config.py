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

# Тарифы (price_stars – цена в звёздах Telegram)
TARIFFS = {
    "free":    {"days": 1,    "label": "Бесплатная",  "price_rub": "0 ₽",   "price_stars": 0,   "pool": "free"},
    "ref":     {"days": 14,   "label": "Реферальная", "price_rub": "0 ₽",   "price_stars": 0,   "pool": "ref"},
    "week":    {"days": 7,    "label": "Неделя",      "price_rub": "35 ₽",  "price_stars": 25,  "pool": "week"},
    "month":   {"days": 30,   "label": "Месяц",       "price_rub": "99 ₽",  "price_stars": 50,  "pool": "month"},
    "halfyear":{"days": 180,  "label": "Полгода",     "price_rub": "549 ₽", "price_stars": 299, "pool": "halfyear"},
    "year":    {"days": 365,  "label": "Год",         "price_rub": "999 ₽", "price_stars": 549, "pool": "year"},
    "forever": {"days": 3650, "label": "Навсегда",    "price_rub": "2499 ₽","price_stars": 1350,"pool": "forever"},
}

ALL_POOLS = ["free", "ref", "week", "month", "halfyear", "year", "forever"]

POOL_LABELS = {
    "free":     "Бесплатные",
    "ref":      "Реферальные",
    "week":     "Неделя",
    "month":    "Месяц",
    "halfyear": "Полгода",
    "year":     "Год",
    "forever":  "Навсегда",
}
