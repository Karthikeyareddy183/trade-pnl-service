from typing import Any

import httpx


def make_trade(**overrides: Any) -> dict[str, Any]:
    trade: dict[str, Any] = {
        "venue": "binance",
        "trade_id": "T-1001",
        "symbol": "BTC-USD",
        "side": "BUY",
        "quantity": "10",
        "price": "100",
        "timestamp": "2026-10-29T10:00:00Z",
    }
    trade.update(overrides)
    return trade


async def post_trade(client: httpx.AsyncClient, **overrides: Any) -> httpx.Response:
    return await client.post("/trades", json=make_trade(**overrides))


async def position(client: httpx.AsyncClient, symbol: str = "BTC-USD") -> dict[str, Any]:
    response = await client.get(f"/positions/{symbol}")
    assert response.status_code == 200, response.text
    return response.json()
