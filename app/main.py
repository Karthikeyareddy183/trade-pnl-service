import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse

from app.api import health, portfolio, reconciliation, trades
from app.api.errors import register_error_handlers
from app.config import Settings, get_settings
from app.db.session import create_engine, create_sessionmaker

logger = logging.getLogger("app.request")

API_DESCRIPTION = """
Records trades from several exchanges ("venues"), keeps track of how much of each coin
you hold, and tells you how much money you have made or lost.

## Try it in 3 steps

Open each endpoint below, click **Try it out**, then **Execute**.

1. **POST /trades**: send `BUY 10 @ 100`, then `BUY 10 @ 110`, then `SELL 5 @ 120`
   (change `trade_id` each time: `T1`, `T2`, `T3`).
2. **PUT /prices/{symbol}**: set `BTC-USD` to `{"price": "125"}`.
3. **GET /pnl**: quantity 15, avg cost 105, realized 75, unrealized 300.

PnL uses the **average cost** method.

## Words used in this API

| Term | Meaning |
|---|---|
| **venue** | The exchange the trade happened on, e.g. `binance`. |
| **symbol** | What was traded, `BASE-QUOTE`. `BTC-USD` means BTC priced in USD. |
| **position** | How much of a symbol you hold now, summed across all venues. |
| **cost basis** | Total money paid for the quantity you still hold. |
| **average cost** | Cost basis divided by quantity. |
| **realized PnL** | Profit or loss locked in by selling. |
| **unrealized PnL** | Profit or loss on what you still hold, at the latest price. |
| **mark price** | The latest price you set with `PUT /prices/{symbol}`. |

## Rules to know

* **Send amounts as strings**: `"100.5"`, not `100.5`. JSON decimals lose precision, so
  they are rejected. Amounts in responses are strings too.
* **Timestamps need a timezone**, e.g. `2026-10-29T10:00:00Z`.
* **Sending the same trade twice is safe.** A trade is identified by `venue` + `trade_id`.
  An identical resend returns `200` with `duplicate: true` and changes nothing.
* **You cannot sell more than you hold.** Such a SELL is rejected with `422` and nothing
  is saved.

## Errors

Every error has the same shape:

```json
{"error": {"code": "INSUFFICIENT_POSITION",
           "message": "SELL of 15 rejected: BTC-USD position is only 10. ...",
           "details": {"symbol": "BTC-USD", "available_quantity": "10",
                       "requested_quantity": "15"}}}
```

| Status | Code | When |
|---|---|---|
| 404 | `NOT_FOUND` | The trade or position does not exist. |
| 409 | `IDEMPOTENCY_CONFLICT` | Same `venue` + `trade_id` as a recorded trade, other data. |
| 422 | `VALIDATION_ERROR` | The request is malformed: missing field, float amount, no timezone... |
| 422 | `INSUFFICIENT_POSITION` | A SELL larger than the current position. |
| 422 | `DUPLICATE_STATEMENT_TRADE` | A reconciliation statement lists the same `trade_id` twice. |
"""

OPENAPI_TAGS = [
    {
        "name": "trades",
        "description": "Record trades and look them up. Start here.",
    },
    {
        "name": "portfolio",
        "description": "What you hold (positions), the latest prices, and profit/loss (PnL).",
    },
    {
        "name": "reconciliation",
        "description": "Check our records against a venue's statement and list the differences.",
    },
    {
        "name": "health",
        "description": "Is the service up and can it reach the database?",
    },
]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await app.state.engine.dispose()

    app = FastAPI(
        title="Trade Recorder & PnL Service",
        version="0.1.0",
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    # The engine connects lazily, so creating it here (not in lifespan) keeps the app
    # usable from test transports that do not run lifespan events.
    app.state.engine = create_engine(settings)
    app.state.sessionmaker = create_sessionmaker(app.state.engine)

    register_error_handlers(app)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s -> %s in %.1fms request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
            request_id,
        )
        return response

    for router in (trades.router, portfolio.router, reconciliation.router, health.router):
        app.include_router(router)

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse("/docs")

    return app


app = create_app()
