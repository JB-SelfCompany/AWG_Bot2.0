import re
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Optional, Dict
from database.database import Client


def parse_handshake_to_days(handshake_str: str) -> Optional[float]:
    """
    Парсит строку latest handshake и возвращает количество дней.
    Примеры: "2 minutes, 30 seconds ago", "1 hour, 5 minutes ago", "3 days, 2 hours ago"
    Возвращает None если никогда не подключался или ошибка парсинга.
    """
    if not handshake_str or handshake_str.lower() in ('never', 'никогда', ''):
        return None

    total_seconds = 0

    # Ищем все числа с единицами времени
    patterns = [
        (r'(\d+)\s*(?:second|секунд)', 1),
        (r'(\d+)\s*(?:minute|минут)', 60),
        (r'(\d+)\s*(?:hour|час)', 3600),
        (r'(\d+)\s*(?:day|д[нея])', 86400),
        (r'(\d+)\s*(?:week|недел)', 604800),
        (r'(\d+)\s*(?:month|месяц)', 2592000),
        (r'(\d+)\s*(?:year|год|лет)', 31536000),
    ]

    for pattern, multiplier in patterns:
        match = re.search(pattern, handshake_str, re.IGNORECASE)
        if match:
            total_seconds += int(match.group(1)) * multiplier

    if total_seconds == 0:
        return None

    return total_seconds / 86400  # конвертируем в дни


def get_activity_emoji(client: Client, client_stats: Optional[Dict] = None) -> str:
    """
    Возвращает эмодзи на основе активности клиента:
    🔴 - заблокирован или неактивен
    🟢 - подключался в последние 7 дней
    🟡 - подключался от 7 до 14 дней назад
    🟠 - подключался более 14 дней назад
    ⚪ - никогда не подключался
    """
    # Заблокированные клиенты
    if not client.is_active or client.is_blocked:
        return "🔴"

    # Если нет статистики - показываем как никогда не подключавшегося
    if not client_stats:
        return "⚪"

    handshake_str = client_stats.get('latest handshake', '')
    days = parse_handshake_to_days(handshake_str)

    if days is None:
        return "⚪"  # никогда не подключался
    elif days <= 7:
        return "🟢"  # активен (до 7 дней)
    elif days <= 14:
        return "🟡"  # средняя активность (7-14 дней)
    else:
        return "🟠"  # давно не подключался (более 14 дней)

def get_main_menu() -> InlineKeyboardMarkup:
    """Главное меню бота"""
    builder = InlineKeyboardBuilder()
    
    builder.add(InlineKeyboardButton(
        text="👥 Управление клиентами",
        callback_data="clients_menu"
    ))
    builder.add(InlineKeyboardButton(
        text="📊 Статистика",
        callback_data="stats_menu"
    ))
    builder.add(InlineKeyboardButton(
        text="💾 Резервные копии",
        callback_data="backup_menu"
    ))
    builder.add(InlineKeyboardButton(
        text="⚙️ Параметры",
        callback_data="settings_menu"
    ))
    
    builder.adjust(1)
    return builder.as_markup()

def get_settings_menu() -> InlineKeyboardMarkup:
    """Меню параметров"""
    builder = InlineKeyboardBuilder()
    
    builder.add(InlineKeyboardButton(
        text="🌐 Настроить DNS",
        callback_data="settings_dns"
    ))
    builder.add(InlineKeyboardButton(
        text="📡 Настроить Endpoint",
        callback_data="settings_endpoint"
    ))
    builder.add(InlineKeyboardButton(
        text="📋 Показать настройки",
        callback_data="settings_show"
    ))
    builder.add(InlineKeyboardButton(
        text="🔙 Главное меню",
        callback_data="main_menu"
    ))
    
    builder.adjust(1)
    return builder.as_markup()

def get_endpoint_settings_menu() -> InlineKeyboardMarkup:
    """Меню настроек endpoint"""
    builder = InlineKeyboardBuilder()
    
    builder.add(InlineKeyboardButton(
        text="📝 Установить Endpoint",
        callback_data="set_default_endpoint"
    ))
    builder.add(InlineKeyboardButton(
        text="🗑️ Очистить Endpoint",
        callback_data="clear_default_endpoint"
    ))
    builder.add(InlineKeyboardButton(
        text="🔙 Назад к параметрам",
        callback_data="settings_menu"
    ))
    
    builder.adjust(1)
    return builder.as_markup()

def get_clients_menu() -> InlineKeyboardMarkup:
    """Меню управления клиентами"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="➕ Добавить клиента",
        callback_data="add_client"
    ))
    builder.add(InlineKeyboardButton(
        text="📋 Список клиентов",
        callback_data="list_clients"
    ))
    builder.add(InlineKeyboardButton(
        text="🔍 Поиск клиента", 
        callback_data="search_client"
    ))
    builder.add(InlineKeyboardButton(
        text="🔙 Главное меню",
        callback_data="main_menu"
    ))
    builder.adjust(1)
    return builder.as_markup()

def get_client_list_keyboard(
    clients: List[Client],
    page: int = 0,
    per_page: int = 10,
    stats: Optional[Dict[str, Dict]] = None
) -> InlineKeyboardMarkup:
    """
    Клавиатура со списком клиентов с улучшенной пагинацией.

    Эмодзи активности:
    🔴 - заблокирован или неактивен
    🟢 - подключался в последние 7 дней
    🟡 - подключался от 7 до 14 дней назад
    🟠 - подключался более 14 дней назад
    ⚪ - никогда не подключался
    """
    builder = InlineKeyboardBuilder()
    stats = stats or {}

    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_clients = clients[start_idx:end_idx]

    for client in page_clients:
        client_stats = stats.get(client.public_key)
        status_emoji = get_activity_emoji(client, client_stats)
        builder.add(InlineKeyboardButton(
            text=f"{status_emoji} {client.name}",
            callback_data=f"client_details:{client.id}"
        ))

    # Навигация по страницам
    nav_buttons = []
    total_pages = (len(clients) - 1) // per_page + 1

    if page > 0:
        nav_buttons.append(InlineKeyboardButton(
            text="⏪ Первая",
            callback_data="clients_page:0"
        ))
        nav_buttons.append(InlineKeyboardButton(
            text="◀️ Назад",
            callback_data=f"clients_page:{page-1}"
        ))

    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(
            text="Вперед ▶️",
            callback_data=f"clients_page:{page+1}"
        ))
        nav_buttons.append(InlineKeyboardButton(
            text="Последняя ⏩",
            callback_data=f"clients_page:{total_pages-1}"
        ))

    if len(nav_buttons) == 2:
        builder.row(nav_buttons[0], nav_buttons[1])
    elif len(nav_buttons) == 4:
        builder.row(nav_buttons[0], nav_buttons[1])
        builder.row(nav_buttons[2], nav_buttons[3])
    elif len(nav_buttons) > 0:
        builder.row(*nav_buttons)

    builder.add(InlineKeyboardButton(
        text="🔙 Меню клиентов",
        callback_data="clients_menu"
    ))

    builder.adjust(1)
    return builder.as_markup()

def get_client_details_keyboard(client_id: int) -> InlineKeyboardMarkup:
    """Клавиатура с действиями над клиентом"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="📝 Редактировать",
        callback_data=f"edit_client:{client_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="🔒 Заблокировать/Разблокировать",
        callback_data=f"toggle_block:{client_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="📊 Статистика",
        callback_data=f"client_stats:{client_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="📱 QR-код",
        callback_data=f"client_qr:{client_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="📄 Конфигурация",
        callback_data=f"client_config:{client_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="🌍 IP Соединения",
        callback_data=f"client_ip_info:{client_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="🗑️ Удалить",
        callback_data=f"delete_client:{client_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="🔙 Список клиентов",
        callback_data="list_clients"
    ))
    builder.adjust(2, 2, 2, 1, 1)
    return builder.as_markup()

def get_time_limit_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора временного ограничения с улучшенным выбором"""
    builder = InlineKeyboardBuilder()
    
    # Часы
    builder.add(InlineKeyboardButton(text="⏱️ 1 час", callback_data="time_limit:1h"))
    builder.add(InlineKeyboardButton(text="⏱️ 6 часов", callback_data="time_limit:6h"))
    builder.add(InlineKeyboardButton(text="⏱️ 12 часов", callback_data="time_limit:12h"))
    
    # Дни
    builder.add(InlineKeyboardButton(text="📅 1 день", callback_data="time_limit:1d"))
    builder.add(InlineKeyboardButton(text="📅 3 дня", callback_data="time_limit:3d"))
    builder.add(InlineKeyboardButton(text="📅 7 дней", callback_data="time_limit:7d"))
    
    # Недели
    builder.add(InlineKeyboardButton(text="🗓️ 2 недели", callback_data="time_limit:2w"))
    builder.add(InlineKeyboardButton(text="🗓️ 1 месяц", callback_data="time_limit:1m"))
    
    # Месяцы и годы  
    builder.add(InlineKeyboardButton(text="📆 3 месяца", callback_data="time_limit:3m"))
    builder.add(InlineKeyboardButton(text="📆 6 месяцев", callback_data="time_limit:6m"))
    builder.add(InlineKeyboardButton(text="📆 1 год", callback_data="time_limit:1y"))
    
    builder.add(InlineKeyboardButton(text="⏰ Свой срок", callback_data="time_limit:custom"))
    builder.add(InlineKeyboardButton(text="♾️ Без ограничений", callback_data="time_limit:unlimited"))
    builder.add(InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_add_client"))
    
    builder.adjust(3, 3, 2, 2, 1, 1, 1)
    return builder.as_markup()

def get_custom_time_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора единиц времени"""
    builder = InlineKeyboardBuilder()
    
    builder.add(InlineKeyboardButton(text="⏱️ В часах", callback_data="custom_time_unit:hours"))
    builder.add(InlineKeyboardButton(text="📅 В днях", callback_data="custom_time_unit:days"))
    builder.add(InlineKeyboardButton(text="🗓️ В неделях", callback_data="custom_time_unit:weeks"))
    builder.add(InlineKeyboardButton(text="📆 В месяцах", callback_data="custom_time_unit:months"))
    builder.add(InlineKeyboardButton(text="🗓️ В годах", callback_data="custom_time_unit:years"))
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_time_selection"))
    
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()

def get_traffic_limit_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора ограничения трафика"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="📊 5 GB",
        callback_data="traffic_limit:5"
    ))
    builder.add(InlineKeyboardButton(
        text="📊 10 GB", 
        callback_data="traffic_limit:10"
    ))
    builder.add(InlineKeyboardButton(
        text="📊 30 GB",
        callback_data="traffic_limit:30"
    ))
    builder.add(InlineKeyboardButton(
        text="📊 100 GB",
        callback_data="traffic_limit:100"
    ))
    builder.add(InlineKeyboardButton(
        text="♾️ Без ограничений",
        callback_data="traffic_limit:unlimited"
    ))
    builder.add(InlineKeyboardButton(
        text="🔙 Отмена",
        callback_data="cancel_add_client"
    ))
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()

def get_backup_menu() -> InlineKeyboardMarkup:
    """Меню резервных копий"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="💾 Создать копию", 
        callback_data="create_backup"
    ))
    builder.add(InlineKeyboardButton(
        text="📋 Список копий",
        callback_data="list_backups"
    ))
    builder.add(InlineKeyboardButton(
        text="🔙 Главное меню",
        callback_data="main_menu"
    ))
    builder.adjust(1)
    return builder.as_markup()

def get_backup_list_keyboard(backups: list) -> InlineKeyboardMarkup:
    """Клавиатура со списком резервных копий"""
    builder = InlineKeyboardBuilder()
    for backup in backups[:10]: 
        builder.add(InlineKeyboardButton(
            text=f"📦 {backup['filename']}",
            callback_data=f"backup_details:{backup['filename']}"
        ))
    builder.add(InlineKeyboardButton(
        text="🔙 Меню копий",
        callback_data="backup_menu"
    ))
    builder.adjust(1)
    return builder.as_markup()

def get_backup_details_keyboard(filename: str) -> InlineKeyboardMarkup:
    """Клавиатура действий с резервной копией"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="🔄 Восстановить",
        callback_data=f"restore_backup:{filename}"
    ))
    builder.add(InlineKeyboardButton(
        text="🗑️ Удалить",
        callback_data=f"delete_backup:{filename}"
    ))
    builder.add(InlineKeyboardButton(
        text="🔙 Список копий",
        callback_data="list_backups"
    ))
    builder.adjust(1)
    return builder.as_markup()

def get_confirmation_keyboard(action: str, item_id: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="✅ Да",
        callback_data=f"confirm:{action}:{item_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="❌ Нет",
        callback_data=f"cancel:{action}"
    ))
    builder.adjust(2)
    return builder.as_markup()

def get_edit_client_keyboard(client_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для редактирования клиента"""
    builder = InlineKeyboardBuilder()
    
    builder.add(InlineKeyboardButton(
        text="📝 Изменить имя",
        callback_data=f"edit_name:{client_id}"
    ))
    
    builder.add(InlineKeyboardButton(
        text="📡 Изменить Endpoint",
        callback_data=f"edit_endpoint:{client_id}"
    ))
    
    builder.add(InlineKeyboardButton(
        text="⏰ Изменить срок действия",
        callback_data=f"edit_expiry:{client_id}"
    ))
    
    builder.add(InlineKeyboardButton(
        text="📊 Изменить лимит трафика",
        callback_data=f"edit_traffic_limit:{client_id}"
    ))
    
    builder.add(InlineKeyboardButton(
        text="🔄 Перегенерировать ключи",
        callback_data=f"regenerate_keys:{client_id}"
    ))
    
    builder.add(InlineKeyboardButton(
        text="🔙 Назад к клиенту",
        callback_data=f"client_details:{client_id}"
    ))
    
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()

def get_time_limit_keyboard_for_edit(client_id: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора временного ограничения для редактирования"""
    builder = InlineKeyboardBuilder()
    
    # Часы
    builder.add(InlineKeyboardButton(text="⏱️ 1 час", callback_data=f"edit_time_limit:{client_id}:1h"))
    builder.add(InlineKeyboardButton(text="⏱️ 6 часов", callback_data=f"edit_time_limit:{client_id}:6h"))
    builder.add(InlineKeyboardButton(text="⏱️ 12 часов", callback_data=f"edit_time_limit:{client_id}:12h"))
    
    # Дни
    builder.add(InlineKeyboardButton(text="📅 1 день", callback_data=f"edit_time_limit:{client_id}:1d"))
    builder.add(InlineKeyboardButton(text="📅 3 дня", callback_data=f"edit_time_limit:{client_id}:3d"))
    builder.add(InlineKeyboardButton(text="📅 7 дней", callback_data=f"edit_time_limit:{client_id}:7d"))
    
    # Недели
    builder.add(InlineKeyboardButton(text="🗓️ 2 недели", callback_data=f"edit_time_limit:{client_id}:2w"))
    builder.add(InlineKeyboardButton(text="🗓️ 1 месяц", callback_data=f"edit_time_limit:{client_id}:1m"))
    
    # Месяцы и годы
    builder.add(InlineKeyboardButton(text="📆 3 месяца", callback_data=f"edit_time_limit:{client_id}:3m"))
    builder.add(InlineKeyboardButton(text="📆 6 месяцев", callback_data=f"edit_time_limit:{client_id}:6m"))
    builder.add(InlineKeyboardButton(text="📆 1 год", callback_data=f"edit_time_limit:{client_id}:1y"))
    
    builder.add(InlineKeyboardButton(text="⏰ Свой срок", callback_data=f"edit_time_limit:{client_id}:custom"))
    builder.add(InlineKeyboardButton(text="♾️ Без ограничений", callback_data=f"edit_time_limit:{client_id}:unlimited"))
    
    builder.add(InlineKeyboardButton(text="🔙 Отмена", callback_data=f"edit_client:{client_id}"))
    
    builder.adjust(3, 3, 2, 2, 1, 1, 1)
    return builder.as_markup()

def get_custom_time_keyboard_for_edit(client_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для выбора единиц времени при редактировании"""
    builder = InlineKeyboardBuilder()
    
    builder.add(InlineKeyboardButton(text="⏱️ В часах", callback_data=f"edit_custom_time_unit:{client_id}:hours"))
    builder.add(InlineKeyboardButton(text="📅 В днях", callback_data=f"edit_custom_time_unit:{client_id}:days"))
    builder.add(InlineKeyboardButton(text="🗓️ В неделях", callback_data=f"edit_custom_time_unit:{client_id}:weeks"))
    builder.add(InlineKeyboardButton(text="📆 В месяцах", callback_data=f"edit_custom_time_unit:{client_id}:months"))
    builder.add(InlineKeyboardButton(text="🗓️ В годах", callback_data=f"edit_custom_time_unit:{client_id}:years"))
    
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data=f"edit_expiry:{client_id}"))
    
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()

def get_traffic_limit_keyboard_for_edit(client_id: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора ограничения трафика для редактирования"""
    builder = InlineKeyboardBuilder()
    
    builder.add(InlineKeyboardButton(
        text="📊 5 GB",
        callback_data=f"edit_traffic_value:{client_id}:5"
    ))
    builder.add(InlineKeyboardButton(
        text="📊 10 GB",
        callback_data=f"edit_traffic_value:{client_id}:10"
    ))
    builder.add(InlineKeyboardButton(
        text="📊 30 GB",
        callback_data=f"edit_traffic_value:{client_id}:30"
    ))
    builder.add(InlineKeyboardButton(
        text="📊 100 GB",
        callback_data=f"edit_traffic_value:{client_id}:100"
    ))
    builder.add(InlineKeyboardButton(
        text="♾️ Без ограничений",
        callback_data=f"edit_traffic_value:{client_id}:unlimited"
    ))
    
    builder.add(InlineKeyboardButton(
        text="🔙 Отмена",
        callback_data=f"edit_client:{client_id}"
    ))
    
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()