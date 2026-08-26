import aiohttp
import re
import asyncio
import json
import base64
from typing import List
from database import clear_free_servers, add_free_server, get_multiple_free_servers

FREE_SUBSCRIPTIONS = [
    "https://raw.githubusercontent.com/hans-thomas/v2ray-subscription/refs/heads/master/servers.txt",
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub",
    "https://raw.githubusercontent.com/rtwo2/FastNodes/main/subscription/v2ray.txt",
    "https://www.ermao.net/sub/v2ray/ermao.net",
    "https://raw.githubusercontent.com/Ruk1ng001/freeSub/main/v2ray",
    "https://raw.githubusercontent.com/free-nodes/v2rayfree/main/v202602242",
    "https://raw.githubusercontent.com/learnhard-cn/free_proxy_ss/main/v2ray",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge.txt",
    "https://raw.githubusercontent.com/yebekhe/TVC/main/subscription/v2ray_config",
    "https://raw.githubusercontent.com/arshia-kh/v2ray/main/v2ray",
    "https://raw.githubusercontent.com/milad-gh/v2ray-configs/main/configs.txt",
    "https://raw.githubusercontent.com/aliheidari2002/V2Ray-Config/main/subscription",
]

def extract_host_port(link: str):
    if link.startswith("vless://"):
        match = re.search(r'@([^:]+):(\d+)', link)
        if match:
            return match.group(1), int(match.group(2))
    elif link.startswith("vmess://"):
        try:
            b64 = link[8:]
            b64 += "=" * (4 - len(b64) % 4) if len(b64) % 4 else ""
            decoded = base64.b64decode(b64).decode('utf-8')
            data = json.loads(decoded)
            if "add" in data and "port" in data:
                return data["add"], int(data["port"])
        except:
            pass
    return None, None

def link_has_required_params(link: str) -> bool:
    if link.startswith("vless://"):
        if "security=reality" in link or "encryption=none" in link:
            return True
        else:
            return False
    elif link.startswith("vmess://"):
        if "alterId=0" in link or "alterId" not in link:
            return True
        else:
            return False
    elif link.startswith("trojan://"):
        return True
    return False

async def check_server(link: str, timeout: int = 10) -> bool:
    host, port = extract_host_port(link)
    if not host or not port:
        return False

    allowed_ports = {443, 8443, 2053, 80, 2083, 2096}
    if port not in allowed_ports:
        return False

    if not link_has_required_params(link):
        return False

    for _ in range(2):
        try:
            reader, writer = await asyncio.open_connection(host, port, timeout=timeout)
            writer.close()
            await writer.wait_closed()
            return True
        except:
            await asyncio.sleep(1)
    return False

async def fetch_free_servers() -> List[str]:
    servers = []
    async with aiohttp.ClientSession() as session:
        for url in FREE_SUBSCRIPTIONS:
            try:
                async with session.get(url, timeout=15) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        found = re.findall(
                            r'(vless://[^\s]+|vmess://[^\s]+|trojan://[^\s]+)',
                            text
                        )
                        servers.extend(found)
            except Exception:
                continue
    return list(set(servers))

async def update_free_servers_db():
    all_servers = await fetch_free_servers()
    if not all_servers:
        return

    to_check = all_servers[:300]
    tasks = [check_server(link) for link in to_check]
    results = await asyncio.gather(*tasks)
    valid = [link for link, ok in zip(to_check, results) if ok]

    if not valid:
        valid = [link for link in all_servers[:300] if link_has_required_params(link)]

    clear_free_servers()
    for link in valid[:200]:
        add_free_server(link)

def get_servers(limit=5) -> List[str]:
    return get_multiple_free_servers(limit)

async def refresh_servers():
    await update_free_servers_db()
