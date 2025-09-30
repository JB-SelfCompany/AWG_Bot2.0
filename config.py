import os
from dataclasses import dataclass
from typing import List

@dataclass
class Config:
    """Конфигурация бота"""
    
    # Основные настройки - укажите свои значения
    bot_token: str = "BOT_TOKEN"  # Замените на ваш токен
    admin_ids: List[int] = None
    
    # AWG настройки
    awg_config_dir: str = "/etc/amnezia/amneziawg"
    awg_interface: str = "awg0"
    server_ip: str = "10.10.0.1"
    server_port: int = 52820
    server_subnet: str = "10.10.0.0/24"
    server_ipv6: str = None 
    server_ipv6_subnet: str = None 
    ipv6_enabled: bool = False
    
    # Базы данных
    database_path: str = "./clients.db"
    
    # Резервные копии
    backup_dir: str = "./backups"
    
    # API настройки
    ip_api_url: str = "http://ip-api.com/json"
    ip_api_rate_limit: int = 45 
    
    def __post_init__(self):
        """Инициализация после создания объекта"""
        if self.admin_ids is None:
            # Укажите ваши Telegram ID администраторов
            self.admin_ids = [12345678,123123133]
        
        # Создание директорий если не существуют
        os.makedirs(self.awg_config_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)