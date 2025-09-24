import asyncio
import aiohttp
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from config import Config

class IPService:
    """Сервис для работы с IP-API для получения информации о геолокации"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._last_request_time = None
        self._request_count = 0
        self._rate_limit_reset = datetime.now()

    async def get_ip_info(self, ip_address: str) -> Optional[Dict[str, Any]]:
        """Получение информации об IP-адресе"""
        if not await self._check_rate_limit():
            self.logger.warning("Rate limit превышен для IP-API")
            return None
        
        try:
            url = f"{self.config.ip_api_url}/{ip_address}"
            params = {
                'fields': 'status,message,country,regionName,city,isp,org,as,query'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        self._update_rate_limit()
                        
                        if data.get('status') == 'success':
                            return {
                                'country': data.get('country', 'Неизвестно'),
                                'region': data.get('regionName', 'Неизвестно'),
                                'city': data.get('city', 'Неизвестно'),
                                'isp': data.get('isp', 'Неизвестно'),
                                'org': data.get('org', 'Неизвестно'),
                                'as': data.get('as', 'Неизвестно'),
                                'ip': data.get('query', ip_address)
                            }
                        else:
                            self.logger.error(f"IP-API вернул ошибку: {data.get('message', 'Неизвестная ошибка')}")
                            return None
                    else:
                        self.logger.error(f"Ошибка HTTP при запросе IP-API: {response.status}")
                        return None
        
        except asyncio.TimeoutError:
            self.logger.error("Таймаут при запросе к IP-API")
            return None
        except Exception as e:
            self.logger.error(f"Ошибка при запросе к IP-API: {e}")
            return None

    async def get_ip_info_batch(self, ip_addresses: list) -> Dict[str, Dict[str, Any]]:
        """Пакетное получение информации о нескольких IP-адресах"""
        results = {}
        
        for ip in ip_addresses[:5]:
            ip_info = await self.get_ip_info(ip)
            if ip_info:
                results[ip] = ip_info
            await asyncio.sleep(0.5)
        
        return results

    async def _check_rate_limit(self) -> bool:
        """Проверка ограничений по количеству запросов"""
        now = datetime.now()
        
        if now >= self._rate_limit_reset:
            self._request_count = 0
            self._rate_limit_reset = now + timedelta(minutes=1)
        
        return self._request_count < self.config.ip_api_rate_limit

    def _update_rate_limit(self):
        """Обновление счетчика запросов"""
        self._request_count += 1
        self._last_request_time = datetime.now()

    def format_ip_info(self, ip_info: Dict[str, Any]) -> str:
        """Форматирование информации об IP для отображения"""
        if not ip_info:
            return "❌ Информация об IP недоступна"
        
        return f"""🌍 Информация об IP: {ip_info['ip']}

🏳️ Страна: {ip_info['country']}
🏛️ Регион: {ip_info['region']}
🏙️ Город: {ip_info['city']}
🌐 Провайдер: {ip_info['isp']}
🏢 Организация: {ip_info['org']}
🔢 AS: {ip_info['as']}"""

    def format_multiple_ip_info(self, ip_info_dict: Dict[str, Dict[str, Any]]) -> str:
        """Форматирование информации о нескольких IP"""
        if not ip_info_dict:
            return "❌ Информация об IP недоступна"
        
        result = "🌍 Геолокация IP подключений:\n\n"
        
        for i, (ip, info) in enumerate(ip_info_dict.items(), 1):
            result += f"{i}. 🌐 {ip}\n"
            result += f"   📍 {info['country']}, {info['city']}\n"
            result += f"   🌐 {info['isp']}\n\n"
        
        return result