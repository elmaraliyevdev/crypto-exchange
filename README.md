# Crypto Exchange API

A simplified **cryptocurrency exchange backend** built with **FastAPI**. It supports user authentication (JWT access + refresh tokens), multi-currency wallets with deposit/withdraw, **limit orders**, a **Celery**-backed matching engine, public **order book** snapshots, and per-user **trade history**.

Trading pairs use the form `BASE/QUOTE` (for example `BTC/USDT`): the base asset is bought or sold; the quote currency (for example USDT) is used for settlement.

## Stack

- **FastAPI** — HTTP API
- **PostgreSQL** — persistence (SQLAlchemy 2.0 async via **asyncpg**)
- **Alembic** — database migrations
- **Redis** — refresh-token storage (hashed) and Celery broker/backend
- **Celery** — background order matching
- **Docker Compose** — `app`, `db`, `redis`, `worker`
- **Pytest** — integration tests for critical flows

## Prerequisites

- **Docker** and **Docker Compose** (recommended), or a local **Python 3.12+** virtual environment with **PostgreSQL** and **Redis** running.

## Quick start (Docker Compose)

1. **Copy environment file** and set a strong `SECRET_KEY`:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and replace `SECRET_KEY` with a long random string. Defaults in `.env.example` match the Compose Postgres/Redis hostnames (`db`, `redis`).

2. **Build and start all services** (API, Postgres, Redis, Celery worker):

   ```bash
   docker compose up --build -d
   ```

3. **Run database migrations** inside the app container:

   ```bash
   docker compose exec app alembic upgrade head
   ```

4. **Health check**:

   ```bash
   curl -s http://localhost:8000/ | python3 -m json.tool
   ```

   Expected: `{"status":"ok"}`.

API base URL: `http://localhost:8000/api/v1` (OpenAPI docs: `http://localhost:8000/docs`).

### Services

| Service | Role |
|--------|------|
| `app` | FastAPI (`uvicorn`), port **8000** on the host |
| `db` | PostgreSQL 16 |
| `redis` | Redis 7 |
| `worker` | Celery worker (`celery -A app.tasks.celery_app worker`) |

Celery uses `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` (see `.env.example`); if omitted, broker/backend fall back to `REDIS_URL` in code.

## Local development (without the `app` container)

Useful when you want breakpoints and reload on the host while still using Docker for Postgres/Redis:

1. Start only dependencies:

   ```bash
   docker compose up -d db redis worker
   ```

2. Create a virtualenv and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Set environment variables so the app reaches Postgres/Redis on **localhost** (example):

   ```bash
   export DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/crypto_exchange
   export REDIS_URL=redis://127.0.0.1:6379/0
   export CELERY_BROKER_URL=redis://127.0.0.1:6379/1
   export CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/2
   export SECRET_KEY=your-local-secret
   export PYTHONDONTWRITEBYTECODE=1
   ```

4. Apply migrations (from the project root):

   ```bash
   alembic upgrade head
   ```

5. Run the API:

   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

Keep the **worker** container running so order placement still enqueues matching tasks against Redis.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Async SQLAlchemy URL (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Redis for app (e.g. refresh tokens); default Celery broker/backend if dedicated URLs unset |
| `CELERY_BROKER_URL` | Optional Celery broker (e.g. `redis://redis:6379/1`) |
| `CELERY_RESULT_BACKEND` | Optional Celery result backend (e.g. `redis://redis:6379/2`) |
| `SECRET_KEY` | JWT signing secret |
| `ALGORITHM` | JWT algorithm (default `HS256`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime |
| `PYTHONDONTWRITEBYTECODE` | Set to `1` to avoid writing `__pycache__` (also set in Docker Compose) |

See `.env.example` for a full template.

## Database migrations

- **Upgrade**:

  ```bash
  docker compose exec app alembic upgrade head
  ```

  Or locally: `alembic upgrade head` (with `DATABASE_URL` set).

- Migrations live under `alembic/versions/`. `alembic/env.py` reads `DATABASE_URL` from the environment.

## Tests

Integration tests expect a real Postgres database and Redis. Example (local venv, DB/Redis on localhost):

```bash
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/crypto_exchange
export REDIS_URL=redis://127.0.0.1:6379/0
export SECRET_KEY=test-secret
export CELERY_BROKER_URL=redis://127.0.0.1:6379/1
export CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/2

alembic upgrade head
pytest -q
```

## API overview

All JSON routes below use the prefix `/api/v1`. Protected routes require:

`Authorization: Bearer <access_token>`

### Authentication

| Method | Path | Auth |
|--------|------|------|
| POST | `/auth/register` | No |
| POST | `/auth/login` | No (JSON `email`/`password` or OAuth2 form `username`/`password`) |
| POST | `/auth/refresh` | No (body: `refresh_token`) |
| POST | `/auth/logout` | Yes |

### Wallets

| Method | Path | Auth |
|--------|------|------|
| POST | `/wallets/deposit` | Yes |
| POST | `/wallets/withdraw` | Yes |
| GET | `/wallets` | Yes |
| GET | `/wallets/{currency}` | Yes |

### Orders and market data

| Method | Path | Auth |
|--------|------|------|
| POST | `/orders` | Yes |
| GET | `/orders` | Yes (query: `status`, `limit`, `offset`) |
| GET | `/orders/open` | Yes — only `open` / `partially_filled` (`limit`, `offset`) |
| GET | `/orders/{order_id}` | Yes |
| DELETE | `/orders/{order_id}` | Yes |
| GET | `/order-book/{pair}` | No — use `BTC-USDT` in the path; internally `BTC/USDT` |
| GET | `/trades/history` | Yes (`limit`, `offset`) |

List endpoints return a paginated object:

```json
{
  "items": [],
  "total": 0,
  "limit": 100,
  "offset": 0
}
```

Default `limit` is **100**, maximum **100**.

## Example API calls

Replace host/port if needed. Pretty-print JSON with `python3 -m json.tool` where shown.

### Register and log in

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","username":"alice","password":"secret123"}' | python3 -m json.tool

curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"secret123"}' | python3 -m json.tool
```

Save `access_token` from the login response (example: `export TOKEN='...'`).

### Deposit and read a wallet

```bash
curl -s -X POST http://localhost:8000/api/v1/wallets/deposit \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"currency":"USDT","amount":"10000"}' | python3 -m json.tool

curl -s http://localhost:8000/api/v1/wallets/USDT \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### Place a limit order

```bash
curl -s -X POST http://localhost:8000/api/v1/orders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pair":"BTC/USDT","side":"buy","price":"5000","quantity":"1"}' | python3 -m json.tool
```

### Public order book

```bash
curl -s http://localhost:8000/api/v1/order-book/BTC-USDT | python3 -m json.tool
```

### Trade history (paginated)

```bash
curl -s "http://localhost:8000/api/v1/trades/history?limit=20&offset=0" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### Worker logs (matching)

After placing orders that cross, check the Celery worker:

```bash
docker compose logs worker --tail=30
```

You should see task lines such as `Trade executed: ...` when a match occurs.

## Project layout (high level)

- `app/main.py` — FastAPI app
- `app/api/v1/` — route handlers
- `app/services/` — business logic and transactions
- `app/models/` — SQLAlchemy models
- `app/schemas/` — Pydantic request/response models
- `app/tasks/` — Celery app and matching engine
- `alembic/` — migrations
- `tests/` — pytest suite
- `.cursor/rules` — optional Cursor / AI workflow notes

## License

This repository is provided as a technical exercise; add a license if you distribute it.
