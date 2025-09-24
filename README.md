# AmneziaWG Management Bot
[![License: GPLV3](https://img.shields.io/badge/License-GPLV3-green.svg)](#) [![Telegram](https://img.shields.io/badge/Telegram-Bot-blue?logo=telegram)](#)

Telegram бот для управления AmneziaWG VPN сервером с полным функционалом администрирования клиентов.

---

## 🚀 Возможности

- ➕ **Добавление клиентов** с настройками времени и трафика
- 🗑️ **Удаление клиентов** с очисткой конфигураций
- 🔒 **Блокировка/разблокировка** клиентов без удаления данных
- ⏰ **Временные конфигурации** (1 час, 1 день, 1 неделя, 1 месяц, свой срок, постоянная)
- 📊 **Ограничение трафика** (5GB, 10GB, 30GB, 100GB, без ограничений)
- 🌍 **Геолокация IP** через API ip-api.com
- 💾 **Резервные копии** с возможностью восстановления
- 📱 **QR-коды** для быстрого подключения клиентов
- 📈 **Статистика** сервера и отдельных клиентов

---

## 📋 Требования

- Python 3.12+
- AmneziaWG установленный и настроенный
- Root права для управления интерфейсом AWG
- Telegram Bot Token

---

## 🛠️ Установка и запуск

### 1. Установка pyenv и зависимостей

#### Ubuntu/Debian

```bash
sudo apt update && sudo apt install -y make build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
libsqlite3-dev wget curl llvm libncurses-dev xz-utils tk-dev libffi-dev liblzma-dev python3-openssl git
```

```bash
curl https://pyenv.run | bash
```

Добавьте в `.bashrc` или `.zshrc`:

```bash
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init - bash)"' >> ~/.bashrc
```

Активировать окружение `.bashrc` или `.zshrc`:
```bash
source .bashrc
```

Проверьте установку:
```bash
pyenv --version
```

---

### 2. Установка Python 3.12 и создание виртуального окружения

```bash
pyenv install 3.12.11
```

```bash
pyenv virtualenv 3.12.11 env
```

```bash
pyenv local env
```

---

### 3. Установка зависимостей проекта

```bash
pip install -r requirements.txt
```

---

### 4. (Опционально) Настройка systemd-юнита

Создать новый systemd-юнит:

```bash
sudo nano /etc/systemd/system/awg_bot.service
```

Внести следующий код в юнит:

```bash
[Unit]
Description=AmneziaWG Telegram Bot
After=network.target

[Service]
User=root
# Указать ваш путь к директории бота
WorkingDirectory=/home/user/AWG_Bot2.0
# Найти в системе, где лежит бинарный файл установленного python 3.12, и указать его вместе с main.py
ExecStart=/root/.pyenv/shims/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Запустить юнита:

```bash
sudo systemctl daemon-reload
```

```bash
sudo systemctl restart awg_bot.service
```

```bash
sudo systemctl enable awg_bot.service
```

---

## ▶️ Запуск проекта

1. Настройте `config.py` с необходимыми параметрами.
2. Запустите:

```bash
python main.py
```

3. Используйте Telegram для управления ботом.

---

## ⚙️ Настройка AmneziaWG

Перед запуском бота убедитесь, что AmneziaWG правильно настроен:

1. **Установка AmneziaWG:**
Установите AmneziaWG согласно официальной документации.

2. **Базовая конфигурация сервера:**
Создайте конфигурационный файл /etc/amnezia/amneziawg/awg0.conf

```bash
[Interface]
PrivateKey = <your_server_private_key>
Address = 10.10.0.1/24
ListenPort = 51820
PostUp = iptables -t nat -A POSTROUTING -o `ip route | awk '/default/ {print $5; exit}'` -j MASQUERADE
PostDown = iptables -t nat -D POSTROUTING -o `ip route | awk '/default/ {print $5; exit}'` -j MASQUERADE
```

3. **Запуск интерфейса:**

```bash
awg-quick up awg0
```

---

## 🔧 Конфигурация

### Основные параметры (config.py):

- `BOT_TOKEN` - Токен Telegram бота от @BotFather
- `ADMIN_IDS` - ID администраторов через запятую
- `SERVER_IP` - Внутренний IP адрес сервера (на интерфейсе)
- `AWG_INTERFACE` - Имя интерфейса AmneziaWG (по умолчанию: awg0)
- `SERVER_PORT` - Порт сервера (по умолчанию: 51820)
- `SERVER_SUBNET` - Подсеть сервера (по умолчанию: 10.10.0.0/24)

### Дополнительные параметры:

- `AWG_CONFIG_DIR` - Директория конфигураций AWG
- `DATABASE_PATH` - Путь к файлу базы данных
- `BACKUP_DIR` - Директория для резервных копий

---

## 📚 Использование

### Основные команды:
- `/start` - Запуск бота и главное меню

### Управление клиентами:
1. **Добавление клиента:**
   - Выберите "Управление клиентами" → "Добавить клиента"
   - Введите имя клиента
   - Укажите endpoint (внешний IP-адрес или домен, к которому будут подключаться клиенты)
   - Выберите срок действия
   - Установите лимит трафика

2. **Управление существующими:**
   - Просмотр списка всех клиентов
   - Блокировка/разблокировка
   - Получение конфигурации и QR-кода
   - Просмотр статистики
   - Удаление клиента

### Резервное копирование:
- Создание полной резервной копии
- Восстановление из резервной копии
- Управление файлами резервных копий

---

## 🏗️ Архитектура проекта

```
├── main.py                         # точка входа
├── config.py                       # конфигурационный файл
├── requirements.txt                # зависимости
└── handlers/                       # обработчики событий
    ├── init.py           
    ├── admin_handlers.py             
├── middlewares/                    # мидлвари
    ├── init.py         
    ├── auth.py
├── keyboards/                      # клавиатуры
    ├── init.py         
    ├── main_keyboards.py
├── database/                       # база данных
    ├── init.py        
    ├── database.py 
├── services/                       # бизнес-логика
    ├── init.py        
    ├── awg_manager.py
    ├── ip_service.py 
    ├── backup_service.py                 
└── utils/                          # утилиты
    ├── init.py  
    ├── qr_generator.py
    ├── formatters.py   
    └── vpn_converter.py         
```

---

## 📸 Скриншоты

| Главное меню |  Клиент | Редактирование клиента | Статистика сервера | Резервные копии |
|-----------------|------------------------|-------------------|-----------------|
| ![Menu](https://github.com/JB-SelfCompany/telegram-php-widget/blob/main/raw/1.png?text=Widget) | ![Client](https://github.com/JB-SelfCompany/telegram-php-widget/blob/main/raw/2.png?text=Telegram+Notify) | ![Editing](https://github.com/JB-SelfCompany/telegram-php-widget/blob/main/raw/3.png?text=Telegram+Notify) | ![Statistic](https://github.com/JB-SelfCompany/telegram-php-widget/blob/main/raw/4.png?text=Telegram+Notify) | ![Backup](https://github.com/JB-SelfCompany/telegram-php-widget/blob/main/raw/3.png?text=Telegram+Notify) |

---

## 🔐 Безопасность

- Аутентификация только для администраторов
- Валидация всех входных данных
- Безопасное хранение конфигураций
- Логирование всех операций

---

## 📊 Мониторинг

Бот ведет подробные логи всех операций:
- Создание/удаление клиентов
- Изменения конфигураций
- Ошибки системы
- Статистика использования

---

## 🆘 Поддержка

При возникновении проблем:
1. Проверьте логи бота
2. Убедитесь, что AmneziaWG работает корректно
3. Проверьте права доступа к файлам конфигурации
4. Проверьте доступность ip-api.com для геолокации

---

## 🔄 Обновления

Для обновления бота:
1. Сделайте резервную копию через интерфейс бота
2. Обновите код
3. Перезапустите бота
4. При необходимости восстановите данные