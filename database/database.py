import aiosqlite
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class Client:
    """Модель клиента"""
    id: Optional[int] = None
    name: str = ""
    public_key: str = ""
    private_key: str = ""
    preshared_key: str = ""
    ip_address: str = ""
    endpoint: str = ""
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    traffic_limit: Optional[int] = None
    traffic_used: int = 0
    is_active: bool = True
    is_blocked: bool = False
    last_ip: str = ""
    daily_ips: str = ""

@dataclass
class BotSettings:
    """Модель настроек бота"""
    id: Optional[int] = None
    setting_key: str = ""
    setting_value: str = ""
    description: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class ClientIPConnection:
    """Модель подключения клиента по IP"""
    id: Optional[int] = None
    client_id: int = 0
    ip_address: str = ""
    connection_count: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    date: str = ""

class Database:
    """Класс для работы с базой данных"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
    
    async def init_db(self):
        """Инициализация базы данных"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                public_key TEXT NOT NULL,
                private_key TEXT NOT NULL,
                preshared_key TEXT DEFAULT '',
                ip_address TEXT NOT NULL UNIQUE,
                endpoint TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                traffic_limit INTEGER,
                traffic_used INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                is_blocked BOOLEAN DEFAULT 0,
                last_ip TEXT DEFAULT '',
                daily_ips TEXT DEFAULT ''
            )
            """)
            
            try:
                await db.execute("ALTER TABLE clients ADD COLUMN preshared_key TEXT DEFAULT ''")
            except:
                pass

            try:
                await db.execute("ALTER TABLE clients ADD COLUMN last_ip TEXT DEFAULT ''")
            except:
                pass
                
            try:
                await db.execute("ALTER TABLE clients ADD COLUMN daily_ips TEXT DEFAULT ''")
            except:
                pass
            
            await db.execute("""
            CREATE TABLE IF NOT EXISTS client_ip_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                ip_address TEXT NOT NULL,
                connection_count INTEGER DEFAULT 1,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date TEXT NOT NULL,
                UNIQUE(client_id, ip_address, date)
            )
            """)
            
            await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_key TEXT NOT NULL UNIQUE,
                setting_value TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            
            await db.execute("""
            INSERT OR IGNORE INTO bot_settings (setting_key, setting_value, description)
            VALUES 
                ('default_dns', '1.1.1.1, 8.8.8.8', 'DNS сервера по умолчанию'),
                ('default_endpoint', '', 'Endpoint по умолчанию')
            """)
            
            await db.commit()
            self.logger.info("База данных инициализирована")

    async def get_setting(self, setting_key: str) -> Optional[str]:
        """Получение значения настройки"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT setting_value FROM bot_settings WHERE setting_key = ?", 
                (setting_key,)
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    async def set_setting(self, setting_key: str, setting_value: str, description: str = "") -> bool:
        """Установка значения настройки"""
        async with aiosqlite.connect(self.db_path) as db:
            now = datetime.now()
            cursor = await db.execute("""
            INSERT OR REPLACE INTO bot_settings 
            (setting_key, setting_value, description, updated_at)
            VALUES (?, ?, ?, ?)
            """, (setting_key, setting_value, description, now))
            await db.commit()
            return cursor.rowcount > 0

    async def get_all_settings(self) -> List[BotSettings]:
        """Получение всех настроек"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM bot_settings ORDER BY setting_key")
            rows = await cursor.fetchall()
            return [self._row_to_setting(row) for row in rows]

    def _row_to_setting(self, row: aiosqlite.Row) -> BotSettings:
        """Преобразование строки БД в объект BotSettings"""
        created_at = None
        updated_at = None
        
        if row["created_at"]:
            created_at = datetime.fromisoformat(row["created_at"])
        if row["updated_at"]:
            updated_at = datetime.fromisoformat(row["updated_at"])
        
        return BotSettings(
            id=row["id"],
            setting_key=row["setting_key"],
            setting_value=row["setting_value"],
            description=row["description"],
            created_at=created_at,
            updated_at=updated_at
        )

    async def add_client(self, client: Client) -> int:
        """Добавление нового клиента"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
            INSERT INTO clients (name, public_key, private_key, preshared_key, ip_address,
                               endpoint, expires_at, traffic_limit, is_active, is_blocked,
                               last_ip, daily_ips)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                client.name, client.public_key, client.private_key,
                client.preshared_key, client.ip_address, client.endpoint, client.expires_at,
                client.traffic_limit, client.is_active, client.is_blocked,
                client.last_ip, client.daily_ips
            ))
            await db.commit()
            return cursor.lastrowid

    async def get_client(self, client_id: int) -> Optional[Client]:
        """Получение клиента по ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
            row = await cursor.fetchone()
            if row:
                return self._row_to_client(row)
            return None

    async def get_client_by_name(self, name: str) -> Optional[Client]:
        """Получение клиента по имени"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM clients WHERE name = ?", (name,))
            row = await cursor.fetchone()
            if row:
                return self._row_to_client(row)
            return None

    async def get_all_clients(self) -> List[Client]:
        """Получение всех клиентов"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM clients ORDER BY created_at DESC")
            rows = await cursor.fetchall()
            return [self._row_to_client(row) for row in rows]

    async def update_client(self, client: Client) -> bool:
        """Обновление клиента"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
            UPDATE clients SET name = ?, endpoint = ?, expires_at = ?,
                             traffic_limit = ?, traffic_used = ?,
                             is_active = ?, is_blocked = ?,
                             last_ip = ?, daily_ips = ?
            WHERE id = ?
            """, (
                client.name, client.endpoint, client.expires_at,
                client.traffic_limit, client.traffic_used,
                client.is_active, client.is_blocked, 
                client.last_ip, client.daily_ips, client.id
            ))
            await db.commit()
            return cursor.rowcount > 0

    async def delete_client(self, client_id: int) -> bool:
        """Удаление клиента"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM client_ip_connections WHERE client_id = ?", (client_id,))
            cursor = await db.execute("DELETE FROM clients WHERE id = ?", (client_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def get_expired_clients(self) -> List[Client]:
        """Получение просроченных клиентов"""
        now = datetime.now()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM clients WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,)
            )
            rows = await cursor.fetchall()
            return [self._row_to_client(row) for row in rows]

    async def get_traffic_exceeded_clients(self) -> List[Client]:
        """Получение клиентов с превышенным трафиком"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM clients WHERE traffic_limit IS NOT NULL AND traffic_used >= traffic_limit"
            )
            rows = await cursor.fetchall()
            return [self._row_to_client(row) for row in rows]

    async def add_client_ip_connection(self, client_id: int, ip_address: str) -> None:
        """Добавление или обновление записи о подключении клиента по IP"""
        today = datetime.now().strftime('%Y-%m-%d')
        now = datetime.now()
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE client_ip_connections 
                SET connection_count = connection_count + 1, last_seen = ?
                WHERE client_id = ? AND ip_address = ? AND date = ?
            """, (now, client_id, ip_address, today))
            
            if cursor.rowcount == 0:
                await db.execute("""
                    INSERT INTO client_ip_connections 
                    (client_id, ip_address, connection_count, first_seen, last_seen, date)
                    VALUES (?, ?, 1, ?, ?, ?)
                """, (client_id, ip_address, now, now, today))
            
            await db.commit()

    async def get_client_daily_ips(self, client_id: int, date: str = None) -> List[Dict]:
        """Получение IP подключений клиента за день"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT ip_address, connection_count, first_seen, last_seen
                FROM client_ip_connections
                WHERE client_id = ? AND date = ?
                ORDER BY last_seen DESC
            """, (client_id, date))
            
            rows = await cursor.fetchall()
            return [{
                'ip_address': row['ip_address'],
                'connection_count': row['connection_count'],
                'first_seen': datetime.fromisoformat(row['first_seen']),
                'last_seen': datetime.fromisoformat(row['last_seen'])
            } for row in rows]

    async def cleanup_old_ip_connections(self, days_to_keep: int = 7) -> None:
        """Очистка старых записей IP подключений"""
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime('%Y-%m-%d')
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM client_ip_connections WHERE date < ?", (cutoff_date,))
            await db.commit()

    def _row_to_client(self, row: aiosqlite.Row) -> Client:
        """Преобразование строки БД в объект Client"""
        expires_at = None
        if row["expires_at"]:
            expires_at = datetime.fromisoformat(row["expires_at"])
        
        created_at = None
        if row["created_at"]:
            created_at = datetime.fromisoformat(row["created_at"])
        
        last_ip = ""
        daily_ips = ""
        try:
            last_ip = row["last_ip"] or ""
            daily_ips = row["daily_ips"] or ""
        except (IndexError, KeyError):
            pass

        return Client(
            id=row["id"],
            name=row["name"],
            public_key=row["public_key"],
            private_key=row["private_key"],
            preshared_key=row["preshared_key"],
            ip_address=row["ip_address"],
            endpoint=row["endpoint"],
            created_at=created_at,
            expires_at=expires_at,
            traffic_limit=row["traffic_limit"],
            traffic_used=row["traffic_used"],
            is_active=bool(row["is_active"]),
            is_blocked=bool(row["is_blocked"]),
            last_ip=last_ip,
            daily_ips=daily_ips
        )

# Глобальный экземпляр базы данных
db_instance = Database("clients.db")

async def init_db():
    """Инициализация базы данных"""
    await db_instance.init_db()

def get_db() -> Database:
    """Получение экземпляра базы данных"""
    return db_instance