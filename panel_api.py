import sqlite3
import time
import random
import logging
import uuid
import json
import subprocess
from config import (
    PANEL_DB_PATH, INBOUND_REALITY_ID, INBOUND_XHTTP_ID,
    REALITY_SNI, REALITY_FINGERPRINT, REALITY_SPIDER_X,
    REALITY_PUBLIC_KEY, REALITY_SHORT_ID,
    PANEL_SERVER_IP, SUB_PORT, REALITY_PORT, VPN_NAME
)

logger = logging.getLogger(__name__)


def _restart_xray():
    """Быстрый перезапуск Xray через SIGKILL. Systemd поднимет его за секунду."""
    try:
        subprocess.run(["systemctl", "kill", "--signal=SIGKILL", "xray"], timeout=10)
        logger.info("Xray перезапущен (быстро)")
    except Exception as e:
        logger.error("Xray restart failed: %s" % e)


def _add_client(conn, inbound_id, email, new_uuid, sub_id, expiry_ts):
    c = conn.cursor()
    c.execute("SELECT settings FROM inbounds WHERE id = ?", (inbound_id,))
    row = c.fetchone()
    if not row:
        logger.warning("Inbound %d не найден" % inbound_id)
        return False
    try:
        data = json.loads(row[0])
    except Exception as e:
        logger.error("Bad settings inbound %d: %s" % (inbound_id, e))
        return False
    clients = data.get("clients", [])
    for cl in clients:
        if cl.get("id") == new_uuid:
            return True
    clients.append({
        "id": new_uuid,
        "email": email,
        "flow": "",
        "limitIp": 1,
        "totalGB": 0,
        "expiryTime": expiry_ts * 1000,
        "enable": True,
        "tgId": 0,
        "subId": sub_id,
    })
    data["clients"] = clients
    c.execute("UPDATE inbounds SET settings = ? WHERE id = ?", (json.dumps(data), inbound_id))
    return True


def create_client(days, email=None):
    if not email:
        email = "%s_%d_%d" % (VPN_NAME.replace(" ", "_"), int(time.time()), random.randint(1000, 9999))
    expiry_ts = int(time.time()) + days * 86400
    new_uuid = str(uuid.uuid4())
    sub_id = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=16))

    conn = sqlite3.connect(PANEL_DB_PATH)
    try:
        _add_client(conn, INBOUND_REALITY_ID, email, new_uuid, sub_id, expiry_ts)
        _add_client(conn, INBOUND_XHTTP_ID, email, new_uuid, sub_id, expiry_ts)
        conn.commit()
    finally:
        conn.close()

    _restart_xray()

    sub_link = "http://%s:%d/sub/%s" % (PANEL_SERVER_IP, SUB_PORT, sub_id)

    direct_link = (
        "vless://%s@%s:%d"
        "?type=tcp&security=reality&sni=%s"
        "&pbk=%s&fp=%s&sid=%s&spx=%s&encryption=none"
        "#%s"
    ) % (new_uuid, PANEL_SERVER_IP, REALITY_PORT, REALITY_SNI,
         REALITY_PUBLIC_KEY, REALITY_FINGERPRINT, REALITY_SHORT_ID,
         REALITY_SPIDER_X, VPN_NAME)

    return {
        "id": new_uuid,
        "uuid": new_uuid,
        "link": sub_link,
        "direct_link": direct_link,
        "sub_id": sub_id,
        "expiry_time": expiry_ts,
        "email": email,
    }


def delete_client(client_id):
    try:
        conn = sqlite3.connect(PANEL_DB_PATH)
        c = conn.cursor()
        for inbound_id in (INBOUND_REALITY_ID, INBOUND_XHTTP_ID):
            c.execute("SELECT settings FROM inbounds WHERE id = ?", (inbound_id,))
            row = c.fetchone()
            if not row:
                continue
            data = json.loads(row[0])
            clients = data.get("clients", [])
            new_clients = [cl for cl in clients if cl.get("id") != client_id]
            if len(new_clients) != len(clients):
                data["clients"] = new_clients
                c.execute("UPDATE inbounds SET settings = ? WHERE id = ?", (json.dumps(data), inbound_id))
        conn.commit()
        conn.close()
        _restart_xray()
        return True
    except Exception as e:
        logger.error("delete_client error: %s" % e)
        return False


def extend_client(client_id, extra_days):
    try:
        conn = sqlite3.connect(PANEL_DB_PATH)
        c = conn.cursor()
        for inbound_id in (INBOUND_REALITY_ID, INBOUND_XHTTP_ID):
            c.execute("SELECT settings FROM inbounds WHERE id = ?", (inbound_id,))
            row = c.fetchone()
            if not row:
                continue
            data = json.loads(row[0])
            clients = data.get("clients", [])
            for cl in clients:
                if cl.get("id") == client_id:
                    cl["expiryTime"] = cl.get("expiryTime", int(time.time() * 1000)) + extra_days * 86400 * 1000
                    break
            c.execute("UPDATE inbounds SET settings = ? WHERE id = ?", (json.dumps(data), inbound_id))
        conn.commit()
        conn.close()
        _restart_xray()
        return True
    except Exception as e:
        logger.error("extend_client error: %s" % e)
        return False
