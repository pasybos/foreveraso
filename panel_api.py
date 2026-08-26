import aiohttp
import logging
from config import PANEL_URL, PANEL_USERNAME, PANEL_PASSWORD, PANEL_INBOUND_ID, API_TOKEN, API_BASE_PATH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PanelAPI:
    def __init__(self):
        self.session = None
        self.token = API_TOKEN
        self.base_url = PANEL_URL.rstrip('/')
        self.inbound_id = PANEL_INBOUND_ID
        self.api_base = API_BASE_PATH.rstrip('/') + '/'

    async def _get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _request(self, method, endpoint, data=None, retries=2):
        session = await self._get_session()
        url = f"{self.base_url}{self.api_base}{endpoint.lstrip('/')}"
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.token,
            "Authorization": f"Bearer {self.token}"
        }
        for attempt in range(retries):
            try:
                async with session.request(method, url, json=data, headers=headers, timeout=10) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"Ошибка {resp.status}: {error_text}")
                        raise Exception(f"HTTP {resp.status}: {error_text}")
                    return await resp.json()
            except Exception as e:
                logger.warning(f"Попытка {attempt+1} не удалась: {e}")
                if attempt == retries-1:
                    raise
                await asyncio.sleep(1)

    async def create_client(self, email: str, expire_timestamp: int, total_gb: int = 0, limit_ip: int = 0):
        import uuid
        client_id = str(uuid.uuid4())
        expiry_ms = int(expire_timestamp * 1000)
        client_data = {
            "id": client_id,
            "email": email,
            "expiryTime": expiry_ms,
            "totalGB": total_gb,
            "limitIp": limit_ip,
            "flow": "xtls-rprx-vision",   # <--- ДОБАВЛЕНО! Обязательно для VLESS-Reality
            "enable": True
        }
        payload = {
            "inboundId": self.inbound_id,
            "clients": [client_data]
        }
        result = await self._request('POST', 'inbounds/addClient', data=payload)
        if result.get('success'):
            return client_id
        else:
            raise Exception(f"Ошибка создания клиента: {result}")

    async def get_client_link(self, client_id: str) -> str:
        result = await self._request('GET', f'inbounds/get/{self.inbound_id}')
        inbound = result.get('obj', {})
        clients = inbound.get('clients', [])
        for client in clients:
            if client.get('id') == client_id:
                return client.get('link', '')
        raise Exception("Клиент не найден")

    async def delete_client(self, client_id: str):
        await self._request('POST', f'inbounds/deleteClient/{client_id}')
        return True

    async def close(self):
        if self.session:
            await self.session.close()
