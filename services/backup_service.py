import os
import json
import zipfile
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import aiofiles

from config import Config
from database.database import get_db, Client


class BackupService:
    """Сервис для создания и восстановления резервных копий"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.backup_dir = Path(config.backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    async def create_backup(self) -> str:
        """Создание полной резервной копии"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"awg_backup_{timestamp}.zip"
            backup_path = self.backup_dir / backup_filename
            
            db = get_db()
            clients = await db.get_all_clients()
            
            backup_data = {
                'version': '1.0',
                'created_at': datetime.now().isoformat(),
                'config': {
                    'awg_interface': self.config.awg_interface,
                    'server_ip': self.config.server_ip,
                    'server_port': self.config.server_port,
                    'server_subnet': self.config.server_subnet
                },
                'clients': []
            }
            
            for client in clients:
                client_data = {
                    'name': client.name,
                    'public_key': client.public_key,
                    'private_key': client.private_key,
                    'ip_address': client.ip_address,
                    'endpoint': client.endpoint,
                    'created_at': client.created_at.isoformat() if client.created_at else None,
                    'expires_at': client.expires_at.isoformat() if client.expires_at else None,
                    'traffic_limit': client.traffic_limit,
                    'traffic_used': client.traffic_used,
                    'is_active': client.is_active,
                    'is_blocked': client.is_blocked
                }
                backup_data['clients'].append(client_data)
            
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                clients_json = json.dumps(backup_data, indent=2, ensure_ascii=False)
                zipf.writestr('clients.json', clients_json)
                
                server_config_path = Path(self.config.awg_config_dir) / f"{self.config.awg_interface}.conf"
                if server_config_path.exists():
                    zipf.write(server_config_path, f"server_{self.config.awg_interface}.conf")
                
                if os.path.exists(self.config.database_path):
                    zipf.write(self.config.database_path, 'database.db')
            
            self.logger.info(f"Резервная копия создана: {backup_filename}")
            return backup_filename
            
        except Exception as e:
            self.logger.error(f"Ошибка при создании резервной копии: {e}")
            raise
    
    async def list_backups(self) -> List[Dict[str, Any]]:
        """Получение списка резервных копий"""
        backups = []
        
        try:
            for backup_file in self.backup_dir.glob("awg_backup_*.zip"):
                stat = backup_file.stat()
                backups.append({
                    'filename': backup_file.name,
                    'size': stat.st_size,
                    'created_at': datetime.fromtimestamp(stat.st_ctime),
                    'path': str(backup_file)
                })
            
            backups.sort(key=lambda x: x['created_at'], reverse=True)
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении списка резервных копий: {e}")
        
        return backups
    
    async def restore_backup(self, backup_filename: str) -> bool:
        """Восстановление из резервной копии"""
        try:
            backup_path = self.backup_dir / backup_filename
            
            if not backup_path.exists():
                self.logger.error(f"Файл резервной копии не найден: {backup_filename}")
                return False
            
            db = get_db()
            
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                if 'clients.json' not in zipf.namelist():
                    self.logger.error("Некорректная резервная копия: отсутствует clients.json")
                    return False
                
                with zipf.open('clients.json') as f:
                    backup_data = json.loads(f.read().decode('utf-8'))
                
                current_clients = await db.get_all_clients()
                for client in current_clients:
                    await db.delete_client(client.id)
                
                for client_data in backup_data['clients']:
                    client = Client(
                        name=client_data['name'],
                        public_key=client_data['public_key'],
                        private_key=client_data['private_key'],
                        ip_address=client_data['ip_address'],
                        endpoint=client_data['endpoint'],
                        expires_at=datetime.fromisoformat(client_data['expires_at']) if client_data['expires_at'] else None,
                        traffic_limit=client_data['traffic_limit'],
                        traffic_used=client_data['traffic_used'],
                        is_active=client_data['is_active'],
                        is_blocked=client_data['is_blocked']
                    )
                    await db.add_client(client)
            
            self.logger.info(f"Резервная копия восстановлена: {backup_filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка при восстановлении резервной копии: {e}")
            return False
    
    async def delete_backup(self, backup_filename: str) -> bool:
        """Удаление резервной копии"""
        try:
            backup_path = self.backup_dir / backup_filename
            
            if backup_path.exists():
                backup_path.unlink()
                self.logger.info(f"Резервная копия удалена: {backup_filename}")
                return True
            else:
                self.logger.warning(f"Файл резервной копии не найден: {backup_filename}")
                return False
                
        except Exception as e:
            self.logger.error(f"Ошибка при удалении резервной копии: {e}")
            return False
    
    def format_backup_size(self, size_bytes: int) -> str:
        """Форматирование размера файла"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"