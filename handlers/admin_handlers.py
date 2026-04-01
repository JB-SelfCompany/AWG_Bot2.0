import logging
import ipaddress
from datetime import datetime, timedelta
from typing import Optional
import json
import re

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import Config
from database.database import get_db, Client
from services.awg_manager import AWGManager
from services.ip_service import IPService
from services.backup_service import BackupService
from services.settings_service import SettingsService
from keyboards.main_keyboards import *
from utils.qr_generator import generate_qr_code
from utils.vpn_converter import conf_to_vpn_url
from utils.formatters import format_client_info, format_client_config, format_traffic_size

admin_router = Router()

# Инициализация сервисов
config = Config()
awg_manager = AWGManager(config)
ip_service = IPService(config)
backup_service = BackupService(config)
db = get_db()
settings_service = SettingsService()
logger = logging.getLogger(__name__)

# Глобальная переменная для хранения ID последнего сообщения каждого пользователя
user_last_message = {}

class ClientStates(StatesGroup):
    """Состояния для создания клиента"""
    waiting_name = State()
    waiting_endpoint = State()
    waiting_custom_time = State()
    waiting_custom_time_value = State()
    waiting_client_search = State()
    waiting_ipv6_choice = State()

class EditClientStates(StatesGroup):
    """Состояния для редактирования клиента"""
    waiting_new_name = State()
    waiting_new_endpoint = State()
    waiting_new_traffic_limit = State()
    waiting_edit_time_value = State()
    waiting_edit_time_unit = State()

class SettingsStates(StatesGroup):
    """Состояния для настройки параметров"""
    waiting_dns = State()
    waiting_endpoint = State()

@admin_router.callback_query(F.data == "settings_menu")
async def show_settings_menu(callback: CallbackQuery):
    """Показать меню параметров"""
    await edit_or_send_message(
        callback,
        "⚙️ Параметры бота\n\n"
        "Здесь можно настроить параметры по умолчанию:",
        reply_markup=get_settings_menu()
    )
    await callback.answer()

@admin_router.callback_query(F.data == "settings_show")
async def show_settings_info(callback: CallbackQuery):
    """Показать текущие настройки"""
    dns = await settings_service.get_default_dns()
    endpoint = await settings_service.get_default_endpoint()
    
    endpoint_text = endpoint if endpoint else "Не установлен (будет спрашиваться)"
    
    await edit_or_send_message(
        callback,
        f"📋 Текущие настройки:\n\n"
        f"🌐 DNS серверы: {dns}\n"
        f"📡 Endpoint по умолчанию: {endpoint_text}",
        reply_markup=get_settings_menu()
    )
    await callback.answer()

@admin_router.callback_query(F.data == "settings_dns")
async def start_dns_setup(callback: CallbackQuery, state: FSMContext):
    """Начать настройку DNS"""
    current_dns = await settings_service.get_default_dns()
    
    await edit_or_send_message(
        callback,
        f"🌐 Настройка DNS серверов\n\n"
        f"Текущие DNS: {current_dns}\n\n"
        f"Введите новые DNS серверы через запятую:\n"
        f"Например: 1.1.1.1, 8.8.8.8",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Отмена", callback_data="settings_menu")
        ]])
    )
    await state.set_state(SettingsStates.waiting_dns)
    await callback.answer()

@admin_router.message(StateFilter(SettingsStates.waiting_dns))
async def process_dns_setup(message: Message, state: FSMContext):
    """Обработка настройки DNS"""
    dns_servers = message.text.strip()
    user_id = message.from_user.id
    
    try:
        await message.delete()
    except:
        pass
    
    if not settings_service.validate_dns_servers(dns_servers):
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text="❌ Некорректные DNS серверы\n\n"
                         "Введите IP-адреса DNS серверов через запятую:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 Отмена", callback_data="settings_menu")
                    ]])
                )
            except:
                pass
        return
    
    success = await settings_service.set_default_dns(dns_servers)
    await state.clear()
    
    if success:
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text=f"✅ DNS серверы обновлены!\n\n"
                         f"Новые DNS: {dns_servers}\n\n"
                         f"Все новые клиенты будут использовать эти DNS серверы.",
                    reply_markup=get_settings_menu()
                )
            except:
                pass

@admin_router.callback_query(F.data == "settings_endpoint")
async def show_endpoint_settings(callback: CallbackQuery):
    """Показать настройки endpoint"""
    current_endpoint = await settings_service.get_default_endpoint()
    endpoint_text = current_endpoint if current_endpoint else "Не установлен"
    
    await edit_or_send_message(
        callback,
        f"📡 Настройки Endpoint\n\n"
        f"Текущий Endpoint по умолчанию: {endpoint_text}\n\n"
        f"Если Endpoint установлен, он будет автоматически подставляться "
        f"всем новым клиентам. Если не установлен, будет спрашиваться при создании клиента.",
        reply_markup=get_endpoint_settings_menu()
    )
    await callback.answer()

@admin_router.callback_query(F.data == "set_default_endpoint")
async def start_endpoint_setup(callback: CallbackQuery, state: FSMContext):
    """Начать настройку endpoint по умолчанию"""
    current_endpoint = await settings_service.get_default_endpoint()
    
    endpoint_text = current_endpoint if current_endpoint else "не установлен"
    
    await edit_or_send_message(
        callback,
        f"📡 Настройка Endpoint по умолчанию\n\n"
        f"Текущий Endpoint: {endpoint_text}\n\n"
        f"Введите IP-адрес или домен сервера:\n"
        f"Примеры:\n"
        f"• vpn.example.com\n"
        f"• my-server.ru",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Отмена", callback_data="settings_endpoint")
        ]])
    )
    await state.set_state(SettingsStates.waiting_endpoint)
    await callback.answer()

@admin_router.message(StateFilter(SettingsStates.waiting_endpoint))
async def process_endpoint_setup(message: Message, state: FSMContext):
    """Обработка настройки endpoint"""
    endpoint = message.text.strip()
    user_id = message.from_user.id
    
    try:
        await message.delete()
    except:
        pass
    
    if not settings_service.validate_endpoint(endpoint):
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text="❌ Некорректный Endpoint\n\n"
                         "Введите корректный IP-адрес или домен:\n"
                         "Примеры: 192.168.1.100, vpn.example.com",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 Отмена", callback_data="settings_endpoint")
                    ]])
                )
            except:
                pass
        return
    
    success = await settings_service.set_default_endpoint(endpoint)
    await state.clear()
    
    if success:
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text=f"✅ Endpoint по умолчанию установлен!\n\n"
                         f"Новый Endpoint: {endpoint}\n\n"
                         f"Теперь все новые клиенты будут автоматически использовать "
                         f"этот Endpoint. Вам больше не нужно будет вводить его при создании клиентов.",
                    reply_markup=get_endpoint_settings_menu()
                )
            except:
                pass

@admin_router.callback_query(F.data == "clear_default_endpoint")
async def clear_endpoint_confirm(callback: CallbackQuery):
    """Подтверждение очистки endpoint по умолчанию"""
    current_endpoint = await settings_service.get_default_endpoint()
    
    if not current_endpoint:
        await edit_or_send_message(
            callback,
            "📡 Endpoint по умолчанию не установлен\n\n"
            "Нечего очищать.",
            reply_markup=get_endpoint_settings_menu()
        )
    else:
        await edit_or_send_message(
            callback,
            f"📡 Очистка Endpoint по умолчанию\n\n"
            f"Текущий Endpoint: {current_endpoint}\n\n"
            f"После очистки при создании новых клиентов "
            f"вам снова нужно будет вводить Endpoint вручную.\n\n"
            f"Подтвердите действие:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="✅ Да, очистить", 
                    callback_data="confirm_clear_endpoint"
                )],
                [InlineKeyboardButton(
                    text="🔙 Отмена", 
                    callback_data="settings_endpoint"
                )]
            ])
        )
    await callback.answer()

@admin_router.callback_query(F.data == "confirm_clear_endpoint")
async def confirm_clear_endpoint(callback: CallbackQuery):
    """Подтвердить очистку endpoint"""
    success = await settings_service.set_default_endpoint("")
    
    if success:
        await edit_or_send_message(
            callback,
            "✅ Endpoint по умолчанию очищен!\n\n"
            "Теперь при создании новых клиентов вам снова нужно будет "
            "вводить Endpoint вручную.",
            reply_markup=get_endpoint_settings_menu()
        )
    else:
        await edit_or_send_message(
            callback,
            "❌ Ошибка при очистке Endpoint",
            reply_markup=get_endpoint_settings_menu()
        )
    await callback.answer()

async def update_client_traffic_usage(client: Client, stats: dict) -> None:
    """Обновление использования трафика клиента из статистики AWG"""
    if not stats:
        return
    
    transfer = stats.get('transfer', '0 B, 0 B')
    try:
        rx_str, tx_str = transfer.split(', ')
        
        def parse_traffic_size(size_str: str) -> int:
            size_str = size_str.strip()
            if 'received' in size_str:
                size_str = size_str.replace(' received', '')
            if 'sent' in size_str:
                size_str = size_str.replace(' sent', '')
            
            parts = size_str.split()
            if len(parts) != 2:
                return 0
            
            value = float(parts[0])
            unit = parts[1].upper()
            
            multipliers = {
                'B': 1,
                'KIB': 1024,
                'MIB': 1024**2,
                'GIB': 1024**3,
                'TIB': 1024**4,
                'KB': 1000,
                'MB': 1000**2,
                'GB': 1000**3,
                'TB': 1000**4
            }
            
            return int(value * multipliers.get(unit, 1))
        
        rx_bytes = parse_traffic_size(rx_str)
        tx_bytes = parse_traffic_size(tx_str)
        total_bytes = rx_bytes + tx_bytes
        
        if total_bytes != client.traffic_used:
            client.traffic_used = total_bytes
            await db.update_client(client)
            
    except Exception as e:
        logger.error(f"Ошибка при парсинге трафика: {e}")

async def edit_or_send_message(callback: CallbackQuery, text: str, reply_markup=None):
    """Универсальная функция для редактирования или отправки сообщения"""
    user_id = callback.from_user.id
    
    try:
        if callback.message:
            await callback.message.edit_text(text, reply_markup=reply_markup)
            user_last_message[user_id] = callback.message.message_id
        else:
            new_message = await callback.bot.send_message(
                chat_id=callback.from_user.id,
                text=text,
                reply_markup=reply_markup
            )
            user_last_message[user_id] = new_message.message_id
    except Exception as e:
        logger.error(f"Ошибка при редактировании сообщения: {e}")
        try:
            new_message = await callback.bot.send_message(
                chat_id=callback.from_user.id,
                text=text,
                reply_markup=reply_markup
            )
            user_last_message[user_id] = new_message.message_id
        except Exception as e2:
            logger.error(f"Критическая ошибка при отправке сообщения: {e2}")

async def edit_or_send_photo(callback: CallbackQuery, photo, caption: str = ""):
    """Универсальная функция для отправки фото с динамическим редактированием"""
    user_id = callback.from_user.id
    
    try:
        if user_id in user_last_message:
            try:
                await callback.bot.delete_message(
                    chat_id=user_id,
                    message_id=user_last_message[user_id]
                )
            except:
                pass
        
        new_message = await callback.bot.send_photo(
            chat_id=user_id,
            photo=photo,
            caption=caption
        )
        user_last_message[user_id] = new_message.message_id
        
    except Exception as e:
        logger.error(f"Ошибка при отправке фото: {e}")

# Команда /start
@admin_router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    user_last_message[message.from_user.id] = message.message_id
    
    await message.answer(
        "🤖 AmneziaWG Management Bot\n\n"
        "Добро пожаловать в бота для управления AmneziaWG сервером!\n"
        "Выберите действие из меню ниже:",
        reply_markup=get_main_menu()
    )

# Главное меню
@admin_router.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery):
    """Показать главное меню"""
    await edit_or_send_message(
        callback,
        "🤖 AmneziaWG Management Bot\n\n"
        "Выберите действие из меню ниже:",
        reply_markup=get_main_menu()
    )
    await callback.answer()

# Меню клиентов
@admin_router.callback_query(F.data == "clients_menu")
async def show_clients_menu(callback: CallbackQuery):
    """Показать меню управления клиентами"""
    clients = await db.get_all_clients()
    active_count = len([c for c in clients if c.is_active and not c.is_blocked])
    blocked_count = len([c for c in clients if c.is_blocked])
    
    await edit_or_send_message(
        callback,
        f"👥 Управление клиентами\n\n"
        f"📊 Всего клиентов: {len(clients)}\n"
        f"🟢 Активных: {active_count}\n"
        f"🔴 Заблокированных: {blocked_count}",
        reply_markup=get_clients_menu()
    )
    await callback.answer()

# Добавление клиента - шаг 1: ввод имени
@admin_router.callback_query(F.data == "add_client")
async def start_add_client(callback: CallbackQuery, state: FSMContext):
    """Начать процесс добавления клиента"""
    # Проверяем есть ли endpoint по умолчанию
    default_endpoint = await settings_service.get_default_endpoint()
    
    if default_endpoint:
        # Если есть endpoint по умолчанию, сохраняем его и переходим к выбору времени
        await state.update_data(endpoint=default_endpoint)
        
        await edit_or_send_message(
            callback,
            f"➕ Добавление нового клиента\n\n"
            f"📡 Endpoint: {default_endpoint} (из настроек)\n\n"
            f"Введите имя клиента:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Отмена", callback_data="clients_menu")
            ]])
        )
        await state.set_state(ClientStates.waiting_name)
    else:
        # Если нет endpoint по умолчанию, показываем стандартное сообщение
        await edit_or_send_message(
            callback,
            "➕ Добавление нового клиента\n\n"
            "Введите имя клиента:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Отмена", callback_data="clients_menu")
            ]])
        )
        await state.set_state(ClientStates.waiting_name)
    
    await callback.answer()

# Обработка имени клиента с динамическим сообщением
@admin_router.message(StateFilter(ClientStates.waiting_name))
async def process_client_name(message: Message, state: FSMContext):
    """Обработка имени клиента с динамическим редактированием"""
    name = message.text.strip()
    user_id = message.from_user.id
    
    try:
        await message.delete()
    except:
        pass
    
    if not name or len(name) < 2 or len(name) > 32:
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text="➕ Добавление нового клиента\n\n"
                         "❌ Имя должно содержать от 2 до 32 символов\n\n"
                         "Введите корректное имя клиента:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 Отмена", callback_data="clients_menu")
                    ]])
                )
            except:
                pass
        return
    
    if not name.replace('-', '').replace('_', '').replace('.', '').isalnum():
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text="➕ Добавление нового клиента\n\n"
                         "❌ Имя может содержать только латинские буквы, цифры и символы - _ .\n\n"
                         "Введите корректное имя клиента:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 Отмена", callback_data="clients_menu")
                    ]])
                )
            except:
                pass
        return
    
    # Проверка уникальности
    existing_client = await db.get_client_by_name(name)
    if existing_client:
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text="➕ Добавление нового клиента\n\n"
                         "❌ Клиент с таким именем уже существует\n\n"
                         "Введите другое имя клиента:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 Отмена", callback_data="clients_menu")
                    ]])
                )
            except:
                pass
        return
    
    await state.update_data(name=name)
    
    state_data = await state.get_data()

    if config.ipv6_enabled and config.server_ipv6_subnet:
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text="➕ Добавление нового клиента\n\n"
                         "Добавить IPv6?\n\n",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="✅ Да", callback_data="ipv6yes")],
                        [InlineKeyboardButton(text="❌ Нет", callback_data="ipv6no")],
                        [InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_addclient")]
                    ])
                )
            except Exception:
                pass
        await state.set_state(ClientStates.waiting_ipv6_choice)
        return

    if "endpoint" in state_data:
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text=f"<b>{name}</b>\nEndpoint: <code>{state_data['endpoint']}</code>",
                    reply_markup=get_time_limit_keyboard()
                )
            except Exception:
                pass
        return

    if user_id in user_last_message:
        try:
            await message.bot.edit_message_text(
                chat_id=user_id,
                message_id=user_last_message[user_id],
                text=f"➕ Добавление нового клиента\n\n"
                     f"✅ Имя клиента: {name}\n\n"
                     f"Введите endpoint (IP-адрес или домен сервера):",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_add_client")
                ]])
            )
        except:
            pass
    
    await state.set_state(ClientStates.waiting_endpoint)

@admin_router.callback_query(F.data.in_({"ipv6yes", "ipv6no"}), StateFilter(ClientStates.waiting_ipv6_choice))
async def process_ipv6_choice(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора IPv6"""
    has_ipv6 = callback.data == "ipv6yes"
    await state.update_data(has_ipv6=has_ipv6)
    
    state_data = await state.get_data()
    name = state_data.get("name")
    
    # Получаем endpoint из state_data
    endpoint = state_data.get("endpoint")
    
    # Если endpoint уже задан в настройках по умолчанию
    if endpoint:
        await edit_or_send_message(
            callback,
            f"➕ Добавление нового клиента\n\n"
            f"✅ Имя: {name}\n"
            f"✅ Endpoint: {endpoint}\n\n"
            f"Выберите срок действия:",
            reply_markup=get_time_limit_keyboard()
        )
    else:
        # Нужно запросить endpoint
        await edit_or_send_message(
            callback,
            f"➕ Добавление нового клиента\n\n"
            f"✅ Имя: {name}\n"
            f"Введите Endpoint (IP-адрес или домен сервера):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_addclient")]
            ])
        )
        await state.set_state(ClientStates.waiting_endpoint)
    
    await callback.answer()

# Обработка endpoint с динамическим сообщением
@admin_router.message(StateFilter(ClientStates.waiting_endpoint))
async def process_client_endpoint(message: Message, state: FSMContext):
    """Обработка endpoint клиента с динамическим редактированием"""
    endpoint = message.text.strip()
    user_id = message.from_user.id
    
    try:
        await message.delete()
    except:
        pass
    
    if not endpoint:
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text="➕ Добавление нового клиента\n\n"
                         "❌ Endpoint не может быть пустым\n\n"
                         "Введите Endpoint (IP-адрес или домен сервера):",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_add_client")
                    ]])
                )
            except:
                pass
        return
    
    await state.update_data(endpoint=endpoint)
    
    if user_id in user_last_message:
        try:
            await message.bot.edit_message_text(
                chat_id=user_id,
                message_id=user_last_message[user_id],
                text=f"➕ Добавление нового клиента\n\n"
                     f"✅ Endpoint: {endpoint}\n\n"
                     f"Выберите срок действия конфигурации:",
                reply_markup=get_time_limit_keyboard()
            )
        except:
            pass

# Обработка выбора временного ограничения с улучшенной логикой
@admin_router.callback_query(F.data.startswith("time_limit:"))
async def process_time_limit(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора временного ограничения"""
    time_limit = callback.data.split(":", 1)[1]
    
    if time_limit == "custom":
        await edit_or_send_message(
            callback,
            "⏰ Выберите единицу времени для своего срока:",
            reply_markup=get_custom_time_keyboard()
        )
        await callback.answer()
        return
    
    # Вычисляем дату окончания
    expires_at = None
    if time_limit != "unlimited":
        now = datetime.now()
        
        # Часы
        if time_limit.endswith('h'):
            hours = int(time_limit[:-1])
            expires_at = now + timedelta(hours=hours)
        # Дни
        elif time_limit.endswith('d'):
            days = int(time_limit[:-1])
            expires_at = now + timedelta(days=days)
        # Недели  
        elif time_limit.endswith('w'):
            weeks = int(time_limit[:-1])
            expires_at = now + timedelta(weeks=weeks)
        # Месяцы
        elif time_limit.endswith('m'):
            months = int(time_limit[:-1])
            expires_at = now + timedelta(days=months * 30)
        # Годы
        elif time_limit.endswith('y'):
            years = int(time_limit[:-1])
            expires_at = now + timedelta(days=years * 365)
    
    await state.update_data(expires_at=expires_at)
    
    expires_text = "Без ограничений" if expires_at is None else expires_at.strftime('%d.%m.%Y %H:%M')
    await edit_or_send_message(
        callback,
        f"➕ Добавление нового клиента\n\n"
        f"✅ Срок действия: {expires_text}\n\n"
        f"Выберите ограничение трафика:",
        reply_markup=get_traffic_limit_keyboard()
    )
    await callback.answer()

# Обработка выбора единиц времени для custom времени
@admin_router.callback_query(F.data.startswith("custom_time_unit:"))
async def process_custom_time_unit(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора единиц времени"""
    time_unit = callback.data.split(":", 1)[1]
    await state.update_data(custom_time_unit=time_unit)
    
    unit_names = {
        'hours': 'часов',
        'days': 'дней', 
        'weeks': 'недель',
        'months': 'месяцев',
        'years': 'лет'
    }
    
    await edit_or_send_message(
        callback,
        f"⏰ Введите количество {unit_names.get(time_unit, time_unit)}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_add_client")
        ]])
    )
    await state.set_state(ClientStates.waiting_custom_time_value)
    await callback.answer()

# Возврат к выбору времени
@admin_router.callback_query(F.data == "back_to_time_selection")
async def back_to_time_selection(callback: CallbackQuery):
    """Возврат к выбору временного ограничения"""
    await edit_or_send_message(
        callback,
        "⏰ Выберите срок действия конфигурации:",
        reply_markup=get_time_limit_keyboard()
    )
    await callback.answer()

# Обработка пользовательского времени
@admin_router.message(StateFilter(ClientStates.waiting_custom_time_value))
async def process_custom_time_value(message: Message, state: FSMContext):
    """Обработка значения пользовательского времени"""
    user_id = message.from_user.id
    
    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except:
        pass
    
    try:
        value = int(message.text.strip())
        if value <= 0 or value > 1000:
            raise ValueError()
            
        data = await state.get_data()
        time_unit = data.get('custom_time_unit', 'days')
        
        now = datetime.now()
        expires_at = None
        
        if time_unit == 'hours':
            expires_at = now + timedelta(hours=value)
        elif time_unit == 'days':
            expires_at = now + timedelta(days=value)
        elif time_unit == 'weeks':
            expires_at = now + timedelta(weeks=value)
        elif time_unit == 'months':
            expires_at = now + timedelta(days=value * 30)
        elif time_unit == 'years':
            expires_at = now + timedelta(days=value * 365)
        
        await state.update_data(expires_at=expires_at)
        
        # Обновляем сообщение с успехом
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text=f"➕ Добавление нового клиента\n\n"
                         f"✅ Срок действия: {expires_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                         f"Выберите ограничение трафика:",
                    reply_markup=get_traffic_limit_keyboard()
                )
            except:
                pass
                
    except ValueError:
        # Ошибка - обновляем сообщение
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text="⏰ Ошибка!\n\n"
                         "❌ Введите корректное число (от 1 до 1000):",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_add_client")
                    ]])
                )
            except:
                pass

# Обработка выбора ограничения трафика  
@admin_router.callback_query(F.data.startswith("traffic_limit:"))
async def process_traffic_limit(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора ограничения трафика"""
    traffic_limit = callback.data.split(":", 1)[1]
    
    # Конвертируем в байты
    traffic_limit_bytes = None
    if traffic_limit != "unlimited":
        gb_limit = int(traffic_limit) 
        traffic_limit_bytes = gb_limit * 1024 * 1024 * 1024
    
    await state.update_data(traffic_limit=traffic_limit_bytes)
    
    # Получаем все данные и создаем клиента
    data = await state.get_data()
    name = data.get("name")
    endpoint = data.get("endpoint")
    expires_at = data.get("expires_at")

    try:
        # Генерируем ключи
        private_key, public_key, preshared_key = awg_manager.generate_keypair_with_preshared()
        
        ip_address = await awg_manager.get_next_available_ip()

        data = await state.get_data()

        ipv6_address = ""
        has_ipv6 = data.get("has_ipv6", False)

        if has_ipv6 and config.ipv6_enabled:
            ipv6_address = await awg_manager.get_next_available_ipv6()
            if not ipv6_address:
                await editor_send_message(
                    callback,
                    "❌ Не удалось получить свободный IPv6-адрес.\n\n"
                    "Клиент будет создан только с IPv4.",
                    reply_markup=get_clients_menu()
                )
                has_ipv6 = False

        if not ip_address:
            await edit_or_send_message(
                callback,
                "❌ Не удалось получить свободный IP-адрес",
                reply_markup=get_clients_menu()
            )
            await state.clear()
            await callback.answer()
            return
        
        # Создаем клиента
        client = Client(
            name=name,
            public_key=public_key,
            private_key=private_key,
            preshared_key=preshared_key,
            ip_address=ip_address,
            ipv6_address=ipv6_address,
            has_ipv6=has_ipv6,
            endpoint=endpoint,
            expires_at=expires_at,
            traffic_limit=traffic_limit_bytes,
            is_active=True,
            is_blocked=False
        )
        
        # Сохраняем в базу
        client_id = await db.add_client(client)
        client.id = client_id
        
        # Добавляем на сервер
        success = await awg_manager.add_peer_to_server(client)
        
        if success:
            traffic_text = "Без ограничений" if traffic_limit == "unlimited" else f"{traffic_limit} GB"
            expires_text = "Без ограничений" if client.expires_at is None else client.expires_at.strftime('%d.%m.%Y %H:%M')
            
            ipv6_info = f"\n🌐 IPv6: {client.ipv6_address}" if client.has_ipv6 and client.ipv6_address else ""

            await edit_or_send_message(
                callback,
                f"✅ Клиент успешно создан!\n\n"
                f"👤 Имя: {client.name}\n"
                f"📡 IP: {client.ip_address}{ipv6_info}\n"
                f"🔐 Preshared Key добавлен\n"
                f"⏱ Срок действия: {expires_text}\n"
                f"📊 Трафик: {traffic_text}\n\n"
                f"✅ Клиент добавлен на сервер.",
                reply_markup=get_client_details_keyboard(client.id)
            )

        else:
            # Удаляем из базы если не удалось добавить на сервер
            await db.delete_client(client_id)
            await edit_or_send_message(
                callback,
                "❌ Ошибка при добавлении клиента на сервер",
                reply_markup=get_clients_menu()
            )
        
    except Exception as e:
        logger.error(f"Ошибка при создании клиента: {e}")
        await edit_or_send_message(
            callback,
            "❌ Произошла ошибка при создании клиента",
            reply_markup=get_clients_menu()
        )
    
    await state.clear()
    await callback.answer()

# Отмена добавления клиента
@admin_router.callback_query(F.data == "cancel_add_client")
async def cancel_add_client(callback: CallbackQuery, state: FSMContext):
    """Отмена добавления клиента"""
    await state.clear()
    await edit_or_send_message(
        callback,
        "❌ Добавление клиента отменено",
        reply_markup=get_clients_menu()
    )
    await callback.answer()

# Список клиентов с улучшенной пагинацией
@admin_router.callback_query(F.data == "list_clients")
@admin_router.callback_query(F.data.startswith("clients_page:"))
async def show_clients_list(callback: CallbackQuery):
    """Показать список клиентов с пагинацией"""
    page = 0
    if callback.data.startswith("clients_page:"):
        page = int(callback.data.split(":", 1)[1])

    clients = await db.get_all_clients()
    if not clients:
        await edit_or_send_message(
            callback,
            "📋 Список клиентов\n\n"
            "Клиенты не найдены",
            reply_markup=get_clients_menu()
        )
        await callback.answer()
        return

    # Получаем статистику AWG для определения активности клиентов
    stats = await awg_manager.get_interface_stats()

    per_page = 10
    total_pages = (len(clients) - 1) // per_page + 1

    # Проверяем корректность страницы
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1

    await edit_or_send_message(
        callback,
        f"📋 Список клиентов\n\n"
        f"Страница {page + 1} из {total_pages}\n"
        f"Всего клиентов: {len(clients)}\n\n"
        f"🟢 до 7 дн · 🟡 7-14 дн · 🟠 >14 дн · ⚪ нет · 🔴 блок",
        reply_markup=get_client_list_keyboard(clients, page, per_page, stats)
    )
    await callback.answer()

# Детали клиента - с поддержкой перехода от QR-кода и обновлением трафика
@admin_router.callback_query(F.data.startswith("client_details:"))
async def show_client_details(callback: CallbackQuery):
    """Показать детали клиента"""
    client_id = int(callback.data.split(":", 1)[1])
    client = await db.get_client(client_id)
    
    if not client:
        await edit_or_send_message(
            callback,
            "❌ Клиент не найден",
            reply_markup=get_clients_menu()
        )
        await callback.answer()
        return
    
    # Получаем статистику
    stats = await awg_manager.get_interface_stats()
    client_stats = stats.get(client.public_key, {})
    
    # Обновляем трафик клиента из статистики
    await update_client_traffic_usage(client, client_stats)
    
    # Получаем обновленного клиента из БД
    client = await db.get_client(client_id)
    
    info_text = format_client_info(client, client_stats)
    
    user_id = callback.from_user.id
    
    # Если предыдущее сообщение было с фото (QR-код), удаляем его и отправляем новое
    try:
        if callback.message and callback.message.photo:
            await callback.bot.delete_message(
                chat_id=user_id,
                message_id=callback.message.message_id
            )
            new_message = await callback.bot.send_message(
                chat_id=user_id,
                text=info_text,
                reply_markup=get_client_details_keyboard(client_id)
            )
            user_last_message[user_id] = new_message.message_id
        else:
            await edit_or_send_message(
                callback,
                info_text,
                reply_markup=get_client_details_keyboard(client_id)
            )
    except Exception as e:
        logger.error(f"Ошибка при обработке перехода от QR: {e}")
        new_message = await callback.bot.send_message(
            chat_id=user_id,
            text=info_text,
            reply_markup=get_client_details_keyboard(client_id)
        )
        user_last_message[user_id] = new_message.message_id
    
    await callback.answer()

# Редактирование клиента
@admin_router.callback_query(F.data.startswith("edit_client:"))
async def show_edit_client_menu(callback: CallbackQuery):
    """Показать меню редактирования клиента"""
    client_id = int(callback.data.split(":", 1)[1])
    client = await db.get_client(client_id)
    
    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
        
    await edit_or_send_message(
        callback,
        f"✏️ Редактирование клиента {client.name}\n\n"
        f"Выберите что хотите изменить:",
        reply_markup=get_edit_client_keyboard(client_id)
    )
    await callback.answer()

# Блокировка/разблокировка клиента
@admin_router.callback_query(F.data.startswith("toggle_block:"))
async def toggle_client_block(callback: CallbackQuery):
    """Заблокировать/разблокировать клиента"""
    client_id = int(callback.data.split(":", 1)[1])
    client = await db.get_client(client_id)
    
    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    # Переключаем статус блокировки
    client.is_blocked = not client.is_blocked
    
    if client.is_blocked:
        # Блокируем - удаляем с сервера
        success = await awg_manager.remove_peer_from_server(client.public_key)
        action = "заблокирован"
    else:
        # Разблокируем - добавляем на сервер  
        success = await awg_manager.add_peer_to_server(client)
        action = "разблокирован"
    
    if success:
        await db.update_client(client)
        await callback.answer(f"✅ Клиент {action}", show_alert=True)
        
        # Обновляем информацию
        stats = await awg_manager.get_interface_stats()
        client_stats = stats.get(client.public_key, {})
        info_text = format_client_info(client, client_stats)
        
        await edit_or_send_message(
            callback,
            info_text,
            reply_markup=get_client_details_keyboard(client_id)
        )
    else:
        await callback.answer(f"❌ Ошибка при изменении статуса клиента", show_alert=True)

# Конфигурация клиента - с отправкой .conf файла
@admin_router.callback_query(F.data.startswith("client_config:"))
async def send_client_config(callback: CallbackQuery):
    """Отправить конфигурацию клиента с файлом .conf"""
    client_id = int(callback.data.split(":", 1)[1])
    client = await db.get_client(client_id)
    
    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    user_id = callback.from_user.id
    
    try:
        from utils.vpn_converter import conf_to_vpn_url
        from aiogram.types import BufferedInputFile
        
        # Генерируем конфигурацию
        config_text = await awg_manager.create_client_config(client)
        
        # Генерируем vpn:// URL
        try:
            vpn_url = conf_to_vpn_url(config_text)
        except Exception as e:
            logger.error(f"Ошибка при конвертации в vpn://: {e}")
            vpn_url = "Ошибка генерации vpn:// строки"
        
        formatted_config = format_client_config(client.name, config_text)
        
        # Создаем полное сообщение с HTML форматированием
        full_message = f"{formatted_config}\n\n" \
                      f"🔗 VPN URL для внешних приложений:\n" \
                      f"<pre>{vpn_url}</pre>"
        
        if user_id in user_last_message:
            try:
                await callback.bot.delete_message(
                    chat_id=user_id,
                    message_id=user_last_message[user_id]
                )
            except Exception as e:
                logger.debug(f"Не удалось удалить предыдущее сообщение: {e}")
        
        sent_message = await callback.bot.send_message(
            chat_id=user_id,
            text=full_message,
            parse_mode="HTML"
        )
        
        # Обновляем ID последнего сообщения
        user_last_message[user_id] = sent_message.message_id
        
        # Создаем .conf файл
        conf_filename = f"{client.name}.conf"
        conf_file = BufferedInputFile(
            file=config_text.encode('utf-8'),
            filename=conf_filename
        )
        
        # Отправляем файл конфигурации
        await callback.bot.send_document(
            chat_id=user_id,
            document=conf_file,
            caption=f"📄 Конфигурационный файл для {client.name}\n\n"
                   f"Импортируйте этот файл в приложение AmneziaWG",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="🔙 Назад к клиенту",
                    callback_data=f"back_from_config:{client_id}"
                )
            ]])
        )
        
        await callback.answer("✅ Конфигурация отправлена")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке конфигурации: {e}")
        await callback.answer("❌ Ошибка при генерации конфигурации", show_alert=True)


# Возврат из конфигурации к карточке клиента
@admin_router.callback_query(F.data.startswith("back_from_config:"))
async def back_from_config(callback: CallbackQuery):
    """Вернуться к карточке клиента из конфигурации"""
    client_id = int(callback.data.split(":", 1)[1])
    client = await db.get_client(client_id)
    
    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    user_id = callback.from_user.id
    
    try:
        await callback.message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение с файлом: {e}")
    
    if user_id in user_last_message:
        try:
            await callback.bot.delete_message(
                chat_id=user_id,
                message_id=user_last_message[user_id]
            )
        except Exception as e:
            logger.debug(f"Не удалось удалить текстовое сообщение: {e}")
    
    # Получаем статистику клиента
    stats = await awg_manager.get_interface_stats()
    client_stats = stats.get(client.public_key, {})
    
    # Обновляем использование трафика
    await update_client_traffic_usage(client, client_stats)
    
    client_info = format_client_info(client, client_stats)
    
    new_message = await callback.bot.send_message(
        chat_id=user_id,
        text=client_info,
        reply_markup=get_client_details_keyboard(client.id),
        parse_mode="Markdown"
    )
    
    user_last_message[user_id] = new_message.message_id
    await callback.answer()

# QR-код конфигурации - с динамическим обновлением и кнопкой возврата
@admin_router.callback_query(F.data.startswith("client_qr:"))
async def send_client_qr(callback: CallbackQuery):
    """Отправить QR-код конфигурации клиента"""
    client_id = int(callback.data.split(":", 1)[1])
    client = await db.get_client(client_id)
    
    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    try:
        config_text = await awg_manager.create_client_config(client)
        qr_image = generate_qr_code(config_text)
        
        user_id = callback.from_user.id
        
        if user_id in user_last_message:
            try:
                await callback.bot.delete_message(
                    chat_id=user_id,
                    message_id=user_last_message[user_id]
                )
            except:
                pass
        
        new_message = await callback.bot.send_photo(
            chat_id=user_id,
            photo=qr_image,
            caption=f"📱 QR-код для клиента {client.name}\n\n"
                   "Отсканируйте этот код в приложении AmneziaWG",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад к клиенту", callback_data=f"client_details:{client_id}")
            ]])
        )
        user_last_message[user_id] = new_message.message_id
        
        await callback.answer("✅ QR-код отправлен")
        
    except Exception as e:
        logger.error(f"Ошибка при создании QR-кода: {e}")
        await callback.answer("❌ Ошибка при создании QR-кода", show_alert=True)

# Обработка возврата после QR-кода
@admin_router.callback_query(F.data.startswith("back_from_qr:"))
async def back_from_qr(callback: CallbackQuery):
    """Возврат к деталям клиента после показа QR-кода"""
    client_id = int(callback.data.split(":", 1)[1])
    
    # Перенаправляем к обработчику деталей клиента
    callback.data = f"client_details:{client_id}"
    await show_client_details(callback)

# Информация об IP клиента с трекингом из awg show
@admin_router.callback_query(F.data.startswith("client_ip_info:"))
async def show_client_ip_info(callback: CallbackQuery):
    """Показать информацию об IP соединениях клиента"""
    client_id = int(callback.data.split(":", 1)[1])
    client = await db.get_client(client_id)
    
    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    await callback.answer("🔍 Получаю информацию о соединениях...")
    
    stats = await awg_manager.get_interface_stats()
    
    today_connections = await db.get_client_daily_ips(client_id)
    
    info_text = f"🌍 IP соединения клиента {client.name}\n\n"
    
    current_endpoint = None
    client_stats = stats.get(client.public_key, {})
    if 'endpoint' in client_stats and client_stats['endpoint']:
        current_endpoint = client_stats['endpoint'].split(':')[0]
        
        current_ip_info = await ip_service.get_ip_info(current_endpoint)
        if current_ip_info:
            info_text += f"🔴 Сейчас подключен с IP: {current_endpoint}\n"
            info_text += f"   📍 {current_ip_info['country']}, {current_ip_info['city']}\n"
            info_text += f"   🌐 {current_ip_info['isp']}\n\n"
        else:
            info_text += f"🔴 Сейчас подключен с IP: {current_endpoint}\n\n"
    
    if not today_connections:
        if not current_endpoint:
            info_text += f"📅 За сегодня ({datetime.now().strftime('%d.%m.%Y')}) подключений не было"
        else:
            info_text += f"📅 За сегодня ({datetime.now().strftime('%d.%m.%Y')}) других подключений не было"
    else:
        info_text += f"📅 История подключений за сегодня ({datetime.now().strftime('%d.%m.%Y')}):\n\n"
        
        unique_ips = []
        seen_ips = set()
        
        for connection in today_connections:
            ip = connection['ip_address']
            if (current_endpoint and ip == current_endpoint) or ip in seen_ips:
                continue
            seen_ips.add(ip)
            unique_ips.append(connection)
        
        if not unique_ips:
            info_text += "Других уникальных IP подключений за сегодня не было"
        else:
            for i, connection in enumerate(unique_ips[:7], 1):  # Показываем до 7 уникальных IP
                ip = connection['ip_address']
                count = connection['connection_count']
                last_time = connection['last_seen'].strftime('%H:%M')
                
                ip_info = await ip_service.get_ip_info(ip)
                
                if ip_info:
                    info_text += f"{i}. 🌐 {ip}\n" \
                               f"   📍 {ip_info['country']}, {ip_info['city']}\n" \
                               f"   🏢 {ip_info['isp']}\n" \
                               f"   🔢 Подключений: {count}\n" \
                               f"   🕒 Последний раз: {last_time}\n\n"
                else:
                    info_text += f"{i}. 🌐 {ip}\n" \
                               f"   🔢 Подключений: {count}\n" \
                               f"   🕒 Последний раз: {last_time}\n\n"
            
            remaining = len(unique_ips) - 7
            if remaining > 0:
                info_text += f"... и еще {remaining} уникальных IP"
    
    await edit_or_send_message(
        callback,
        info_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔄 Обновить", callback_data=f"client_ip_info:{client_id}"),
            InlineKeyboardButton(text="🔙 Назад", callback_data=f"client_details:{client_id}")
        ]])
    )

# Статистика клиента
@admin_router.callback_query(F.data.startswith("client_stats:"))
async def show_client_stats(callback: CallbackQuery):
    """Показать статистику клиента"""
    client_id = int(callback.data.split(":", 1)[1])
    client = await db.get_client(client_id)
    
    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    stats = await awg_manager.get_interface_stats()
    client_stats = stats.get(client.public_key, {})
    
    if not client_stats:
        stats_text = f"👤 Статистика клиента {client.name}\n\n❌ Статистика недоступна"
    else:
        rx_bytes = client_stats.get('transfer', '0 B, 0 B').split(', ')[0]
        tx_bytes = client_stats.get('transfer', '0 B, 0 B').split(', ')[1]
        last_handshake = client_stats.get('latest handshake', 'Никогда')
        
        stats_text = f"""👤 Статистика клиента {client.name}

📥 Получено: {rx_bytes}
📤 Отправлено: {tx_bytes}  
🤝 Последнее подключение: {last_handshake}\n
📊 Использовано трафика: {format_traffic_size(client.traffic_used)}
📈 Лимит трафика: {'Без ограничений' if not client.traffic_limit or client.traffic_limit == 'unlimited' else format_traffic_size(client.traffic_limit)}"""
    
    await edit_or_send_message(
        callback,
        stats_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔄 Обновить", callback_data=f"client_stats:{client_id}"),
            InlineKeyboardButton(text="🔙 Назад", callback_data=f"client_details:{client_id}")
        ]])
    )
    await callback.answer()

# Удаление клиента
@admin_router.callback_query(F.data.startswith("delete_client:"))
async def confirm_delete_client(callback: CallbackQuery):
    """Подтвердить удаление клиента"""
    client_id = int(callback.data.split(":", 1)[1])
    client = await db.get_client(client_id)
    
    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    await edit_or_send_message(
        callback,
        f"🗑️ Удаление клиента\n\n"
        f"Вы действительно хотите удалить клиента {client.name}?\n\n"
        f"⚠️ Это действие нельзя отменить!",
        reply_markup=get_confirmation_keyboard("delete_client", str(client_id))
    )
    await callback.answer()

# Подтверждение удаления клиента
@admin_router.callback_query(F.data.startswith("confirm:delete_client:"))
async def delete_client_confirmed(callback: CallbackQuery):
    """Удалить клиента после подтверждения"""
    client_id = int(callback.data.split(":", 2)[2])
    client = await db.get_client(client_id)

    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return

    try:
        await awg_manager.remove_peer_from_server(client.public_key)

        success = await db.delete_client(client_id)

        if success:
            await callback.answer("✅ Клиент удален")

            # Возвращаем в список клиентов
            clients = await db.get_all_clients()
            if not clients:
                await edit_or_send_message(
                    callback,
                    f"✅ Клиент {client.name} успешно удален\n\n"
                    "📋 Список клиентов пуст",
                    reply_markup=get_clients_menu()
                )
            else:
                stats = await awg_manager.get_interface_stats()
                total_pages = (len(clients) - 1) // 10 + 1
                await edit_or_send_message(
                    callback,
                    f"✅ Клиент {client.name} удален\n\n"
                    f"📋 Список клиентов\n"
                    f"Страница 1 из {total_pages}\n"
                    f"Всего клиентов: {len(clients)}\n\n"
                    f"🟢 до 7 дн · 🟡 7-14 дн · 🟠 >14 дн · ⚪ нет · 🔴 блок",
                    reply_markup=get_client_list_keyboard(clients, 0, 10, stats)
                )
        else:
            await callback.answer("❌ Ошибка при удалении клиента", show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка при удалении клиента: {e}")
        await callback.answer("❌ Ошибка при удалении клиента", show_alert=True)

# Отмена действия
@admin_router.callback_query(F.data.startswith("cancel:"))
async def cancel_action(callback: CallbackQuery):
    """Отмена действия"""
    await edit_or_send_message(
        callback,
        "❌ Действие отменено",
        reply_markup=get_clients_menu()
    )
    await callback.answer()

@admin_router.callback_query(F.data == "stats_menu")
async def show_stats_menu(callback: CallbackQuery):
    """Отображение статистики сервера"""
    clients = await db.get_all_clients()
    active_clients = [c for c in clients if c.is_active and not c.is_blocked]
    blocked_clients = [c for c in clients if c.is_blocked]
    
    stats = await awg_manager.get_interface_stats()
    online_clients = len([key for key in stats.keys() if "latest handshake" in stats[key]])
    
    # Вычисление общего трафика всех клиентов
    total_traffic_used = 0
    total_traffic_limit = 0
    clients_with_limit = 0
    
    for client in clients:
        # Суммируем использованный трафик
        if client.traffic_used:
            total_traffic_used += client.traffic_used
        
        # Суммируем лимиты трафика (только для клиентов с установленным лимитом)
        if client.traffic_limit and client.traffic_limit != "unlimited":
            total_traffic_limit += client.traffic_limit
            clients_with_limit += 1
    
    try:
        network = ipaddress.IPv4Network(config.server_subnet)
        total_ips = network.num_addresses - 2
        available_ips = total_ips - len(clients)
    except:
        total_ips = available_ips = "—"
    
    current_time = datetime.now().strftime('%H:%M:%S')
    
    # Форматирование трафика
    traffic_used_formatted = format_traffic_size(total_traffic_used)
    traffic_limit_formatted = format_traffic_size(total_traffic_limit) if clients_with_limit > 0 else "—"
    
    stats_text = (
        f"📊 Статистика сервера\n\n"
        f"🕐 Время: {current_time}\n\n"
        f"👥 Клиенты:\n"
        f"├ 📋 Всего: {len(clients)}\n"
        f"├ ✅ Активных: {len(active_clients)}\n"
        f"├ 🔴 Заблокированных: {len(blocked_clients)}\n"
        f"└ 🟢 Онлайн: {online_clients}\n\n"
        f"🌐 IP-адреса:\n"
        f"├ 👤 Занято: {len(clients)} / {total_ips}\n"
        f"└ ✨ Доступно: {available_ips}\n\n"
        f"📈 Трафик сервера:\n"
        f"├ 📤 Использовано: {traffic_used_formatted}\n"
        f"└ 🎯 Лимит: {traffic_limit_formatted}\n"
        f"   💡 ({clients_with_limit} клиент{'ов' if clients_with_limit != 1 else ''})"
    )

    await edit_or_send_message(
        callback,
        stats_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="stats_menu")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
        ])
    )
    
    await callback.answer()

# Меню резервных копий
@admin_router.callback_query(F.data == "backup_menu")
async def show_backup_menu(callback: CallbackQuery):
    """Показать меню резервных копий"""
    backups = await backup_service.list_backups()
    
    await edit_or_send_message(
        callback,
        f"💾 Резервные копии\n\n"
        f"Найдено копий: {len(backups)}",
        reply_markup=get_backup_menu()
    )
    await callback.answer()

# Поиск клиента
@admin_router.callback_query(F.data == "search_client")
async def start_search_client(callback: CallbackQuery, state: FSMContext):
    """Начать поиск клиента"""
    await edit_or_send_message(
        callback,
        "🔍 Поиск клиента\n\n"
        "Введите имя клиента для поиска:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Отмена", callback_data="clients_menu")
        ]])
    )
    await state.set_state(ClientStates.waiting_client_search)
    await callback.answer()

# Обработка поиска клиента
@admin_router.message(StateFilter(ClientStates.waiting_client_search))
async def process_search_client(message: Message, state: FSMContext):
    """Обработка поиска клиента"""
    search_term = message.text.strip().lower()
    user_id = message.from_user.id
    
    try:
        await message.delete()
    except:
        pass
    
    if not search_term:
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text="🔍 Поиск клиента\n\n"
                         "❌ Введите корректное имя для поиска:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 Отмена", callback_data="clients_menu")
                    ]])
                )
            except:
                pass
        return
    
    all_clients = await db.get_all_clients()
    found_clients = [c for c in all_clients if search_term in c.name.lower()]

    await state.clear()

    if not found_clients:
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text=f"🔍 Поиск клиента\n\n"
                         f"❌ Клиенты с именем '{search_term}' не найдены",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 Меню клиентов", callback_data="clients_menu")
                    ]])
                )
            except:
                pass
    else:
        # Получаем статистику AWG для определения активности клиентов
        stats = await awg_manager.get_interface_stats()
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text=f"🔍 Результаты поиска\n\n"
                         f"Найдено клиентов: {len(found_clients)}\n\n"
                         f"🟢 до 7 дн · 🟡 7-14 дн · 🟠 >14 дн · ⚪ нет · 🔴 блок",
                    reply_markup=get_client_list_keyboard(found_clients, 0, 10, stats)
                )
            except:
                pass

# Редактирование имени клиента
@admin_router.callback_query(F.data.startswith("edit_name:"))
async def edit_client_name(callback: CallbackQuery, state: FSMContext):
    """Редактирование имени клиента"""
    client_id = int(callback.data.split(":", 1)[1])
    client = await db.get_client(client_id)
    
    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    await state.update_data(edit_client_id=client_id)
    await edit_or_send_message(
        callback,
        f"📝 Изменение имени клиента\n\n"
        f"Текущее имя: {client.name}\n\n"
        f"Введите новое имя (латинские буквы, цифры, символы - _ .):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Отмена", callback_data=f"edit_client:{client_id}")
        ]])
    )
    await state.set_state(EditClientStates.waiting_new_name)
    await callback.answer()

# Обработка нового имени
@admin_router.message(StateFilter(EditClientStates.waiting_new_name))
async def process_new_client_name(message: Message, state: FSMContext):
    """Обработка нового имени клиента"""
    new_name = message.text.strip()
    user_id = message.from_user.id
    
    try:
        await message.delete()
    except:
        pass
    
    data = await state.get_data()
    client_id = data.get('edit_client_id')
    client = await db.get_client(client_id)
    
    if not new_name or len(new_name) < 2 or len(new_name) > 32:
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text="📝 Изменение имени клиента\n\n"
                         "❌ Имя должно содержать от 2 до 32 символов\n\n"
                         "Введите корректное имя:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 Отмена", callback_data=f"edit_client:{client_id}")
                    ]])
                )
            except:
                pass
        return
    
    if not new_name.replace('-', '').replace('_', '').replace('.', '').isalnum():
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text="📝 Изменение имени клиента\n\n"
                         "❌ Имя может содержать только латинские буквы, цифры и символы - _ .\n\n"
                         "Введите корректное имя:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 Отмена", callback_data=f"edit_client:{client_id}")
                    ]])
                )
            except:
                pass
        return
    
    # Проверка уникальности
    existing_client = await db.get_client_by_name(new_name)
    if existing_client and existing_client.id != client_id:
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text="📝 Изменение имени клиента\n\n"
                         "❌ Клиент с таким именем уже существует\n\n"
                         "Введите другое имя:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 Отмена", callback_data=f"edit_client:{client_id}")
                    ]])
                )
            except:
                pass
        return
    
    # Обновляем имя
    old_name = client.name
    client.name = new_name
    success = await db.update_client(client)
    
    await state.clear()
    
    if success:
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text=f"✅ Имя клиента изменено\n\n"
                         f"Старое имя: {old_name}\n"
                         f"Новое имя: {new_name}",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 К клиенту", callback_data=f"client_details:{client_id}")
                    ]])
                )
            except:
                pass
    else:
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text="❌ Ошибка при изменении имени клиента",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 К клиенту", callback_data=f"client_details:{client_id}")
                    ]])
                )
            except:
                pass

# Редактирование endpoint
@admin_router.callback_query(F.data.startswith("edit_endpoint:"))
async def edit_client_endpoint(callback: CallbackQuery, state: FSMContext):
    """Редактирование endpoint клиента"""
    client_id = int(callback.data.split(":", 1)[1])
    client = await db.get_client(client_id)
    
    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    await state.update_data(edit_client_id=client_id)
    await edit_or_send_message(
        callback,
        f"📡 Изменение Endpoint клиента\n\n"
        f"Текущий Endpoint: {client.endpoint}\n\n"
        f"Введите новый IP-адрес или домен сервера:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Отмена", callback_data=f"edit_client:{client_id}")
        ]])
    )
    await state.set_state(EditClientStates.waiting_new_endpoint)
    await callback.answer()

# Обработка нового endpoint
@admin_router.message(StateFilter(EditClientStates.waiting_new_endpoint))
async def process_new_client_endpoint(message: Message, state: FSMContext):
    """Обработка нового endpoint клиента"""
    new_endpoint = message.text.strip()
    user_id = message.from_user.id
    
    try:
        await message.delete()
    except:
        pass
    
    data = await state.get_data()
    client_id = data.get('edit_client_id')
    client = await db.get_client(client_id)
    
    if not new_endpoint:
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text="📡 Изменение Endpoint клиента\n\n"
                         "❌ Endpoint не может быть пустым\n\n"
                         "Введите IP-адрес или домен сервера:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 Отмена", callback_data=f"edit_client:{client_id}")
                    ]])
                )
            except:
                pass
        return
    
    old_endpoint = client.endpoint
    client.endpoint = new_endpoint
    success = await db.update_client(client)
    
    await state.clear()
    
    if success:
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text=f"✅ Endpoint клиента изменен\n\n"
                         f"Старый Endpoint: {old_endpoint}\n"
                         f"Новый Endpoint: {new_endpoint}\n\n"
                         f"⚠️ Клиенту потребуется новая конфигурация!",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 К клиенту", callback_data=f"client_details:{client_id}")
                    ]])
                )
            except:
                pass
    else:
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text="❌ Ошибка при изменении Endpoint клиента",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 К клиенту", callback_data=f"client_details:{client_id}")
                    ]])
                )
            except:
                pass

# Редактирование срока действия клиента
@admin_router.callback_query(F.data.startswith("edit_expiry:"))
async def edit_client_expiry(callback: CallbackQuery, state: FSMContext):
    """Редактирование срока действия клиента"""
    client_id = int(callback.data.split(":", 1)[1])
    client = await db.get_client(client_id)
    
    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    await state.update_data(edit_client_id=client_id)
    
    expiry_text = "Без ограничений" if client.expires_at is None else client.expires_at.strftime('%d.%m.%Y %H:%M')
    
    await edit_or_send_message(
        callback,
        f"⏰ Изменение срока действия\n\n"
        f"Клиент: {client.name}\n"
        f"Текущий срок: {expiry_text}\n\n"
        f"Выберите новый срок действия:",
        reply_markup=get_time_limit_keyboard_for_edit(client_id)
    )
    await callback.answer()

# Обработка выбора нового срока действия
@admin_router.callback_query(F.data.startswith("edit_time_limit:"))
async def process_edit_time_limit(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора нового срока действия"""
    parts = callback.data.split(":", 2)
    client_id = int(parts[1])
    time_limit = parts[2]
    
    client = await db.get_client(client_id)
    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    if time_limit == "custom":
        await state.update_data(edit_client_id=client_id)
        await edit_or_send_message(
            callback,
            "⏰ Выберите единицу времени для своего срока:",
            reply_markup=get_custom_time_keyboard_for_edit(client_id)
        )
        await callback.answer()
        return
    
    # Вычисляем дату окончания
    expires_at = None
    if time_limit != "unlimited":
        now = datetime.now()
        
        if time_limit.endswith('h'):
            hours = int(time_limit[:-1])
            expires_at = now + timedelta(hours=hours)
        elif time_limit.endswith('d'):
            days = int(time_limit[:-1])
            expires_at = now + timedelta(days=days)
        elif time_limit.endswith('w'):
            weeks = int(time_limit[:-1])
            expires_at = now + timedelta(weeks=weeks)
        elif time_limit.endswith('m'):
            months = int(time_limit[:-1])
            expires_at = now + timedelta(days=months * 30)
        elif time_limit.endswith('y'):
            years = int(time_limit[:-1])
            expires_at = now + timedelta(days=years * 365)
    
    # Обновляем клиента
    old_expiry = "Без ограничений" if client.expires_at is None else client.expires_at.strftime('%d.%m.%Y %H:%M')
    client.expires_at = expires_at
    success = await db.update_client(client)
    
    if success:
        new_expiry = "Без ограничений" if expires_at is None else expires_at.strftime('%d.%m.%Y %H:%M')
        await edit_or_send_message(
            callback,
            f"✅ Срок действия изменен\n\n"
            f"Клиент: {client.name}\n"
            f"Старый срок: {old_expiry}\n"
            f"Новый срок: {new_expiry}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 К клиенту", callback_data=f"client_details:{client_id}")
            ]])
        )
    else:
        await edit_or_send_message(
            callback,
            "❌ Ошибка при изменении срока действия",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 К клиенту", callback_data=f"client_details:{client_id}")
            ]])
        )
    
    await callback.answer()

# Обработка выбора единиц времени для редактирования
@admin_router.callback_query(F.data.startswith("edit_custom_time_unit:"))
async def process_edit_custom_time_unit(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора единиц времени для редактирования"""
    parts = callback.data.split(":", 2)
    client_id = int(parts[1])
    time_unit = parts[2]
    
    await state.update_data(edit_client_id=client_id, custom_time_unit=time_unit)
    
    unit_names = {
        'hours': 'часов',
        'days': 'дней',
        'weeks': 'недель',
        'months': 'месяцев',
        'years': 'лет'
    }
    
    await edit_or_send_message(
        callback,
        f"⏰ Введите количество {unit_names.get(time_unit, time_unit)}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Отмена", callback_data=f"edit_client:{client_id}")
        ]])
    )
    
    await state.set_state(EditClientStates.waiting_edit_time_value)
    await callback.answer()

# Обработка пользовательского времени для редактирования
@admin_router.message(StateFilter(EditClientStates.waiting_edit_time_value))
async def process_edit_custom_time_value(message: Message, state: FSMContext):
    """Обработка значения пользовательского времени для редактирования"""
    user_id = message.from_user.id
    
    try:
        await message.delete()
    except:
        pass
    
    try:
        value = int(message.text.strip())
        if value <= 0 or value > 1000:
            raise ValueError()
        
        data = await state.get_data()
        client_id = data.get('edit_client_id')
        time_unit = data.get('custom_time_unit', 'days')
        
        client = await db.get_client(client_id)
        if not client:
            if user_id in user_last_message:
                try:
                    await message.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=user_last_message[user_id],
                        text="❌ Клиент не найден",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(text="🔙 Меню клиентов", callback_data="clients_menu")
                        ]])
                    )
                except:
                    pass
            await state.clear()
            return
        
        now = datetime.now()
        expires_at = None
        
        if time_unit == 'hours':
            expires_at = now + timedelta(hours=value)
        elif time_unit == 'days':
            expires_at = now + timedelta(days=value)
        elif time_unit == 'weeks':
            expires_at = now + timedelta(weeks=value)
        elif time_unit == 'months':
            expires_at = now + timedelta(days=value * 30)
        elif time_unit == 'years':
            expires_at = now + timedelta(days=value * 365)
        
        old_expiry = "Без ограничений" if client.expires_at is None else client.expires_at.strftime('%d.%m.%Y %H:%M')
        client.expires_at = expires_at
        success = await db.update_client(client)
        
        await state.clear()
        
        if success:
            if user_id in user_last_message:
                try:
                    await message.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=user_last_message[user_id],
                        text=f"✅ Срок действия изменен\n\n"
                             f"Клиент: {client.name}\n"
                             f"Старый срок: {old_expiry}\n"
                             f"Новый срок: {expires_at.strftime('%d.%m.%Y %H:%M')}",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(text="🔙 К клиенту", callback_data=f"client_details:{client_id}")
                        ]])
                    )
                except:
                    pass
        else:
            if user_id in user_last_message:
                try:
                    await message.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=user_last_message[user_id],
                        text="❌ Ошибка при изменении срока действия",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(text="🔙 К клиенту", callback_data=f"client_details:{client_id}")
                        ]])
                    )
                except:
                    pass
    
    except ValueError:
        if user_id in user_last_message:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_last_message[user_id],
                    text="⏰ Ошибка!\n\n"
                         "❌ Введите корректное число (от 1 до 1000):",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="🔙 Отмена", callback_data="clients_menu")
                    ]])
                )
            except:
                pass

# Редактирование лимита трафика
@admin_router.callback_query(F.data.startswith("edit_traffic_limit:"))
async def edit_client_traffic(callback: CallbackQuery, state: FSMContext):
    """Редактирование лимита трафика клиента"""
    client_id = int(callback.data.split(":", 1)[1])
    client = await db.get_client(client_id)
    
    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    await state.update_data(edit_client_id=client_id)
    
    traffic_text = "Без ограничений"
    if client.traffic_limit and client.traffic_limit != "unlimited":
        traffic_gb = client.traffic_limit / (1024 * 1024 * 1024)
        traffic_text = f"{traffic_gb:.0f} GB"
    
    await edit_or_send_message(
        callback,
        f"📊 Изменение лимита трафика\n\n"
        f"Клиент: {client.name}\n"
        f"Текущий лимит: {traffic_text}\n\n"
        f"Выберите новый лимит трафика:",
        reply_markup=get_traffic_limit_keyboard_for_edit(client_id)
    )
    await callback.answer()

# Обработка выбора нового лимита трафика
@admin_router.callback_query(F.data.startswith("edit_traffic_value:"))
async def process_edit_traffic_limit(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора нового лимита трафика"""
    parts = callback.data.split(":", 2)
    client_id = int(parts[1])
    traffic_limit = parts[2]
    
    client = await db.get_client(client_id)
    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    # Конвертируем в байты
    traffic_limit_bytes = None
    if traffic_limit != "unlimited":
        gb_limit = int(traffic_limit)
        traffic_limit_bytes = gb_limit * 1024 * 1024 * 1024
    
    # Сохраняем старое значение для отображения
    old_traffic = "Без ограничений"
    if client.traffic_limit and client.traffic_limit != "unlimited":
        old_traffic_gb = client.traffic_limit / (1024 * 1024 * 1024)
        old_traffic = f"{old_traffic_gb:.0f} GB"
    
    # Обновляем клиента
    client.traffic_limit = traffic_limit_bytes
    success = await db.update_client(client)
    
    await state.clear()
    
    if success:
        new_traffic = "Без ограничений" if traffic_limit == "unlimited" else f"{traffic_limit} GB"
        await edit_or_send_message(
            callback,
            f"✅ Лимит трафика изменен\n\n"
            f"Клиент: {client.name}\n"
            f"Старый лимит: {old_traffic}\n"
            f"Новый лимит: {new_traffic}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 К клиенту", callback_data=f"client_details:{client_id}")
            ]])
        )
    else:
        await edit_or_send_message(
            callback,
            "❌ Ошибка при изменении лимита трафика",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 К клиенту", callback_data=f"client_details:{client_id}")
            ]])
        )
    
    await callback.answer()

# Перегенерация ключей
@admin_router.callback_query(F.data.startswith("regenerate_keys:"))
async def confirm_regenerate_keys(callback: CallbackQuery):
    """Подтверждение перегенерации ключей"""
    client_id = int(callback.data.split(":", 1)[1])
    client = await db.get_client(client_id)
    
    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    await edit_or_send_message(
        callback,
        f"🔄 Перегенерация ключей\n\n"
        f"Вы хотите перегенерировать ключи для клиента {client.name}?\n\n"
        f"⚠️ После этого:\n"
        f"• Старая конфигурация перестанет работать\n"
        f"• Клиент будет временно отключен\n"
        f"• Потребуется выдать новую конфигурацию\n\n"
        f"Продолжить?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_regenerate:{client_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"edit_client:{client_id}")
        ]])
    )
    await callback.answer()

# Подтверждение перегенерации ключей
@admin_router.callback_query(F.data.startswith("confirm_regenerate:"))
async def regenerate_client_keys(callback: CallbackQuery):
    """Перегенерация ключей клиента"""
    client_id = int(callback.data.split(":", 1)[1])
    client = await db.get_client(client_id)
    
    if not client:
        await callback.answer("❌ Клиент не найден", show_alert=True)
        return
    
    await callback.answer("🔄 Перегенерируем ключи...")
    
    try:
        await awg_manager.remove_peer_from_server(client.public_key)
        
        new_private_key, new_public_key = awg_manager.generate_keypair()
        
        client.private_key = new_private_key
        client.public_key = new_public_key
        success = await db.update_client(client)
        
        if success:
            if not client.is_blocked:
                await awg_manager.add_peer_to_server(client)
            
            await edit_or_send_message(
                callback,
                f"✅ Ключи успешно перегенерированы!\n\n"
                f"👤 Клиент: {client.name}\n"
                f"🔑 Новый публичный ключ: {new_public_key[:20]}...\n\n"
                f"⚠️ Старая конфигурация больше не работает!\n"
                f"Выдайте клиенту новую конфигурацию.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="📱 QR-код", callback_data=f"client_qr:{client_id}"),
                    InlineKeyboardButton(text="📄 Конфигурация", callback_data=f"client_config:{client_id}")
                ], [
                    InlineKeyboardButton(text="🔙 К клиенту", callback_data=f"client_details:{client_id}")
                ]])
            )
        else:
            await edit_or_send_message(
                callback,
                "❌ Ошибка при сохранении новых ключей",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🔙 К клиенту", callback_data=f"client_details:{client_id}")
                ]])
            )
    except Exception as e:
        logger.error(f"Ошибка при перегенерации ключей: {e}")
        await edit_or_send_message(
            callback,
            "❌ Произошла ошибка при перегенерации ключей",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 К клиенту", callback_data=f"client_details:{client_id}")
            ]])
        )

# Создание резервной копии
@admin_router.callback_query(F.data == "create_backup")
async def create_backup(callback: CallbackQuery):
    """Создание резервной копии"""
    await callback.answer("💾 Создаю резервную копию...")
    
    try:
        backup_filename = await backup_service.create_backup()
        if backup_filename:
            await edit_or_send_message(
                callback,
                f"✅ Резервная копия создана!\n\n"
                f"📦 Файл: {backup_filename}\n" 
                f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                reply_markup=get_backup_menu()
            )
        else:
            await edit_or_send_message(
                callback,
                "❌ Ошибка при создании резервной копии",
                reply_markup=get_backup_menu()
            )
    except Exception as e:
        logger.error(f"Ошибка при создании резервной копии: {e}")
        await edit_or_send_message(
            callback,
            "❌ Произошла ошибка при создании резервной копии",
            reply_markup=get_backup_menu()
        )

# Список резервных копий
@admin_router.callback_query(F.data == "list_backups")
async def list_backups(callback: CallbackQuery):
    """Показать список резервных копий"""
    backups = await backup_service.list_backups() 
    
    if not backups:
        await edit_or_send_message(
            callback,
            "📋 Список резервных копий\n\n"
            "Резервные копии не найдены",
            reply_markup=get_backup_menu()
        )
    else:
        await edit_or_send_message(
            callback,
            f"📋 Список резервных копий\n\n"
            f"Найдено копий: {len(backups)}",
            reply_markup=get_backup_list_keyboard(backups)
        )
    await callback.answer()

# Детали резервной копии
@admin_router.callback_query(F.data.startswith("backup_details:"))
async def show_backup_details(callback: CallbackQuery):
    """Показать детали резервной копии"""
    backup_filename = callback.data.split(":", 1)[1]
    backups = await backup_service.list_backups()
    
    backup_info = None
    for backup in backups:
        if backup['filename'] == backup_filename:
            backup_info = backup
            break
    
    if not backup_info:
        await edit_or_send_message(
            callback,
            "❌ Резервная копия не найдена",
            reply_markup=get_backup_menu()
        )
        await callback.answer()
        return
    
    size_str = backup_service.format_backup_size(backup_info['size'])
    created_str = backup_info['created_at'].strftime('%d.%m.%Y %H:%M')
    
    await edit_or_send_message(
        callback,
        f"📦 Детали резервной копии\n\n"
        f"📄 Имя файла: {backup_filename}\n"
        f"📊 Размер: {size_str}\n"
        f"📅 Создана: {created_str}",
        reply_markup=get_backup_details_keyboard(backup_filename)
    )
    await callback.answer()

# Восстановление резервной копии
@admin_router.callback_query(F.data.startswith("restore_backup:"))
async def restore_backup_confirm(callback: CallbackQuery):
    """Подтверждение восстановления резервной копии"""
    backup_filename = callback.data.split(":", 1)[1]
    
    await edit_or_send_message(
        callback,
        f"🔄 Восстановление резервной копии\n\n"
        f"Вы хотите восстановить резервную копию:\n"
        f"{backup_filename}\n\n"
        f"⚠️ ВНИМАНИЕ!\n"
        f"• Все текущие клиенты будут удалены\n"
        f"• Активные подключения будут разорваны\n"
        f"• Настройки сервера будут заменены\n\n"
        f"Продолжить?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_restore:{backup_filename}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"backup_details:{backup_filename}")
        ]])
    )
    await callback.answer()

# Подтверждение восстановления
@admin_router.callback_query(F.data.startswith("confirm_restore:"))
async def confirm_restore_backup(callback: CallbackQuery):
    """Выполнить восстановление резервной копии"""
    backup_filename = callback.data.split(":", 1)[1]
    
    await callback.answer("🔄 Восстанавливаю резервную копию...")
    
    try:
        success = await backup_service.restore_backup(backup_filename)
        if success:
            await edit_or_send_message(
                callback,
                f"✅ Резервная копия восстановлена!\n\n"
                f"📦 Файл: {backup_filename}\n"
                f"📅 Восстановлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                f"🔄 Перезапустите AWG сервис для применения изменений",
                reply_markup=get_backup_menu()
            )
        else:
            await edit_or_send_message(
                callback,
                "❌ Ошибка при восстановлении резервной копии",
                reply_markup=get_backup_menu()
            )
    except Exception as e:
        logger.error(f"Ошибка при восстановлении резервной копии: {e}")
        await edit_or_send_message(
            callback,
            "❌ Произошла ошибка при восстановлении резервной копии",
            reply_markup=get_backup_menu()
        )

# Удаление резервной копии
@admin_router.callback_query(F.data.startswith("delete_backup:"))
async def delete_backup_confirm(callback: CallbackQuery):
    """Подтверждение удаления резервной копии"""
    backup_filename = callback.data.split(":", 1)[1]
    
    await edit_or_send_message(
        callback,
        f"🗑️ Удаление резервной копии\n\n"
        f"Вы хотите удалить резервную копию:\n"
        f"{backup_filename}\n\n"
        f"⚠️ Это действие нельзя отменить!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_delete_backup:{backup_filename}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"backup_details:{backup_filename}")
        ]])
    )
    await callback.answer()

# Подтверждение удаления резервной копии
@admin_router.callback_query(F.data.startswith("confirm_delete_backup:"))
async def confirm_delete_backup(callback: CallbackQuery):
    """Выполнить удаление резервной копии"""
    backup_filename = callback.data.split(":", 1)[1]
    
    try:
        success = await backup_service.delete_backup(backup_filename)
        if success:
            await edit_or_send_message(
                callback,
                f"✅ Резервная копия удалена!\n\n"
                f"📦 Файл: {backup_filename}",
                reply_markup=get_backup_menu()
            )
        else:
            await edit_or_send_message(
                callback,
                "❌ Ошибка при удалении резервной копии",
                reply_markup=get_backup_menu()
            )
    except Exception as e:
        logger.error(f"Ошибка при удалении резервной копии: {e}")
        await edit_or_send_message(
            callback,
            "❌ Произошла ошибка при удалении резервной копии",
            reply_markup=get_backup_menu()
        )
    await callback.answer()

# Обработчик для неактивных кнопок
@admin_router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    """Обработчик для неактивных кнопок"""
    await callback.answer()