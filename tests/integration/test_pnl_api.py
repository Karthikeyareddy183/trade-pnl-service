from typing import Any

import httpx

from tests.integration.helpers import position, post_trade


async def _load_worked_example(client: httpx.AsyncClient) -> None:
    await post_trade(client, trade_id="T1", side="BUY", quantity="10", price="100")
    await post_trade(client, trade_id="T2", side="BUY", quantity="10", price="110")
    await post_trade(client, trade_id="T3", side="SELL", quantity="5", price="120")
    await client.put("/prices/BTC-USD", json={"price": "125"})


async def _pnl(client: httpx.AsyncClient, **params: str) -> dict[str, Any]:
    response = await client.get("/pnl", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def test_worked_example(client: httpx.AsyncClient) -> None:
    await _load_worked_example(client)

    report = await _pnl(client)

    (row,) = report["positions"]
    assert row["quantity"] == "15"
    assert row["avg_cost"] == "105"
    assert row["realized_pnl"] == "75"
    assert row["unrealized_pnl"] == "300"
    assert row["total_pnl"] == "375"
    assert row["market_value"] == "1875"
    (totals,) = report["totals"]
    assert totals == {
        "quote_currency": "USD",
        "realized_pnl": "75",
        "unrealized_pnl": "300",
        "total_pnl": "375",
        "symbols_without_price": [],
    }


async def test_positions_endpoint_reflects_average_cost(client: httpx.AsyncClient) -> None:
    await _load_worked_example(client)

    pos = await position(client)

    assert pos["quantity"] == "15"
    assert pos["avg_cost"] == "105"
    assert pos["cost_basis"] == "1575"
    assert pos["realized_pnl"] == "75"
    assert pos["trade_count"] == 3


async def test_unrealized_is_null_until_a_price_is_set(client: httpx.AsyncClient) -> None:
    await post_trade(client)

    report = await _pnl(client)

    (row,) = report["positions"]
    assert row["unrealized_pnl"] is None
    assert row["total_pnl"] is None
    assert report["totals"][0]["symbols_without_price"] == ["BTC-USD"]


async def test_latest_price_replaces_previous(client: httpx.AsyncClient) -> None:
    await post_trade(client)
    await client.put("/prices/BTC-USD", json={"price": "90"})
    response = await client.put("/prices/btc-usd", json={"price": "130"})

    assert response.json()["price"] == "130"
    assert (await _pnl(client))["positions"][0]["unrealized_pnl"] == "300"


async def test_invalid_price_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.put("/prices/BTC-USD", json={"price": "0"})
    assert response.status_code == 422


async def test_totals_are_never_summed_across_quote_currencies(
    client: httpx.AsyncClient,
) -> None:
    await post_trade(client, trade_id="1", symbol="BTC-USD", quantity="1", price="100")
    await post_trade(client, trade_id="2", symbol="ETH-USD", quantity="1", price="10")
    await post_trade(client, trade_id="3", symbol="ETH-BTC", quantity="1", price="0.05")
    for symbol, price in [("BTC-USD", "110"), ("ETH-USD", "12"), ("ETH-BTC", "0.06")]:
        await client.put(f"/prices/{symbol}", json={"price": price})

    totals = {t["quote_currency"]: t for t in (await _pnl(client))["totals"]}

    assert totals["USD"]["unrealized_pnl"] == "12"
    assert totals["BTC"]["unrealized_pnl"] == "0.01"


async def test_pnl_can_be_filtered_by_symbol(client: httpx.AsyncClient) -> None:
    await post_trade(client, trade_id="1", symbol="BTC-USD")
    await post_trade(client, trade_id="2", symbol="ETH-USD")

    report = await _pnl(client, symbol="eth-usd")
    assert [row["symbol"] for row in report["positions"]] == ["ETH-USD"]


async def test_unknown_position_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/positions/DOGE-USD")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
