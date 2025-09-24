from datetime import datetime
from typing import Dict, Any, Optional
from database.database import Client


def format_client_info(client: Client, stats: Optional[Dict[str, Any]] = None) -> str:
    """Форматирование информации о клиенте"""
    
    # Статус
    if client.is_blocked:
        status = "🔴 Заблокирован"
    elif not client.is_active:
        status = "⚪ Неактивен"
    else:
        status = "🟢 Активен"
    
    # Проверяем подключение
    is_connected = stats is not None and len(stats) > 0
    connection_status = "🟢 Подключен" if is_connected else "⚪ Не подключен"
    
    # Срок действия
    expires_text = "♾️ Без ограничений"
    if client.expires_at:
        expires_text = client.expires_at.strftime('%d.%m.%Y %H:%M')
        if client.expires_at < datetime.now():
            expires_text += " ❌ Истек"
    
    # Трафик
    traffic_limit_text = "♾️ Без ограничений"
    if client.traffic_limit:
        traffic_limit_text = format_traffic_size(client.traffic_limit)
        used_percent = (client.traffic_used / client.traffic_limit * 100) if client.traffic_limit > 0 else 0
        if used_percent >= 100:
            traffic_limit_text += " ❌ Превышен"
    
    # Статистика подключения
    transfer_info = ""
    last_handshake = ""
    
    if stats:
        transfer = stats.get('transfer', '0 B, 0 B')
        rx_bytes, tx_bytes = transfer.split(', ')
        transfer_info = f"\n📥 Получено: {rx_bytes}\n📤 Отправлено: {tx_bytes}"
        
        handshake = stats.get('latest handshake', 'Никогда')
        last_handshake = f"\n🤝 Последнее подключение: {handshake}"
    
    info_text = f"""👤 <b>Клиент: {client.name}</b>

📊 <b>Статус:</b> {status}
🌐 <b>Подключение:</b> {connection_status}
📱 <b>IP-адрес:</b> {client.ip_address}

⏰ <b>Действует до:</b> {expires_text}
📊 <b>Трафик:</b> {format_traffic_size(client.traffic_used)} / {traffic_limit_text}

📅 <b>Создан:</b> {client.created_at.strftime('%d.%m.%Y %H:%M') if client.created_at else 'Неизвестно'}{transfer_info}{last_handshake}
"""
    
    return info_text


def format_client_config(client_name: str, config_text: str) -> str:
    """Форматирование конфигурации клиента"""
    return f"""📄 <b>Конфигурация для {client_name}</b>

<pre>{config_text}</pre>

💾 Сохраните этот текст в файл с расширением .conf
📱 Или импортируйте через QR-код в приложении AmneziaVPN
"""


def format_traffic_size(bytes_count: int) -> str:
    """Форматирование размера трафика"""
    if bytes_count == 0:
        return "0 B"
    
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0
    size = float(bytes_count)
    
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.2f} {units[unit_index]}"


def format_duration(seconds: int) -> str:
    """Форматирование длительности в секундах"""
    if seconds < 60:
        return f"{seconds} сек"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} мин"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}ч {minutes}м"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}д {hours}ч"


def format_datetime(dt: datetime) -> str:
    """Форматирование даты и времени"""
    return dt.strftime('%d.%m.%Y %H:%M')


def format_date(dt: datetime) -> str:
    """Форматирование только даты"""
    return dt.strftime('%d.%m.%Y')


def format_time(dt: datetime) -> str:
    """Форматирование только времени"""
    return dt.strftime('%H:%M')


def truncate_text(text: str, max_length: int = 30) -> str:
    """Обрезка текста с добавлением троеточия"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def format_boolean(value: bool, true_text: str = "Да", false_text: str = "Нет") -> str:
    """Форматирование булевого значения"""
    return true_text if value else false_text


def format_percentage(value: float) -> str:
    """Форматирование процентов"""
    return f"{value:.1f}%"


def format_ip_with_mask(ip: str, mask: int = 32) -> str:
    """Форматирование IP с маской"""
    return f"{ip}/{mask}"
