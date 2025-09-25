import logging
from typing import Optional, List
import ipaddress
import re
from database.database import get_db, BotSettings

class SettingsService:
    """Сервис для управления настройками бота"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.db = get_db()
    
    async def get_default_dns(self) -> str:
        """Получить DNS серверы по умолчанию"""
        dns = await self.db.get_setting('default_dns')
        return dns if dns else "1.1.1.1, 8.8.8.8"
    
    async def set_default_dns(self, dns_servers: str) -> bool:
        """Установить DNS серверы по умолчанию"""
        return await self.db.set_setting(
            'default_dns', 
            dns_servers, 
            'DNS сервера по умолчанию'
        )
    
    async def get_default_endpoint(self) -> Optional[str]:
        """Получить endpoint по умолчанию"""
        endpoint = await self.db.get_setting('default_endpoint')
        return endpoint if endpoint and endpoint.strip() else None
    
    async def set_default_endpoint(self, endpoint: str) -> bool:
        """Установить endpoint по умолчанию"""
        return await self.db.set_setting('default_endpoint', endpoint, 'Endpoint по умолчанию')
    
    def validate_dns_servers(self, dns_servers: str) -> bool:
        """Проверить корректность DNS серверов"""
        try:
            servers = [s.strip() for s in dns_servers.split(',')]
            for server in servers:
                if server:
                    ipaddress.ip_address(server)
            return len(servers) > 0
        except:
            return False
    
    def validate_endpoint(self, endpoint: str) -> bool:
        """Проверить корректность endpoint"""
        if not endpoint or not endpoint.strip():
            return False
        try:
            ipaddress.ip_address(endpoint.strip())
            return True
        except:
            domain_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
            return bool(re.match(domain_pattern, endpoint.strip()))