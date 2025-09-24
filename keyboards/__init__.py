"""
Клавиатуры для Telegram бота
"""

from .main_keyboards import (
    get_main_menu,
    get_clients_menu,
    get_client_list_keyboard,
    get_client_details_keyboard,
    get_time_limit_keyboard,
    get_traffic_limit_keyboard,
    get_backup_menu,
    get_backup_list_keyboard,
    get_backup_details_keyboard,
    get_confirmation_keyboard
)

__all__ = [
    'get_main_menu',
    'get_clients_menu',
    'get_client_list_keyboard',
    'get_client_details_keyboard',
    'get_time_limit_keyboard',
    'get_traffic_limit_keyboard',
    'get_backup_menu',
    'get_backup_list_keyboard',
    'get_backup_details_keyboard',
    'get_confirmation_keyboard'
]