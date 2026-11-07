# crypto_allert_api

REST API для графика криптовалют и сигналов осцилляторной системы.
Отдельный сервис от [crypto_allert](https://github.com/2018ZA/crypto_allert) —
читает данные из **общей PostgreSQL** (`kline_data`, `oscillator_data`), которую
наполняет `main.py` основного проекта.

- **Backend:** FastAPI + SQLAlchemy 2.0 (async) + asyncpg
- **Python:** 3.11+ (проверено на 3.12)
- **Swagger UI:** `/docs`
- **ReDoc:** `/redoc`

---

## 📐 Архитектура

```
┌─────────────────────────────────────────────────────┐
│  VPS                                                 │
│                                                      │
│  ┌──────────────────────────┐  ┌─────────────────┐   │
│  │ crypto_allert (прод)     │  │ crypto_api      │   │
│  │ ──────────────────────── │  │ ─────────────── │   │
│  │ main.py                  │  │ uvicorn :8000   │   │
│  │ • пишет в БД по расписанию│ │ • читает из БД  │   │
│  │ • отправляет в Telegram  │  │ • отдаёт JSON   │   │
│  └──────────┬───────────────┘  └────────┬────────┘   │
│             │ write                     │ read        │
│             ▼                           ▼             │
│        ┌────────────────────────────────────┐         │
│        │ PostgreSQL: crypto_analyzer        │         │
│        │   kline_data, oscillator_data      │         │
│        └────────────────────────────────────┘         │
└─────────────────────────────────────────────────────┘
```

**Ключевые принципы:**
- Оба сервиса независимы и запускаются как разные systemd-юниты
- `main.py` **пишет**, `api` **только читает** (никаких INSERT/UPDATE в API)
- Общая БД — единственная точка интеграции
- API слушает `127.0.0.1:8000` (снаружи — через SSH-туннель или nginx)

---

## 🌐 Эндпоинты

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/health` | Живость API + доступность БД |
| GET | `/api/chart` | Свечи OHLCV + сигналы за период |
| GET | `/docs` | Swagger UI |
| GET | `/redoc` | ReDoc |
| GET | `/openapi.json` | OpenAPI-схема |

### `GET /api/chart`

**Параметры:**

| Параметр | Тип | Обязательный | Допустимые значения |
|---|---|---|---|
| `symbol` | string | ✅ | `eth`, `btc`, `sol` или полный тикер `ETHUSDT` |
| `period` | string | — | `1h`, `4h`, `6h`, `12h`, `1d` (по умолчанию `1d`) |
| `signals` | string / list | — | `buy`, `sell`, `strong buy`, `strong sell`, `neutral` |

**Форматы `signals`:**
- `?signals=buy,sell` — через запятую
- `?signals=buy&signals=sell` — повторяющийся параметр
- `?signals=strong%20buy` — с пробелом
- не передан — все сигналы (включая `neutral`)

**Логика фильтра:**
Массив свечей **не сужается** — флаг `is_filtered_signal` проставляется точкам,
прошедшим фильтр. Фронт использует флаг для маркеров, а свечи рисует полностью —
чтобы график не терял контекст.

**Ответ:**

```json
{
  "symbol": "ETHUSDT",
  "interval": "1h",
  "period": "1d",
  "from_time": "2026-11-06T09:50:50Z",
  "to_time": "2026-11-07T09:50:50Z",
  "points_count": 24,
  "signal_points_count": 18,
  "points": [
    {
      "timestamp": 1793959200000,
      "time": "2026-11-06T10:00:00Z",
      "open": 2226.76,
      "high": 2247.44,
      "low": 2226.33,
      "close": 2237.68,
      "volume": 5725.9843,
      "signal": "neutral",
      "score": 1.0,
      "has_signal": true,
      "is_filtered_signal": true
    }
  ]
}
```

**Соглашения:**
- `points` всегда отсортированы по возрастанию времени (ASC)
- `timestamp` — Unix ms (UTC), совместим с lightweight-charts / highcharts
- `signal = null` — если у свечи нет строки в `oscillator_data`
- `signal = "neutral"` — валидный сигнал (не пустой)
- `is_filtered_signal` — **единственный флаг** для маркеров на фронте

**Примеры:**

```bash
# Все сигналы за сутки
curl "http://localhost:8000/api/chart?symbol=eth&period=1d"

# Только buy-семейство за 6 часов
curl "http://localhost:8000/api/chart?symbol=eth&period=6h&signals=buy,strong%20buy"

# Полный тикер, sell-семейство за 4 часа
curl "http://localhost:8000/api/chart?symbol=SOLUSDT&period=4h&signals=sell,strong%20sell"

# Без фильтра — все точки с непустым сигналом
curl "http://localhost:8000/api/chart?symbol=btc&period=12h"
```

---

## 🚀 Локальный запуск

### 1. Клонирование

```bash
git clone https://github.com/2018ZA/crypto_allert_api.git
cd crypto_allert_api
```

### 2. Виртуальное окружение

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Конфигурация `.env`

```bash
cp .env.example .env
nano .env
```

Минимум, что нужно заполнить — креды PostgreSQL (те же, что у `crypto_allert`):

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=crypto_analyzer
DB_USER=postgres
DB_PASSWORD=ваш_пароль

API_HOST=127.0.0.1
API_PORT=8000
API_DEBUG=false
API_CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

### 4. Проверка подключения к БД

```bash
set -a; . ./.env; set +a

venv/bin/python - <<'PY'
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine
url = (f"postgresql+asyncpg://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
       f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}")
async def main():
    eng = create_async_engine(url)
    async with eng.connect() as c:
        r = await c.exec_driver_sql("SELECT 1")
        print("asyncpg OK:", r.scalar())
    await eng.dispose()
asyncio.run(main())
PY
```

Ожидаемо: `asyncpg OK: 1`.

### 5. Запуск

```bash
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
# или
make dev
```

### 6. Проверка

```bash
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool
# {"status":"ok","db":"ok","version":"1.0.0"}

open http://127.0.0.1:8000/docs
```

### 7. Тесты

```bash
make test
# или
PYTHONPATH=. pytest tests/ -v
```

Ожидаемо: **36 passed** (на чистом окружении).

---

## 🖥 Деплой на сервер (production, systemd)

**Предусловия:**
- Ubuntu 22.04+ / Debian 12+
- PostgreSQL с рабочей БД (`kline_data`, `oscillator_data` уже наполнены `main.py`)
- Python 3.11+

### 1. Клонирование

```bash
git clone https://github.com/2018ZA/crypto_allert_api.git /opt/crypto_api
cd /opt/crypto_api
```

Если репозиторий **приватный** — используйте SSH:
```bash
git clone git@github.com:2018ZA/crypto_allert_api.git /opt/crypto_api
```

### 2. venv и зависимости

```bash
cd /opt/crypto_api
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate
```

**Проверка ключевых пакетов:**

```bash
/opt/crypto_api/venv/bin/pip list | grep -Ei '^(fastapi|uvicorn|pydantic|sqlalchemy|asyncpg|greenlet)'
```

Все шесть должны быть установлены.

### 3. `.env`

```bash
# Копируем из прод-проекта — креды БД те же
cp /root/crypto_allert/.env /opt/crypto_api/.env

# Добавляем API_*-переменные
cat >> /opt/crypto_api/.env <<'EOF'

# --- API ---
API_HOST=127.0.0.1
API_PORT=8000
API_DEBUG=false
API_CORS_ORIGINS=https://your-frontend.com
EOF

chmod 600 /opt/crypto_api/.env
```

### 4. Проверка БД

```bash
cd /opt/crypto_api
set -a; . ./.env; set +a

/opt/crypto_api/venv/bin/python - <<'PY'
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine
url = (f"postgresql+asyncpg://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
       f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}")
async def main():
    eng = create_async_engine(url)
    async with eng.connect() as c:
        r = await c.exec_driver_sql("SELECT 1")
        print("asyncpg OK:", r.scalar())
    await eng.dispose()
asyncio.run(main())
PY
```

Ожидаемо: `asyncpg OK: 1`.

### 5. Тестовый запуск на 8001 (до systemd)

```bash
cd /opt/crypto_api
source venv/bin/activate

nohup uvicorn api.main:app --host 127.0.0.1 --port 8001 \
    > /tmp/api_test.log 2>&1 &
echo $! > /tmp/api_test.pid
sleep 3

# Проверки
curl -s http://127.0.0.1:8001/api/health | python3 -m json.tool
curl -s "http://127.0.0.1:8001/api/chart?symbol=eth&period=1d" | python3 -m json.tool | head -20
curl -s -o /dev/null -w "docs=%{http_code}\n" http://127.0.0.1:8001/docs

# Остановка
kill $(cat /tmp/api_test.pid) && rm /tmp/api_test.pid
```

Если что-то не так — `cat /tmp/api_test.log` покажет traceback.

### 6. Systemd-сервис

```bash
cat > /etc/systemd/system/crypto-api.service <<'EOF'
[Unit]
Description=Crypto Alert API (FastAPI)
After=network.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/crypto_api

Environment="PATH=/opt/crypto_api/venv/bin"
EnvironmentFile=/opt/crypto_api/.env

ExecStart=/opt/crypto_api/venv/bin/uvicorn api.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 2 \
    --proxy-headers \
    --forwarded-allow-ips="127.0.0.1"

StandardOutput=journal
StandardError=journal
SyslogIdentifier=crypto-api

Restart=on-failure
RestartSec=5s

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/crypto_api

TimeoutStartSec=30
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
EOF

systemd-analyze verify /etc/systemd/system/crypto-api.service
```

### 7. Права для `www-data`

```bash
chown -R root:www-data /opt/crypto_api
chmod -R 750 /opt/crypto_api
chmod 640 /opt/crypto_api/.env
chmod -R g+rX /opt/crypto_api/venv

# Проверка
sudo -u www-data test -r /opt/crypto_api/.env && echo "OK: .env"
sudo -u www-data test -x /opt/crypto_api/venv/bin/uvicorn && echo "OK: uvicorn"
```

### 8. Запуск

```bash
systemctl daemon-reload
systemctl enable crypto-api
systemctl start crypto-api

sleep 3
systemctl status crypto-api --no-pager | head -15
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool
```

### 9. Проверка, что прод `crypto_allert` не пострадал

```bash
# Прод-процесс жив
pgrep -af "python.*main.py"

# Прод-каталог не изменён
cd /root/crypto_allert && git status && git branch --show-current

# Прод наполняет БД
set -a; . /root/crypto_allert/.env; set +a
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
    -U "$DB_USER" -d "$DB_NAME" \
    -c "SELECT symbol, max(open_time) FROM kline_data GROUP BY symbol;"
```

Все три проверки должны быть ✅.

---

## 🌐 Доступ снаружи (варианты)

### Вариант A — SSH-туннель (для разработки, самый простой)

На **вашей машине**:

```bash
ssh -L 8000:127.0.0.1:8000 root@<IP-сервера>
```

После этого `http://localhost:8000/docs` на вашей машине открывает API с сервера.
Ничего настраивать на сервере не нужно, HTTPS не требуется — трафик шифрует SSH.

### Вариант B — Nginx + HTTPS (для боевого фронта)

Требуется:
- Поддомен `api.your-domain.com` → A-запись на IP сервера
- Nginx
- Let's Encrypt

```bash
apt install -y nginx certbot python3-certbot-nginx

cat > /etc/nginx/sites-available/crypto-api <<'EOF'
server {
    listen 80;
    server_name api.your-domain.com;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl http2;
    server_name api.your-domain.com;
    ssl_certificate     /etc/letsencrypt/live/api.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/health {
        proxy_pass http://127.0.0.1:8000;
        access_log off;
    }
}
EOF

ln -s /etc/nginx/sites-available/crypto-api /etc/nginx/sites-enabled/crypto-api
nginx -t && systemctl reload nginx

certbot --nginx -d api.your-domain.com --email admin@your-domain.com --agree-tos --no-eff-email
```

Не забудьте обновить `API_CORS_ORIGINS` в `.env` на `https://your-frontend.com` и перезапустить:

```bash
sed -i 's|^API_CORS_ORIGINS=.*|API_CORS_ORIGINS=https://your-frontend.com|' /opt/crypto_api/.env
systemctl restart crypto-api
```

### ❌ Не делайте: открывать 8000 наружу без HTTPS

```bash
ufw allow 8000/tcp   # НЕ ДЕЛАЙТЕ
```

Без HTTPS, rate-limit и авторизации любой сканер найдёт API. Только для разовых тестов.

---

## 🔧 Управление сервисом

```bash
# Статус
systemctl status crypto-api

# Логи в реальном времени
journalctl -u crypto-api -f

# Последние 100 строк
journalctl -u crypto-api -n 100 --no-pager

# Логи за последние 10 минут
journalctl -u crypto-api --since "10 minutes ago"

# Перезапуск (после изменения кода или .env)
systemctl restart crypto-api

# Мягкая перезагрузка (без простоя)
systemctl reload-or-restart crypto-api

# Остановить (прод не затронется)
systemctl stop crypto-api

# Запустить
systemctl start crypto-api

# Отключить автозапуск
systemctl disable crypto-api

# Проверить статус одним словом
systemctl is-active crypto-api    # active | inactive | failed
systemctl is-enabled crypto-api   # enabled | disabled

# Проверить, что сервис отвечает
curl -s http://127.0.0.1:8000/api/health
```

---

## 🔄 Обновление кода

На **локальной машине**:

```bash
git add <изменённые файлы>
git commit -m "feat: ..."
git push origin master
```

На **сервере**:

```bash
cd /opt/crypto_api
git pull origin master
source venv/bin/activate
pip install -r requirements.txt
deactivate
systemctl restart crypto-api

# Проверка
curl -s http://127.0.0.1:8000/api/health
journalctl -u crypto-api -n 30 --no-pager
```

**Важно:** ветка `master` (не `main`) — так создан репозиторий.

---

## 🧯 Troubleshooting

### `ModuleNotFoundError: api`

Запуск не из `/opt/crypto_api`. Проверить `WorkingDirectory`:

```bash
grep WorkingDirectory /etc/systemd/system/crypto-api.service
# должно быть: WorkingDirectory=/opt/crypto_api
```

### `ImportError: SQLAlchemy asyncio requires greenlet`

`greenlet` не установлен. В `requirements.txt` должно быть:

```txt
sqlalchemy[asyncio]>=2.0.27,<3.0.0
```

Фикс:

```bash
source /opt/crypto_api/venv/bin/activate
pip install 'sqlalchemy[asyncio]'
deactivate
systemctl restart crypto-api
```

### `asyncpg.exceptions.InvalidPasswordError`

Пароль в `.env` неверный. Сверить с прод-проектом:

```bash
diff <(grep '^DB_' /root/crypto_allert/.env | sort) \
     <(grep '^DB_' /opt/crypto_api/.env | sort)
```

### `Connection refused` к БД

PostgreSQL не запущен или `DB_HOST` не тот:

```bash
systemctl status postgresql
ss -tlnp | grep 5432
```

### `Permission denied` на `.env`

`www-data` не читает файл:

```bash
chmod 640 /opt/crypto_api/.env
chown root:www-data /opt/crypto_api/.env
systemctl restart crypto-api
```

### `Address already in use` (8000)

Порт занят:

```bash
ss -tlnp | grep 8000
```

Либо остановите чужой процесс, либо смените `--port 8000` на `--port 8002` в unit-файле:

```bash
sed -i 's/--port 8000/--port 8002/' /etc/systemd/system/crypto-api.service
systemctl daemon-reload
systemctl restart crypto-api
```

### `points_count: 0`

В БД нет свечей за запрошенный период. Проверить:

```bash
set -a; . /opt/crypto_api/.env; set +a
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
    -U "$DB_USER" -d "$DB_NAME" \
    -c "SELECT count(*) FROM kline_data WHERE open_time > now() - interval '24 hours';"
```

Если `0` — прод `main.py` не наполняет БД. Запустить:

```bash
cd /root/crypto_allert
./venv/bin/python main.py --once
```

### `/api/health` возвращает `503`

БД недоступна. Смотреть логи:

```bash
journalctl -u crypto-api -n 50 --no-pager
```

Проверить, что `asyncpg OK: 1` (команда из шага 4 деплоя).

### Прод `crypto_allert` упал после деплоя API

**Такого не должно быть** — все действия только в `/opt/crypto_api`. Проверить:

```bash
cd /root/crypto_allert
git status
git branch --show-current
diff .env /root/backups/crypto_allert_env_*.bak
```

Перезапустить прод:

```bash
systemctl restart <имя-прод-сервиса>
# или
cd /root/crypto_allert && ./venv/bin/python main.py
```

---

## 📊 Полезные команды диагностики

```bash
# Кто слушает 8000
ss -tlnp | grep 8000

# Все процессы uvicorn
pgrep -af uvicorn

# Открытые файлы процесса
lsof -p $(pgrep -f "uvicorn api.main")

# Проверить JSON-ответ валидатором
curl -s http://127.0.0.1:8000/api/chart?symbol=eth | python3 -m json.tool

# Проверить время ответа
curl -s -o /dev/null -w "time=%{time_total}s code=%{http_code}\n" \
    http://127.0.0.1:8000/api/chart?symbol=eth

# Следить за логами nginx (если подключён)
tail -f /var/log/nginx/crypto-api.access.log

# Проверить размер БД
set -a; . /opt/crypto_api/.env; set +a
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "
    SELECT pg_size_pretty(pg_total_relation_size('kline_data')) AS kline_data,
           pg_size_pretty(pg_total_relation_size('oscillator_data')) AS oscillator_data;"
```

---

## 🧪 Тесты

```bash
make test
# или
PYTHONPATH=. pytest tests/ -v
```

Покрыто:
- `normalize_signal` — все алиасы (`buy`/`BUY`/`strong_buy`/`hold`/...)
- `normalize_signals_filter` — оба формата (`a,b` и `["a","b"]`), лимиты
- `normalize_symbol` — upper-case, защита от LIKE-инъекций, лимиты

**Не покрыто** (требует БД): `get_chart_data`, `_fetch_rows`, `_pick_dominant_symbol`.

---

## 📁 Структура проекта

```
crypto_allert_api/
├── api/
│   ├── __init__.py
│   ├── main.py               — FastAPI app, CORS, роутеры
│   ├── config.py             — настройки (pydantic-settings)
│   ├── db.py                 — async-движок SQLAlchemy + get_db
│   ├── schemas.py            — Pydantic-модели ответов
│   ├── routes/
│   │   ├── chart.py          — GET /api/chart
│   │   └── health.py         — GET /api/health
│   └── services/
│       └── chart_service.py  — бизнес-логика (SQL, нормализация)
├── tests/
│   └── api/
│       └── test_chart_service.py
├── .env.example              — шаблон конфигурации
├── .gitignore
├── requirements.txt
├── Makefile
└── README.md
```

---

## ✅ Чек-лист после деплоя

| # | Проверка | Команда | Ожидание |
|---|---|---|---|
| 1 | Сервис активен | `systemctl is-active crypto-api` | `active` |
| 2 | Health | `curl -s http://127.0.0.1:8000/api/health` | `{"status":"ok","db":"ok"}` |
| 3 | Данные | `curl -s ".../api/chart?symbol=eth&period=1d"` | `points_count > 0` |
| 4 | Swagger | `curl -s -o /dev/null -w "%{http_code}\n" .../docs` | `200` |
| 5 | Прод жив | `pgrep -af "python.*main.py"` | PID есть |
| 6 | Прод-каталог чист | `cd /root/crypto_allert && git status` | без изменений кода |
| 7 | Прод пишет в БД | `SELECT max(open_time) FROM kline_data` | свежие данные |
| 8 | Автозапуск | `systemctl is-enabled crypto-api` | `enabled` |

---

## 🚨 Известные грабли (для истории)

1. **`greenlet` не в `requirements.txt`** — `sqlalchemy[asyncio]` требует явного extras.
   Исправлено в коммите `917fe43`. При чистом развёртывании — обязательно
   `pip install 'sqlalchemy[asyncio]'` (или `requirements.txt` с extras).

2. **Ветка `master`, а не `main`** — при `git pull` используйте `origin master`.

3. **`signal_points_count = points_count` без фильтра** — нормально, если у всех
   свечей `neutral`. Фронт должен фильтровать по `signal`, а не по
   `is_filtered_signal` при отсутствии `signals`-параметра. В коде API
   при отсутствии фильтра `is_filtered_signal = has_signal` (включая `neutral`).

4. **`LIMIT max_rows = hours * 60 + 100`** — на период `1d` это 1540 строк.
   Если в БД хранятся минутные свечи — хватит с запасом. Если часовые —
   избыточно, но безопасно.

5. **`open_time` в БД — naive UTC** — сравнение с `datetime.now(timezone.utc)`
   требует `_to_naive_utc()`. Не менять на aware — Postgres `timestamp`
   без `tz` не примет aware.

---

## 📜 Лицензия

MIT (см. `LICENSE` в основном репозитории `crypto_allert`).

---

## 🔗 Связанные репозитории

- [crypto_allert](https://github.com/2018ZA/crypto_allert) — основной проект (сбор данных, анализ, Telegram-алерты)
- [crypto_allert_api](https://github.com/2018ZA/crypto_allert_api) — этот репозиторий
