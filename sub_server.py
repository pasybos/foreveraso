from flask import Flask, Response, request
import sqlite3
import base64
import json

app = Flask(__name__)

DB_PATH = "/etc/x-ui/x-ui.db"
RELAY_LINK = "vless://ddea8633-e239-4125-83f8-22a8bc302d4a@81.26.177.11:443?type=tcp&security=reality&sni=www.microsoft.com&pbk=umlKj1LxX4Z2aadIeabM0fTh9qn9LAR7U9RydX0ZWw&sid=be93&fp=chrome&allowInsecure=1&encryption=none#🇷🇺 Нидерланды"

def get_client_links(sub_id):
    """Находит клиента по subId и формирует 2 ссылки (Reality + XHTTP)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT uuid FROM clients WHERE sub_id = ?", (sub_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return []

    uuid_val = row[0]

    # Reality ссылка
    reality = (
        f"vless://{uuid_val}@89.125.33.130:8444"
        f"?type=tcp&security=reality&sni=p-nt-www-amazon-com-kalias.amazon.com"
        f"&pbk=5I-t7A_iNuQ3RQnc27QyoxgL7at_mohR6ZhUQGcJB1k&sid=be93&fp=chrome"
        f"&spx=/BevXivqIOpAwr8e&allowInsecure=1&encryption=none"
        f"#🇳🇱 Нидерланды"
    )

    # XHTTP ссылка
    xhttp = (
        f"vless://{uuid_val}@89.125.33.130:443"
        f"?type=xhttp&mode=packet-up&host=foreverasovpn.work.gd&path=/api/v9/feed"
        f"&security=tls&sni=foreverasovpn.work.gd&fp=firefox&alpn=h2%2Chttp%2F1.1"
        f"&allowInsecure=1&encryption=none"
        f"#🇳🇱 Нидерланды (обход)"
    )

    return [reality, xhttp, RELAY_LINK]


@app.route("/sub/<sub_id>")
def subscription(sub_id):
    links = get_client_links(sub_id)
    if not links:
        return Response("Not Found", status=404)
    text = "\n".join(links)
    b64 = base64.b64encode(text.encode()).decode()
    return Response(b64, mimetype="text/plain")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=2087)
