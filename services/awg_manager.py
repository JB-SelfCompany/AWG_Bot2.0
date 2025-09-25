import asyncio
import logging
import os
import subprocess
import pwd
import grp
from typing import Optional, List, Tuple, Dict
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.backends import default_backend
import base64
import ipaddress
from config import Config
from database.database import Client, get_db
from services.settings_service import SettingsService

class AWGManager:
    """Менеджер для работы с AmneziaWG"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.db = get_db()
        
        self.logger.info("Инициализация AWGManager")
        self.logger.info(f"AWG интерфейс: {self.config.awg_interface}")
        self.logger.info(f"Конфигурационная директория: {self.config.awg_config_dir}")
        self.logger.info(f"Текущий пользователь: {os.getuid()}")
        self.logger.info(f"Текущая группа: {os.getgid()}")
        
        try:
            username = pwd.getpwuid(os.getuid()).pw_name
            self.logger.info(f"Пользователь: {username}")
        except:
            self.logger.warning("Не удалось получить имя пользователя")

    async def save_server_config(self) -> bool:
        """Сохранить конфигурацию сервера с sudo если необходимо"""
        self.logger.debug("Сохранение конфигурации сервера")
        try:
            process = await asyncio.create_subprocess_exec(
                'awg-quick', 'save', self.config.awg_interface,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                self.logger.debug("Конфигурация сохранена")
                return True
            
            sudo_process = await asyncio.create_subprocess_exec(
                'sudo', 'awg-quick', 'save', self.config.awg_interface,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            sudo_stdout, sudo_stderr = await sudo_process.communicate()
            
            if sudo_process.returncode == 0:
                self.logger.debug("Конфигурация сохранена с sudo")
                return True
            else:
                self.logger.error(f"Ошибка сохранения конфигурации с sudo: {sudo_stderr.decode()}")
                return False
            
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении конфигурации: {e}")
            return False

    async def get_interface_stats(self) -> Dict[str, Dict]:
        """Получить статистику интерфейса с трекингом IP"""
        self.logger.debug("Получение статистики интерфейса")
        try:
            process = await asyncio.create_subprocess_exec(
                'awg', 'show', self.config.awg_interface,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                sudo_process = await asyncio.create_subprocess_exec(
                    'sudo', 'awg', 'show', self.config.awg_interface,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await sudo_process.communicate()
                
                if sudo_process.returncode != 0:
                    self.logger.error(f"Ошибка получения статистики: {stderr.decode()}")
                    return {}
            
            stats = {}
            current_peer = None
            
            for line in stdout.decode().split('\n'):
                line = line.strip()
                
                if line.startswith('peer:'):
                    current_peer = line.split(':', 1)[1].strip()
                    stats[current_peer] = {}
                    self.logger.debug(f"Найден peer: {current_peer[:20]}...")
                elif current_peer and ':' in line and not line.startswith('interface:'):
                    key, value = line.split(':', 1)
                    stats[current_peer][key.strip()] = value.strip()
                    
                    if key.strip() == 'endpoint':
                        endpoint_value = value.strip()
                        if endpoint_value:
                            client_ip = endpoint_value.split(':')[0]
                            await self._track_client_ip(current_peer, client_ip)
                            self.logger.debug(f"Трекаем IP {client_ip} для peer {current_peer[:20]}...")
            
            self.logger.debug(f"Получена статистика для {len(stats)} peers")
            return stats
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении статистики: {e}")
            return {}

    async def _track_client_ip(self, public_key: str, client_ip: str):
        """Трекинг IP клиента по его public key"""
        try:
            clients = await self.db.get_all_clients()
            client = None
            for c in clients:
                if c.public_key == public_key:
                    client = c
                    break
            
            if not client:
                self.logger.warning(f"Клиент с public key {public_key[:20]}... не найден в БД")
                return
            
            client.last_ip = client_ip
            await self.db.update_client(client)
            
            await self.db.add_client_ip_connection(client.id, client_ip)
            
            self.logger.debug(f"IP {client_ip} зафиксирован для клиента {client.name}")
            
        except Exception as e:
            self.logger.error(f"Ошибка при трекинге IP: {e}")

    async def check_awg_available(self) -> bool:
        """Проверить доступность AmneziaWG"""
        self.logger.info("Проверка доступности AmneziaWG")
        try:
            process = await asyncio.create_subprocess_exec(
                'which', 'awg',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                self.logger.error("AmneziaWG не найден в системе")
                self.logger.error(f"Ошибка: {stderr.decode()}")
                return False
            
            awg_path = stdout.decode().strip()
            self.logger.info(f"AWG найден: {awg_path}")
            
            if not os.access(awg_path, os.X_OK):
                self.logger.error(f"Нет прав на выполнение: {awg_path}")
                return False
            
            process = await asyncio.create_subprocess_exec(
                'awg', '--version',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                version = stdout.decode().strip()
                self.logger.info(f"Версия AWG: {version}")
            else:
                self.logger.warning(f"Не удалось получить версию AWG: {stderr.decode()}")
            
            await self.check_interface_exists()
            
            await self.check_interface_permissions()
            
            return True
            
        except FileNotFoundError:
            self.logger.error("AmneziaWG не установлен в системе")
            return False
        except Exception as e:
            self.logger.error(f"Ошибка при проверке AWG: {e}")
            return False

    async def check_interface_exists(self):
        """Проверить существование AWG интерфейса"""
        self.logger.info(f"Проверка интерфейса {self.config.awg_interface}")
        try:
            process = await asyncio.create_subprocess_exec(
                'ip', 'link', 'show', self.config.awg_interface,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                self.logger.info(f"Интерфейс {self.config.awg_interface} существует")
                self.logger.debug(f"Информация об интерфейсе: {stdout.decode().strip()}")
            else:
                self.logger.warning(f"Интерфейс {self.config.awg_interface} не найден")
                self.logger.warning(f"Ошибка: {stderr.decode()}")
                
                config_path = Path(self.config.awg_config_dir) / f"{self.config.awg_interface}.conf"
                if config_path.exists():
                    self.logger.info(f"Найден конфигурационный файл: {config_path}")
                    self.logger.info("Попробуйте поднять интерфейс командой:")
                    self.logger.info(f"sudo awg-quick up {self.config.awg_interface}")
                else:
                    self.logger.error(f"Конфигурационный файл не найден: {config_path}")
        except Exception as e:
            self.logger.error(f"Ошибка при проверке интерфейса: {e}")

    async def check_interface_permissions(self):
        """Проверить права доступа к AWG интерфейсу"""
        self.logger.info("Проверка прав доступа к AWG")
        try:
            process = await asyncio.create_subprocess_exec(
                'awg', 'show', self.config.awg_interface,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                self.logger.info("Права доступа к AWG в порядке")
                self.logger.debug(f"Вывод awg show: {stdout.decode()}")
            else:
                self.logger.error("Недостаточно прав для работы с AWG")
                self.logger.error(f"Ошибка: {stderr.decode()}")
                
                if "Operation not permitted" in stderr.decode():
                    self.logger.error("Возможные решения:")
                    self.logger.error("1. Запустите бота с sudo")
                    self.logger.error("2. Добавьте пользователя в группу с правами на AWG")
                    self.logger.error("3. Используйте sudo для команд awg")
        except Exception as e:
            self.logger.error(f"Ошибка при проверке прав: {e}")

    def generate_keypair(self) -> Tuple[str, str]:
        """Генерация пары ключей для клиента"""
        self.logger.debug("Генерация ключей клиента")
        try:
            private_key = x25519.X25519PrivateKey.generate()
            public_key = private_key.public_key()
            
            private_key_bytes = private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption()
            )
            
            public_key_bytes = public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
            
            private_key_b64 = base64.b64encode(private_key_bytes).decode('utf-8')
            public_key_b64 = base64.b64encode(public_key_bytes).decode('utf-8')
            
            self.logger.debug("Ключи сгенерированы успешно")
            self.logger.debug(f"Public key: {public_key_b64[:20]}...")
            
            return private_key_b64, public_key_b64
            
        except Exception as e:
            self.logger.error(f"Ошибка при генерации ключей: {e}")
            raise

    async def get_next_available_ip(self) -> Optional[str]:
        """Получить следующий доступный IP-адрес"""
        self.logger.info("Поиск свободного IP-адреса")
        try:
            network = ipaddress.IPv4Network(self.config.server_subnet)
            self.logger.debug(f"Подсеть сервера: {network}")
            
            used_ips = set()
            
            clients = await self.db.get_all_clients()
            for client in clients:
                used_ips.add(client.ip_address)
            
            used_ips.add(self.config.server_ip)
            
            self.logger.debug(f"Занятые IP: {sorted(used_ips)}")
            
            for ip in network.hosts():
                if str(ip) not in used_ips:
                    self.logger.info(f"Найден свободный IP: {ip}")
                    return str(ip)
            
            self.logger.error("Нет свободных IP-адресов")
            return None
            
        except Exception as e:
            self.logger.error(f"Ошибка при поиске IP: {e}")
            return None

    async def add_peer_to_server(self, client: Client) -> bool:
        try:
            process = await asyncio.create_subprocess_exec(
                'awg', 'set', self.config.awg_interface,
                'peer', client.public_key,
                'preshared-key', '/dev/stdin',
                'allowed-ips', f"{client.ip_address}/32",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate(input=client.preshared_key.encode())
            
            if process.returncode == 0:
                self.logger.info("Клиент добавлен на сервер")
                await self.save_server_config()
                return True
            
            sudo_process = await asyncio.create_subprocess_exec(
                'sudo', 'awg', 'set', self.config.awg_interface,
                'peer', client.public_key,
                'preshared-key', '/dev/stdin',
                'allowed-ips', f"{client.ip_address}/32",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate(input=client.preshared_key.encode())
            
            if sudo_process.returncode == 0:
                self.logger.info("Клиент добавлен на сервер с sudo")
                await self.save_server_config()
                return True
            else:
                self.logger.error(f"Ошибка добавления клиента с sudo: {sudo_stderr.decode()}")
                return False
                
        except Exception as e:
            self.logger.error(f"Ошибка при добавлении клиента: {e}")
            return False

    async def verify_interface_active(self):
        """Проверить активность интерфейса"""
        self.logger.debug("Проверка активности интерфейса")
        process = await asyncio.create_subprocess_exec(
            'ip', 'link', 'show', self.config.awg_interface,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"Интерфейс {self.config.awg_interface} не найден")
        
        if "UP" not in stdout.decode():
            self.logger.warning(f"Интерфейс {self.config.awg_interface} неактивен")
            self.logger.info("Попытка поднятия интерфейса...")
            
            up_process = await asyncio.create_subprocess_exec(
                'sudo', 'awg-quick', 'up', self.config.awg_interface,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            up_stdout, up_stderr = await up_process.communicate()
            
            if up_process.returncode == 0:
                self.logger.info("Интерфейс успешно поднят")
            else:
                self.logger.error(f"Не удалось поднять интерфейс: {up_stderr.decode()}")

    async def add_peer_normal(self, client: Client) -> bool:
        self.logger.debug("Попытка добавления пира без sudo")
        process = await asyncio.create_subprocess_exec(
            'awg', 'set', self.config.awg_interface,
            'peer', client.public_key,
            'allowed-ips', f"{client.ip_address}/32",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            self.logger.info("Пир добавлен без sudo")
            await self.save_server_config()
            return True
        else:
            self.logger.warning(f"Ошибка добавления без sudo: {stderr.decode()}")
            return False

    async def add_peer_sudo(self, client: Client) -> bool:
        """Добавить пира с sudo"""
        self.logger.debug("Попытка добавления пира с sudo")
        process = await asyncio.create_subprocess_exec(
            'sudo', 'awg', 'set', self.config.awg_interface,
            'peer', client.public_key,
            'allowed-ips', f"{client.ip_address}/32",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            self.logger.info("Пир добавлен с sudo")
            await self.save_server_config()
            return True
        else:
            self.logger.error(f"Ошибка добавления пира с sudo: {stderr.decode()}")
            return False

    async def create_client_config(self, client: Client) -> str:
        """Создать конфигурационный файл для клиента"""
        self.logger.debug(f"Создание конфигурации для клиента: {client.name}")
        
        try:
            settings_service = SettingsService()
            server_public_key = await self.get_server_public_key()
            if not server_public_key:
                raise Exception("Не удалось получить публичный ключ сервера")
            
            dns_servers = await settings_service.get_default_dns()
            additional_params = await self.get_server_amnezia_params()
            if additional_params is None:
                self.logger.error("Не удалось получить параметры Amnezia, используем обычный WireGuard")
                raise Exception("Ошибка получения параметров Amnezia")
            
            config_lines = [
                "[Interface]",
                f"PrivateKey = {client.private_key}",
                f"Address = {client.ip_address}/32",
                f"DNS = {dns_servers}"
            ]
            
            if additional_params:
                for param_name, param_value in additional_params.items():
                    config_lines.append(f"{param_name} = {param_value}")
                self.logger.info(f"Добавлены параметры Amnezia: {list(additional_params.keys())}")
            else:
                self.logger.info("Используются стандартные параметры WireGuard")
            
            config_lines.append("")
            config_lines.extend([
                "",
                "[Peer]",
                f"PublicKey = {server_public_key}",
                f"PresharedKey = {client.preshared_key}",
                "AllowedIPs = 0.0.0.0/0",
                f"Endpoint = {client.endpoint}:{self.config.server_port}",
                "PersistentKeepalive = 25"
            ])
            
            return '\n'.join(config_lines)
            self.logger.debug("Конфигурация создана успешно")
            return config
            
        except Exception as e:
            self.logger.error(f"Ошибка при создании конфигурации: {e}")
            raise

    async def remove_peer_from_server(self, public_key: str) -> bool:
        """Удалить пира с сервера AmneziaWG"""
        self.logger.info(f"Удаление пира с сервера: {public_key[:20]}...")
        try:
            process = await asyncio.create_subprocess_exec(
                'sudo', 'awg', 'set', self.config.awg_interface,
                'peer', public_key, 'remove',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                self.logger.info("Пир удален с сервера")
                await self.save_server_config()
                return True
            else:
                self.logger.error(f"Ошибка удаления пира: {stderr.decode()}")
                return False
                
        except Exception as e:
            self.logger.error(f"Ошибка при удалении пира: {e}")
            return False

    async def get_server_amnezia_params(self) -> Optional[Dict[str, str]]:
        """Получить параметры Amnezia из конфигурации сервера"""
        self.logger.debug("Получение параметров Amnezia")
        try:
            config_path = Path(self.config.awg_config_dir) / f"{self.config.awg_interface}.conf"
            self.logger.debug(f"Путь к конфигурации: {config_path}")
            
            if not config_path.exists():
                self.logger.error(f"Конфигурационный файл не найден: {config_path}")
                return None
            
            with open(config_path, 'r') as f:
                content = f.read()

            skip_params = {
                'PrivateKey', 'PublicKey', 'Address', 'ListenPort', 
                'PostUp', 'PostDown', 'DNS', 'AllowedIPs', 
                'Endpoint', 'PersistentKeepalive', 'PresharedKey', 'FwMark'
            }
            
            amnezia_params = {}
            in_interface_section = False
            
            for line in content.split('\n'):
                line = line.strip()
                
                if not line or line.startswith('#'):
                    continue
                
                if line.startswith('['):
                    in_interface_section = line.strip() == '[Interface]'
                    continue
                
                if in_interface_section and '=' in line:
                    try:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        if key not in skip_params:
                            amnezia_params[key] = value
                            self.logger.debug(f"Найден параметр Amnezia: {key} = {value}")
                    except ValueError:
                        self.logger.warning(f"Некорректная строка в конфиге: {line}")
                        continue
            
            if amnezia_params:
                self.logger.info(f"Найдено {len(amnezia_params)} параметров Amnezia: {list(amnezia_params.keys())}")
            else:
                self.logger.info("Параметры Amnezia не найдены, используется стандартный WireGuard")
            
            return amnezia_params
            
        except Exception as e:
            self.logger.error(f"Ошибка при чтении параметров Amnezia: {e}")
            return None

    async def get_server_public_key(self) -> Optional[str]:
        """Получить публичный ключ сервера"""
        self.logger.debug("Получение публичного ключа сервера")
        try:
            config_path = Path(self.config.awg_config_dir) / f"{self.config.awg_interface}.conf"
            self.logger.debug(f"Путь к конфигурации: {config_path}")
            
            if not config_path.exists():
                self.logger.error(f"Конфигурационный файл не найден: {config_path}")
                return None
            
            with open(config_path, 'r') as f:
                content = f.read()
            
            for line in content.split('\n'):
                if line.strip().startswith('PrivateKey'):
                    private_key = line.split('=', 1)[1].strip()
                    public_key = self.private_to_public_key(private_key)
                    self.logger.debug(f"Публичный ключ сервера: {public_key[:20]}...")
                    return public_key
            
            self.logger.error("PrivateKey не найден в конфигурации")
            return None
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении публичного ключа: {e}")
            return None

    def generate_preshared_key(self) -> str:
        """Генерация Preshared Key для дополнительной безопасности"""
        try:
            preshared_bytes = os.urandom(32)
            preshared_key_b64 = base64.b64encode(preshared_bytes).decode('utf-8')
            return preshared_key_b64
        except Exception as e:
            self.logger.error(f"Ошибка при генерации Preshared Key: {e}")
            raise

    def generate_keypair_with_preshared(self) -> Tuple[str, str, str]:
        """Генерация пары ключей + preshared key для клиента"""
        try:
            private_key, public_key = self.generate_keypair()
            preshared_key = self.generate_preshared_key()
            return private_key, public_key, preshared_key
        except Exception as e:
            self.logger.error(f"Ошибка при генерации ключей с Preshared: {e}")
            raise

    def private_to_public_key(self, private_key_b64: str) -> Optional[str]:
        """Конвертировать приватный ключ в публичный"""
        try:
            private_key_b64 = private_key_b64.strip()
            
            missing_padding = len(private_key_b64) % 4
            if missing_padding:
                private_key_b64 += '=' * (4 - missing_padding)
            
            private_key_bytes = base64.b64decode(private_key_b64)
            private_key = x25519.X25519PrivateKey.from_private_bytes(private_key_bytes)
            public_key = private_key.public_key()
            
            public_key_bytes = public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
            
            return base64.b64encode(public_key_bytes).decode('utf-8')
            
        except Exception as e:
            self.logger.error(f"Ошибка конвертации ключа: {e}")
            return None