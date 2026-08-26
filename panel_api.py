import aiohttp
import asyncio
import logging
from config import PANEL_URL, PANEL_USERNAME, PANEL_PASSWORD, PANEL_INBOUND_ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PanelAPI:
    def __init__(self):
        self.session = None
        self.cookies = None
        self.base_url = PANEL_URL.rstrip('/')
        self.inbound_id = PANEL_INBOUND_ID
        self.logged_in = False

    async def _get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _login(self):
        """Авторизуется в панели и сохраняет куки."""
        session = await self._get_session()
        login_url = f"{self.base_url}/login"
        data = {
            "username": PANEL_USERNAME,
            "password": PANEL_PASSWORD
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        async with session.post(login_url, data=data, headers=headers) as resp:
            if resp.status == 200:
                self.cookies = session.cookie_jar
                self.logged_in = True
                logger.info("✅ Успешная авторизация в панели")
                return True
            else:
                error = await resp.text()
                logger.error(f"❌ Ошибка авторизации: {resp.status} - {error}")
                raise Exception(f"Не удалось войти в панель: {error}")

    async def _ensure_login(self):
        if not self.logged_in:
            await self._login()

    async def _request(self, method, endpoint, data=None):
        """Выполняет запрос к API с куками сессии."""
        await self._ensure_login()
        session = await self._get_session()
        # Пробуем разные пути
        possible_paths = ["/panel/api/", "/xui/API/", "/api/"]
        for path in possible_paths:
            url = f"{self.base_url}{path}{endpoint.lstrip('/')}"
            logger.info(f"Попытка запроса: {method} {url}")
            async with session.request(method, url, json=data, headers={"Content-Type": "application/json"}, cookies=self.cookies) as resp:
                if resp.status == 200:
                    logger.info(f"Успешный ответ от {url}")
                    return await resp.json()
                elif resp.status == 404:
                    continue
                else:
                    error_text = await resp.text()
                    logger.error(f"Ошибка {resp.status} от {url}: {error_text}")
                    raise Exception(f"HTTP {resp.status}: {error_text}")
        raise Exception("Не удалось найти рабочий путь к API (проверены /panel/api/, /xui/API/, /api/)")

    async def create_client(self, email: str, expire_timestamp: int, total_gb: int = 0, limit_ip: int = 1):
        import uuid
        client_id = str(uuid.uuid4())
        expiry_ms = int(expire_timestamp * 1000)
        client_data = {
            "id": client_id,
            "email": email,
            "expiryTime": expiry_ms,
            "totalGB": total_gb,
            "limitIp": limit_ip,
            "flow": "xtls-rprx-vision",
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
