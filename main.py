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
from utils.traffic_parser import parse_traffic_size

async def update_client_traffic_usage_main(client, stats, awg_manager, db):
    """Обновление использования трафика клиента из статистики AWG"""
    if not stats:
        return

    transfer = stats.get('transfer', '0 B, 0 B')
    try:
        rx_str, tx_str = transfer.split(', ')

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

    consecutive_errors = 0
    max_consecutive_errors = 5

    while True:
        try:
            logger.info("Проверка лимитов клиентов...")

            # Проверка истекших клиентов
            expired_clients = await db.get_expired_clients()
            for client in expired_clients:
                if not client.is_blocked and client.is_active:
                    # Удаляем peer с сервера AWG
                    success = await awg_manager.remove_peer_from_server(client.public_key)
                    if success:
                        client.is_blocked = True
                        await db.update_client(client)
                        logger.info(f"Клиент {client.name} заблокирован: истек срок ({client.expires_at})")
                    else:
                        logger.error(f"Не удалось заблокировать клиента {client.name} на сервере AWG")

            # Обновление статистики трафика
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

                    # Проверка превышения лимита трафика
                    if (updated_client.traffic_limit and
                        isinstance(updated_client.traffic_limit, int) and
                        updated_client.traffic_used >= updated_client.traffic_limit and
                        not updated_client.is_blocked and updated_client.is_active):

                        # Удаляем peer с сервера AWG
                        success = await awg_manager.remove_peer_from_server(updated_client.public_key)
                        if success:
                            updated_client.is_blocked = True
                            await db.update_client(updated_client)
                            logger.info(f"Клиент {updated_client.name} заблокирован: превышен лимит трафика ({updated_client.traffic_used}/{updated_client.traffic_limit})")
                        else:
                            logger.error(f"Не удалось заблокировать клиента {updated_client.name} на сервере AWG")

            consecutive_errors = 0
            await asyncio.sleep(300)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Ошибка в проверке лимитов (попытка {consecutive_errors}/{max_consecutive_errors}): {e}")

            if consecutive_errors >= max_consecutive_errors:
                logger.critical("Слишком много последовательных ошибок в check_client_limits, задача останавливается")
                return

            # Exponential backoff: 10s, 20s, 40s, 80s, 160s
            wait_time = min(10 * (2 ** (consecutive_errors - 1)), 300)
            logger.info(f"Повтор через {wait_time} секунд...")
            await asyncio.sleep(wait_time)

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
    
    # Инициализация базы данных с пулом соединений
    await init_db()
    logger.info("База данных инициализирована")
    
    # Получаем экземпляр базы данных для последующего закрытия
    db = get_db()
    
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
    
    # Запуск фоновой задачи проверки лимитов
    limits_task = asyncio.create_task(check_client_limits())
    logger.info("Фоновая задача проверки лимитов запущена")
    
    try:
        await dp.start_polling(bot)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Получен сигнал завершения работы")
    finally:
        logger.info("Завершение работы бота...")
        
        # Отмена фоновой задачи
        limits_task.cancel()
        try:
            await limits_task
        except asyncio.CancelledError:
            logger.info("Фоновая задача остановлена")
        
        # Закрытие сессии бота
        await bot.session.close()
        logger.info("Сессия бота закрыта")
        
        # Закрытие пула соединений базы данных
        await db.close()
        logger.info("Пул соединений базы данных закрыт")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Программа завершена пользователем")