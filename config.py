import os

VPN_NAME = "Foreveraso VPN"
BOT_TOKEN = "8917061204:AAFSds2LuB4t4T0-Bm8t1rdGwfnietPr8WM"
BOT_USERNAME = "ForeverasoVpn_bot"

ADMIN_IDS = [5926969950, 8293308280]
CHANNEL_ID = "@Foreveraso_Vpn"
PAYMENT_CONTACT = "@pasybos"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_PATH = os.path.join(BASE_DIR, "logo.jpg")
DB_PATH = os.path.join(BASE_DIR, "users.db")

FREE_HOURS = 24

PANEL_DB_PATH = "/etc/x-ui/x-ui.db"
PANEL_SERVER_IP = "89.125.33.130"
SUB_PORT = 2096

# --- Reality-инбаунд (Нидерланды, Amazon) ---
INBOUND_REALITY_ID = 20
REALITY_PORT = 8444
REALITY_SNI = "sun6-21.userapi.com"
REALITY_FINGERPRINT = "chrome"
REALITY_SPIDER_X = "/BevXivqIOpAwr8e"
REALITY_PUBLIC_KEY = "5I-t7A_iNuQ3RQnc27QyoxgL7at_mohR6ZhUQGcJB1k"
REALITY_SHORT_ID = "be93"

# --- XHTTP-инбаунд (Нидерланды, обход) ---
INBOUND_XHTTP_ID = 22
XHTTP_PORT = 443
XHTTP_HOST = "foreverasovpn.work.gd"
XHTTP_PATH = "/api/v9/feed"
XHTTP_SNI = "foreverasovpn.work.gd"
XHTTP_FINGERPRINT = "firefox"
XHTTP_ALPN = "h2,http/1.1"
XHTTP_MODE = "packet-up"

TARIFFS = {
    "free":     {"days": 1,    "label": "Бесплатная",  "price_rub": "0",    "price_stars": 0},
    "ref":      {"days": 14,   "label": "Реферальная", "price_rub": "0",    "price_stars": 0},
    "week":     {"days": 7,    "label": "Неделя",      "price_rub": "35",   "price_stars": 25},
    "month":    {"days": 30,   "label": "Месяц",       "price_rub": "99",   "price_stars": 50},
    "halfyear": {"days": 180,  "label": "Полгода",     "price_rub": "549",  "price_stars": 299},
    "year":     {"days": 365,  "label": "Год",         "price_rub": "999",  "price_stars": 549},
    "forever":  {"days": 3650, "label": "Навсегда",    "price_rub": "2499", "price_stars": 1350},
}
