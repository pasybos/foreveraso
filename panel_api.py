import sqlite3
import time
import random
import logging
import uuid
import json
import subprocess
from config import (
    PANEL_DB_PATH, INBOUND_REALITY_ID, INBOUND_XHTTP_ID,
    PANEL_SERVER_IP, SUB_PORT,
    RELAY_IP, RELAY_PORT, RELAY_UUID, RELAY_PUBLIC_KEY,
    RELAY_SNI, RELAY_SHORT_ID,
    VPN_NAME
)

logger = logging.getLogger(__name__)


def _restart_xray():
    try:
        subprocess.run(["x-ui", "restart"], timeout=25)
        logger.info("Xray перезапущен")
    except Exception as e:
        logger.error("Xray restart failed: %s" % e)


def _add_client_everywhere(conn, inbound_id, email, new_uuid, sub_id, expiry_ts):
    """Создаёт клиента в панели 3x-ui (для учёта)."""
    c = conn.cursor()
    now_ms = int(time.time() * 1000)
    expiry_ms = expiry_ts * 1000

    c.execute("SELECT id FROM clients WHERE email = ?", (email,))
    row = c.fetchone()
    if row:
        client_id = row[0]
        c.execute("""UPDATE clients SET sub_id=?, uuid=?, limit_ip=?, total_gb=?,
                     expiry_time=?, enable=?, updated_at=? WHERE id=?""",
                  (sub_id, new_uuid, 1, 0, expiry_ms, 1, now_ms, client_id))
    else:
        c.execute("""INSERT INTO clients
                     (email, sub_id, uuid, limit_ip, total_gb, expiry_time, enable,
                      tg_id, reset, reset_day, reset_max, traffic_reset, traffic_reset_day,
                      created_at, updated_at, flow, security)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (email, sub_id, new_uuid, 1, 0, expiry_ms, 1,
                   0, 0, 0, 0, "never", 1, now_ms, now_ms, "", "auto"))
        c.execute("SELECT id FROM clients WHERE email = ?", (email,))
        client_id = c.fetchone()[0]

    try:
        c.execute("""INSERT OR IGNORE INTO client_inbounds
                     (client_id, inbound_id, flow_override, created_at)
                     VALUES (?, ?, ?, ?)""",
                  (client_id, inbound_id, "", now_ms))
    except Exception as e:
        logger.warning("client_inbounds insert: %s" % e)

    c.execute("SELECT settings FROM inbounds WHERE id = ?", (inbound_id,))
    row2 = c.fetchone()
    if row2:
        try:
            data = json.loads(row2[0])
            clients = data.get("clients", [])
            found = False
            for cl in clients:
                if cl.get("id") == new_uuid:
                    found = True
                    break
            if not found:
                clients.append({
                    "id": new_uuid,
                    "email": email,
                    "flow": "",
                    "limitIp": 1,
                    "totalGB": 0,
                    "expiryTime": expiry_ms,
                    "enable": True,
                    "tgId": 0,
                    "subId": sub_id,
                })
                data["clients"] = clients
            c.execute("UPDATE inbounds SET settings = ? WHERE id = ?",
                      (json.dumps(data), inbound_id))
        except Exception as e:
            logger.error("JSON update error: %s" % e)

    return True


def get_relay_link():
    """Возвращает единственную ссылку — российский relay."""
    return (
        "vless://%s@%s:%d"
        "?type=tcp&security=reality&sni=%s"
        "&pbk=%s&sid=%s&fp=chrome"
        "&allowInsecure=1&encryption=none"
        "#%s"
    ) % (RELAY_UUID, RELAY_IP, RELAY_PORT,
         RELAY_SNI, RELAY_PUBLIC_KEY, RELAY_SHORT_ID,
         "🇷🇺 Нидерланды")


def create_client(days, email=None):
    """Создаёт клиента в панели для учёта, возвращает relay-ссылку."""
    if not email:
        email = "%s_%d_%d" % (VPN_NAME.replace(" ", "_"), int(time.time()), random.randint(1000, 9999))
    expiry_ts = int(time.time()) + days * 86400
    new_uuid = str(uuid.uuid4())
    sub_id = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=16))

    conn = sqlite3.connect(PANEL_DB_PATH)
    try:
        _add_client_everywhere(conn, INBOUND_REALITY_ID, email, new_uuid, sub_id, expiry_ts)
        _add_client_everywhere(conn, INBOUND_XHTTP_ID, email, new_uuid, sub_id, expiry_ts)
        conn.commit()
    finally:
        conn.close()

    _restart_xray()

    relay_link = get_relay_link()

    return {
        "id": new_uuid,
        "uuid": new_uuid,
        "link": relay_link,
        "relay_link": relay_link,
        "sub_id": sub_id,
        "expiry_time": expiry_ts,
        "email": email,
    }


def delete_client(client_id):
    try:
        conn = sqlite3.connect(PANEL_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, email FROM clients WHERE uuid = ?", (client_id,))
        row = c.fetchone()
        if row:
            db_id, email = row
            c.execute("DELETE FROM client_inbounds WHERE client_id = ?", (db_id,))
            c.execute("DELETE FROM clients WHERE id = ?", (db_id,))
            try:
                c.execute("DELETE FROM client_traffics WHERE email = ?", (email,))
            except:
                pass

        for inbound_id in (INBOUND_REALITY_ID, INBOUND_XHTTP_ID):
            c.execute("SELECT settings FROM inbounds WHERE id = ?", (inbound_id,))
            r = c.fetchone()
            if not r:
                continue
            data = json.loads(r[0])
            clients = data.get("clients", [])
            new_clients = [cl for cl in clients if cl.get("id") != client_id]
            if len(new_clients) != len(clients):
                data["clients"] = new_clients
                c.execute("UPDATE inbounds SET settings = ? WHERE id = ?",
                          (json.dumps(data), inbound_id))

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
        add_ms = extra_days * 86400 * 1000

        c.execute("SELECT id, email, expiry_time FROM clients WHERE uuid = ?", (client_id,))
        row = c.fetchone()
        if row:
            db_id, email, cur = row
            new_exp = (cur if cur and cur > int(time.time() * 1000) else int(time.time() * 1000)) + add_ms
            c.execute("UPDATE clients SET expiry_time = ?, updated_at = ? WHERE id = ?",
                      (new_exp, int(time.time() * 1000), db_id))

        for inbound_id in (INBOUND_REALITY_ID, INBOUND_XHTTP_ID):
            c.execute("SELECT settings FROM inbounds WHERE id = ?", (inbound_id,))
            r = c.fetchone()
            if not r:
                continue
            data = json.loads(r[0])
            clients = data.get("clients", [])
            for cl in clients:
                if cl.get("id") == client_id:
                    cur = cl.get("expiryTime", int(time.time() * 1000))
                    if cur < int(time.time() * 1000):
                        cur = int(time.time() * 1000)
                    cl["expiryTime"] = cur + add_ms
                    break
            c.execute("UPDATE inbounds SET settings = ? WHERE id = ?",
                      (json.dumps(data), inbound_id))

        conn.commit()
        conn.close()
        _restart_xray()
        return True
    except Exception as e:
        logger.error("extend_client error: %s" % e)
        return False
