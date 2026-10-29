# Trade Recorder & PnL Service

A backend that ingests trades from multiple venues, keeps positions, and reports realized
and unrealized PnL. It handles idempotent ingestion, rejects oversells, and reconciles
against venue statements.

**Stack:** Python 3.12+, FastAPI, SQLAlchemy 2 (async, asyncpg), PostgreSQL, Alembic, pytest.

* Cost-basis method: **average cost**. See [DESIGN.md](DESIGN.md) for why.
* Money is `Decimal` / `NUMERIC(38,18)` end to end, and JSON floats are rejected.

## Quick start (Windows, PostgreSQL installed locally)

```powershell
# 1. Create a virtual environment and install
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

# 2. Configure: copy the example and put your PostgreSQL password in both URLs
copy .env.example .env

# 3. Create the database (uses DATABASE_URL from .env, no psql needed) and the tables
python -m app.db.create_database
alembic upgrade head

# 4. Run the API
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for the interactive OpenAPI UI.

### See every requirement working (one command)

With the API running, in a second terminal:

```powershell
python scripts/demo.py
```

It runs the worked example, the duplicate and conflict cases,
the oversell rejection, the reconciliation example and input validation against the live
API, printing each request and a PASS/FAIL check. Each run uses its own `demo-<id>`
venue and symbols, so it can be repeated on a database that already has data.

On macOS/Linux use `source .venv/bin/activate` and `cp .env.example .env`.

## Running tests

```powershell
pytest                      # everything
pytest tests/unit           # pure domain tests, no database needed
pytest -m integration       # API + concurrency tests against PostgreSQL
```

Integration tests use `TEST_DATABASE_URL` (from `.env` or the environment). They create the
test database if it does not exist and run the migrations. If PostgreSQL is not reachable,
they are **skipped** with the reason shown (`pytest -rs`).

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/trades` | Record a trade. `201` new, `200` duplicate (no-op), `409` same id with different data, `422` invalid or oversell |
| `GET`  | `/trades?venue=&symbol=&after_id=&limit=` | List trades in arrival order (keyset pagination) |
| `GET`  | `/trades/{venue}/{trade_id}` | Fetch one trade |
| `GET`  | `/positions`, `/positions/{symbol}` | Quantity, average cost, cost basis, realized PnL |
| `PUT`  | `/prices/{symbol}` | Set the latest price `{"price": "125"}` |
| `GET`  | `/pnl?symbol=` | Realized, unrealized and total PnL per symbol, plus totals per quote currency |
| `POST` | `/reconciliations/{venue}` | Compare a venue statement: `missing`, `extra`, `mismatched` |
| `GET`  | `/health` | Liveness and database check |

All errors have the same shape:

```json
{"error": {"code": "INSUFFICIENT_POSITION",
           "message": "SELL of 15 rejected: BTC-USD position is only 10. Short selling is not allowed.",
           "details": {"symbol": "BTC-USD", "available_quantity": "10", "requested_quantity": "15"}}}
```

## Worked example (from the requirements)

```bash
curl -X POST localhost:8000/trades -H "Content-Type: application/json" -d '{"venue":"binance","trade_id":"T1","symbol":"BTC-USD","side":"BUY","quantity":"10","price":"100","timestamp":"2026-10-29T10:00:00Z"}'
curl -X POST localhost:8000/trades -H "Content-Type: application/json" -d '{"venue":"binance","trade_id":"T2","symbol":"BTC-USD","side":"BUY","quantity":"10","price":"110","timestamp":"2026-10-29T10:01:00Z"}'
curl -X POST localhost:8000/trades -H "Content-Type: application/json" -d '{"venue":"binance","trade_id":"T3","symbol":"BTC-USD","side":"SELL","quantity":"5","price":"120","timestamp":"2026-10-29T10:02:00Z"}'
curl -X PUT  localhost:8000/prices/BTC-USD -H "Content-Type: application/json" -d '{"price":"125"}'
curl "localhost:8000/pnl"   # qty 15, avg 105, realized 75, unrealized 300
```

These exact numbers, the oversell case (position 10, SELL 15 rejected, position stays 10),
the duplicate `(binance, T-1001)` case and the reconciliation example are all covered by
tests.

## Project layout

```
app/
  domain/        pure logic: cost_basis.py (average cost), reconciliation.py, money.py
  services/      transactions, row locking, idempotency
  api/           FastAPI routers, dependency wiring, error handlers
  schemas/       Pydantic request/response models (Decimal-safe)
  db/            SQLAlchemy models and engine
migrations/      Alembic
tests/unit/          fast, no database
tests/integration/   real PostgreSQL, including concurrency races
```

## Documents

* [DESIGN.md](DESIGN.md): architecture, cost-basis choice, concurrency model, trade-offs
* [AI_USAGE.md](AI_USAGE.md): how AI tools were used while building this
