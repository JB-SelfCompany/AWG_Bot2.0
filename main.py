import asyncio
import logging
import sys
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import Config
from handlers import admin_router
from middlewares.auth import AuthMiddleware
from database.database import init_db, get_db
from services.awg_manager import AWGManager

async def update_client_traffic_usage_main(client, stats, awg_manager, db):
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
        logging.error(f"Ошибка при парсинге трафика: {e}")

async def check_client_limits():
    """Фоновая задача проверки лимитов клиентов"""
    logger = logging.getLogger(__name__)
    config = Config()
    awg_manager = AWGManager(config)
    db = get_db()
    
    await asyncio.sleep(30) 
    
    while True:
        try:
            logger.info("Проверка лимитов клиентов...")
            
            expired_clients = await db.get_expired_clients()
            for client in expired_clients:
                if not client.is_blocked and client.is_active:
                    client.is_blocked = True
                    await db.update_client(client)
                    logger.info(f"Клиент {client.name} заблокирован в БД: истек срок ({client.expires_at})")

            stats = await awg_manager.get_interface_stats()
            all_clients = await db.get_all_clients()
            
            for client in all_clients:
                if client.public_key in stats:
                    client_stats = stats[client.public_key]
                    old_traffic = client.traffic_used
                    await update_client_traffic_usage_main(client, client_stats, awg_manager, db)
                    
                    updated_client = await db.get_client(client.id)
                    if updated_client.traffic_used != old_traffic:
                        logger.debug(f"Трафик клиента {client.name} обновлен: {old_traffic} -> {updated_client.traffic_used}")
                    
                    if (updated_client.traffic_limit and 
                        isinstance(updated_client.traffic_limit, int) and
                        updated_client.traffic_used >= updated_client.traffic_limit and
                        not updated_client.is_blocked and updated_client.is_active):
                        updated_client.is_blocked = True
                        await db.update_client(updated_client)
                        logger.info(f"Клиент {updated_client.name} заблокирован в БД: превышен лимит трафика ({updated_client.traffic_used}/{updated_client.traffic_limit})")

        except Exception as e:
            logger.error(f"Ошибка в проверке лимитов: {e}")
        
        await asyncio.sleep(300)

async def main():
    """Основная функция запуска бота"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('bot.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    logger = logging.getLogger(__name__)

    config = Config()

    if not config.bot_token:
        logger.error("BOT_TOKEN не найден в конфигурации")
        sys.exit(1)

    await init_db()
    logger.info("База данных инициализирована")

    awg_manager = AWGManager(config)
    if not await awg_manager.check_awg_available():
        logger.error("AmneziaWG недоступен")
        sys.exit(1)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.message.middleware(AuthMiddleware(config.admin_ids))
    dp.callback_query.middleware(AuthMiddleware(config.admin_ids))

    dp.include_router(admin_router)

    logger.info("Бот запущен")

    asyncio.create_task(check_client_limits())
    logger.info("Фоновая задача проверки лимитов запущена")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())