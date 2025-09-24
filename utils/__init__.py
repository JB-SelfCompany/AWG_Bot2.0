"""
Утилиты для работы бота
"""

from .qr_generator import generate_qr_code
from .formatters import (
    format_client_info,
    format_client_config,
    format_traffic_size,
    format_duration,
    format_datetime,
    format_date,
    format_time,
    truncate_text,
    format_boolean,
    format_percentage,
    format_ip_with_mask
)

__all__ = [
    'generate_qr_code',
    'format_client_info',
    'format_client_config', 
    'format_traffic_size',
    'format_duration',
    'format_datetime',
    'format_date',
    'format_time',
    'truncate_text',
    'format_boolean',
    'format_percentage',
    'format_ip_with_mask'
]