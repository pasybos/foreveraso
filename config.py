import os

# ================== БОТ ==================
VPN_NAME = "Foreveraso Vpn"
BRAND_NAME = "Foreveraso Vpn"          # Имя в карточке подписки
BOT_TOKEN = "8917061204:AAFSds2LuB4t4T0-Bm8t1rdGwfnietPr8WM"
BOT_USERNAME = "ForeverasoVpn_bot"

ADMIN_IDS = [5926969950, 8293308280]
CHANNEL_ID = "@Foreveraso_Vpn"
PAYMENT_CONTACT = "@pasybos"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_PATH = os.path.join(BASE_DIR, "logo.jpg")
DB_PATH = os.path.join(BASE_DIR, "users.db")

FREE_HOURS = 24

# ================== ПАНЕЛЬ 3x-ui ==================
PANEL_DB_PATH = "/etc/x-ui/x-ui.db"
INBOUND_REALITY_ID = 20
INBOUND_XHTTP_ID = 22

# ================== РОССИЙСКИЙ СЕРВЕР (Reality + XHTTP) ==================
RU_IP = "89.125.33.130"
RU_REALITY_PORT = 8444
RU_XHTTP_PORT = 443

# Reality-параметры (публичный ключ соответствует приватному на сервере)
RU_REALITY_PBK = "q_pkX4t8t9oY8E2oEs1I7ZvrplJkYLyksTHQ91idGCY"
RU_REALITY_SNI = "www.microsoft.com"
RU_REALITY_SID = "be93"
RU_REALITY_SPX = "/"

# XHTTP-параметры (порт 443 с TLS)
RU_XHTTP_HOST = "foreverasovpn.work.gd"
RU_XHTTP_PATH = "/api/v9/feed"
RU_XHTTP_SNI  = "foreverasovpn.work.gd"

# ================== НИДЕРЛАНДЫ (Relay) ==================
RELAY_IP = "81.26.177.11"
RELAY_PORT = 443
RELAY_UUID = "ddea8633-e239-4125-83f8-22a8bc302d4a"
RELAY_PUBLIC_KEY = "umlKj1LxX4Z2aadIeabM0fTh9qn9LAR7U9RydX0ZWw"
RELAY_SNI = "www.microsoft.com"
RELAY_SHORT_ID = "be93"

# ================== ПОДПИСКИ ==================
SUB_PORT = 2096
SUB_SERVER_PORT = 2087
SUB_UPDATE_INTERVAL_HOURS = 6

# ================== ТАРИФЫ ==================
TARIFFS = {
    "free":     {"days": 1,    "label": "Бесплатная",  "price_rub": "0",    "price_stars": 0},
    "ref":      {"days": 14,   "label": "Реферальная", "price_rub": "0",    "price_stars": 0},
    "week":     {"days": 7,    "label": "Неделя",      "price_rub": "35",   "price_stars": 25},
    "month":    {"days": 30,   "label": "Месяц",       "price_rub": "99",   "price_stars": 50},
    "halfyear": {"days": 180,  "label": "Полгода",     "price_rub": "549",  "price_stars": 299},
    "year":     {"days": 365,  "label": "Год",         "price_rub": "999",  "price_stars": 549},
    "forever":  {"days": 3650, "label": "Навсегда",    "price_rub": "2499", "price_stars": 1350},
}
