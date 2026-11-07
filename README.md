# crypto_allert_api

REST API для графика криптовалют и сигналов осцилляторной системы.
Отдельный сервис от [crypto_allert](https://github.com/2018ZA/crypto_allert).
Читает данные из общей PostgreSQL (`kline_data`, `oscillator_data`).

## Эндпоинты

- `GET /api/health` — живость API и БД
- `GET /api/chart?symbol=eth&period=1d&signals=buy,strong buy` — свечи + сигналы
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Локальный запуск

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # заполнить DB_*
uvicorn api.main:app --reload
```

Проверка:

```bash
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool
curl -s "http://127.0.0.1:8000/api/chart?symbol=eth&period=1d" | python3 -m json.tool
```

## Тесты

```bash
make test
```

## Параметры `/api/chart`

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `symbol` | string | ✅ | `eth`, `btc`, `sol` или `ETHUSDT` |
| `period` | string | — | `1h`, `4h`, `6h`, `12h`, `1d` (по умолчанию `1d`) |
| `signals` | string/list | — | `buy`, `sell`, `strong buy`, `strong sell`, `neutral` |

Примеры:

```bash
# Все сигналы за сутки
curl "http://localhost:8000/api/chart?symbol=eth&period=1d"

# Только buy-семейство за 6 часов (оба формата эквивалентны)
curl "http://localhost:8000/api/chart?symbol=eth&period=6h&signals=buy,strong%20buy"
curl "http://localhost:8000/api/chart?symbol=eth&period=6h&signals=buy&signals=strong%20buy"
```

## Структура

```
api/
  main.py           — FastAPI app
  config.py         — настройки (pydantic-settings)
  db.py             — async-движок SQLAlchemy + get_db
  schemas.py        — Pydantic-модели
  routes/           — HTTP-роутеры (chart, health)
  services/         — бизнес-логика (chart_service)
```

## Контракт с фронтендом

- `points` всегда по возрастанию времени (ASC).
- `is_filtered_signal` — единственный флаг для маркеров.
  Свечи при фильтрации не сужаются — фронт получает полный график.
- `signal` = `null`, если у свечи нет строки в `oscillator_data`.