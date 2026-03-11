# 🕵️ OpenClaw Arkham Intel Agent

Автономный ончейн-аналитик для поиска и расследования blockchain bounty.

## 📋 Описание

OpenClaw Arkham Intel Agent — это система автоматического мониторинга и расследования криптовалютных адресов с bounty-наградами. Агент работает в автономном режиме 12-13 часов без вмешательства пользователя.

### Возможности:

- 🔍 **Scout** — поиск новых bounty-целей с наградой > $500
- 🧠 **Investigator** — анализ транзакций с помощью AI (LLM)
- 📊 **Graph Analysis** — построение графа связей через networkx
- 📤 **IPFS Upload** — загрузка отчётов в децентрализованное хранилище
- ⛓️ **Blockchain Submit** — отправка результатов в смарт-контракт
- 📱 **Telegram Notifications** — мгновенные уведомления

## 🏗️ Архитектура

```
┌─────────────┐     ┌───────────────┐     ┌─────────────┐
│   Scout     │────▶│  Investigator │────▶│  Notifier   │
│ (Arkham API)│     │   (web3.py)   │     │  (Telegram) │
└─────────────┘     └───────┬───────┘     └─────────────┘
                          │
                    ┌─────▼─────┐
                    │   LLM     │
                    │ (Local)   │
                    └─────┬─────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │ Database │   │  Pinata  │   │Blockchain │
    │ (SQLite) │   │  (IPFS)  │   │ (Submit)  │
    └──────────┘   └──────────┘   └──────────┘
```

## 📁 Структура проекта

```
openclaw_arkham/
├── main.py              # Главный контроллер
├── scout.py             # Поиск bounty-целей
├── investigator.py      # Анализ транзакций
├── auto_submitter.py    # IPFS + Blockchain
├── notifier.py          # Telegram уведомления
├── database.py          # SQLite база данных
├── requirements.txt     # Python зависимости
├── .env.example         # Шаблон конфигурации
└── README.md            # Документация
```

## ⚙️ Установка

### 1. Клонирование репозитория

```bash
git clone https://github.com/OlehHavrilko/openclawArcham.git
cd openclawArcham
```

### 2. Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Конфигурация

```bash
cp .env.example .env
```

Отредактируйте `.env` файл:

```ini
# Web3 RPC URL (Ethereum mainnet)
WEB3_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY

# Pinata API (для IPFS)
PINATA_API_KEY=your_pinata_api_key
PINATA_SECRET_KEY=your_pinata_secret_key

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Wallet для подписи транзакций
WORKER_WALLET_PRIVATE_KEY=your_private_key
ARKHAM_CONTRACT_ADDRESS=0x...
```

## 🚀 Запуск

```bash
python main.py
```

Агент запустит бесконечный цикл:
1. Поиск новых bounty-целей
2. Расследование адреса (если найден)
3. Загрузка отчёта в IPFS
4. Отправка транзакции в блокчейн
5. Уведомление в Telegram
6. Пауза 1 час → повтор цикла

## 🔧 Требования к LLM

Локальная LLM должна быть запущена на `http://localhost:1234/v1/chat/completions`

**Рекомендуемая конфигурация:**
- RAM: 32 ГБ
- VRAM: 8 ГБ (частичная выгрузка)
- Модель: Llama 3, Mistral или аналогичная

## 🛡️ Отказоустойчивость

Все сетевые запросы защищены:
- try/except блоки
- Экспоненциальный backoff (5 попыток)
- Автоматическое восстановление при обрывах Wi-Fi
- Логирование в файл `arkham_agent.log`

## 📊 База данных

SQLite таблица `targets`:

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER | Primary Key |
| address | TEXT | Ethereum адрес |
| reward | REAL | Размер награды ($) |
| status | TEXT | Статус: pending/investigated/submitted |
| tx_hash | TEXT | Хеш транзакции |
| created_at | TIMESTAMP | Время создания |

## 📝 License

MIT License

## 👤 Author

Oleh Havrilko

---

**⚠️ Важно:** Никогда не коммитьте `.env` файл с реальными ключами!