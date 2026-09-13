from flask import Flask, Response
import sqlite3
import base64
import time

from config import (
    PANEL_DB_PATH, BRAND_NAME, SUB_UPDATE_INTERVAL_HOURS,
    RU_IP, RU_REALITY_PORT, RU_REALITY_PBK, RU_REALITY_SNI,
    RU_REALITY_SID, RU_REALITY_SPX,
    RU_XHTTP_PORT, RU_XHTTP_HOST, RU_XHTTP_PATH, RU_XHTTP_SNI,
    RELAY_IP, RELAY_PORT, RELAY_UUID, RELAY_PUBLIC_KEY,
    RELAY_SNI, RELAY_SHORT_ID,
    SUB_SERVER_PORT,
)

app = Flask(__name__)


# ---------- Генерация ссылок ----------
def _remark(text: str) -> str:
    return text.replace(" ", "%20")


def build_reality_link(uuid_val: str) -> str:
    remark = _remark(f"{BRAND_NAME} (RU)")
    return (
        f"vless://{uuid_val}@{RU_IP}:{RU_REALITY_PORT}"
        f"?type=tcp&security=reality&sni={RU_REALITY_SNI}"
        f"&pbk={RU_REALITY_PBK}&sid={RU_REALITY_SID}&fp=chrome"
        f"&spx={RU_REALITY_SPX}&allowInsecure=1&encryption=none"
        f"&flow=xtls-rprx-vision"
        f"#{remark}"
    )


def build_xhttp_link(uuid_val: str) -> str:
    remark = _remark(f"{BRAND_NAME} (RU-XHTTP)")
    return (
        f"vless://{uuid_val}@{RU_IP}:{RU_XHTTP_PORT}"
        f"?type=xhttp&mode=packet-up&host={RU_XHTTP_HOST}&path={RU_XHTTP_PATH}"
        f"&security=tls&sni={RU_XHTTP_SNI}&fp=firefox&alpn=h2%2Chttp%2F1.1"
        f"&allowInsecure=1&encryption=none"
        f"#{remark}"
    )


def build_relay_link() -> str:
    remark = _remark(f"{BRAND_NAME} (NL)")
    return (
        f"vless://{RELAY_UUID}@{RELAY_IP}:{RELAY_PORT}"
        f"?type=tcp&security=reality&sni={RELAY_SNI}"
        f"&pbk={RELAY_PUBLIC_KEY}&sid={RELAY_SHORT_ID}&fp=chrome"
        f"&allowInsecure=1&encryption=none"
        f"#{remark}"
    )


# ---------- Работа с БД ----------
def get_client_data(sub_id: str):
    """Возвращает UUID и трафик клиента по sub_id."""
    conn = sqlite3.connect(PANEL_DB_PATH)
    c = conn.cursor()

    c.execute("SELECT uuid, email FROM clients WHERE sub_id = ?", (sub_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None

    uuid_val, email = row

    up = 0
    down = 0
    total = 0
    expire = 0

    # client_traffics содержит счётчики по email
    try:
        c.execute("""SELECT up, down, total, expiry_time
                     FROM client_traffics WHERE email = ? LIMIT 1""", (email,))
        t = c.fetchone()
        if t:
            up     = int(t[0] or 0)
            down   = int(t[1] or 0)
            total  = int(t[2] or 0)
            exp_ms = int(t[3] or 0)
            expire = exp_ms // 1000 if exp_ms > 0 else 0
    except Exception as e:
        print("[sub_server] traffic query error:", e)

    conn.close()
    return {
        "uuid": uuid_val,
        "email": email,
        "up": up,
        "down": down,
        "total": total,
        "expire": expire,
    }


# ---------- HTTP ----------
@app.route("/sub/<sub_id>")
def subscription(sub_id):
    data = get_client_data(sub_id)
    if not data:
        return Response("Not Found", status=404)

    links = [
        build_reality_link(data["uuid"]),
        build_xhttp_link(data["uuid"]),
        build_relay_link(),
    ]

    text = "\n".join(links)
    b64 = base64.b64encode(text.encode()).decode()

    # Заголовок с трафиком (для красивого прогресс-бара в клиенте)
    # Если total == 0 — показываем 100 ГБ как дефолт, чтобы клиент не ругался
    total_for_header = data["total"] if data["total"] > 0 else 107374182400
    userinfo = (
        f"upload={data['up']}; "
        f"download={data['down']}; "
        f"total={total_for_header}; "
        f"expire={data['expire']}"
    )

    # Название профиля (base64, как требует спецификация)
    profile_title = base64.b64encode(BRAND_NAME.encode()).decode()

    resp = Response(b64, mimetype="text/plain; charset=utf-8")
    resp.headers["Subscription-Userinfo"] = userinfo
    resp.headers["Profile-Title"] = profile_title
    resp.headers["Profile-Update-Interval"] = str(SUB_UPDATE_INTERVAL_HOURS)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/health")
def health():
    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=SUB_SERVER_PORT)
