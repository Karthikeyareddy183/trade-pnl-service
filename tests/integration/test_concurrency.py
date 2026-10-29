"""Races are fired with asyncio.gather through the ASGI app, so each request gets its own
pooled connection and its own transaction, and they genuinely contend in PostgreSQL."""

import asyncio
from collections import Counter
from decimal import Decimal

import httpx

from tests.integration.helpers import position, post_trade


async def test_identical_trade_sent_concurrently_is_recorded_once(
    client: httpx.AsyncClient,
) -> None:
    responses = await asyncio.gather(*(post_trade(client) for _ in range(15)))

    assert Counter(r.status_code for r in responses) == {201: 1, 200: 14}
    assert len({r.json()["trade"]["id"] for r in responses}) == 1
    assert len((await client.get("/trades")).json()["items"]) == 1
    assert (await position(client))["quantity"] == "10"


async def test_concurrent_sells_cannot_oversell(client: httpx.AsyncClient) -> None:
    """Position 10, ten concurrent SELLs of 3: without the row lock several would read
    quantity=10 at once and all pass the check. With it, exactly three succeed."""
    await post_trade(client, trade_id="B1", quantity="10")

    responses = await asyncio.gather(
        *(post_trade(client, trade_id=f"S{i}", side="SELL", quantity="3") for i in range(10))
    )

    assert Counter(r.status_code for r in responses) == {201: 3, 422: 7}
    assert (await position(client))["quantity"] == "1"


async def test_concurrent_buys_across_venues_all_land(client: httpx.AsyncClient) -> None:
    venues = ["binance", "coinbase", "kraken", "okx"]
    responses = await asyncio.gather(
        *(
            post_trade(
                client,
                venue=venues[i % len(venues)],
                trade_id=f"T{i}",
                quantity="1",
                price=str(100 + i),
            )
            for i in range(20)
        )
    )

    assert all(r.status_code == 201 for r in responses)
    pos = await position(client)
    assert pos["quantity"] == "20"
    assert Decimal(pos["cost_basis"]) == sum(Decimal(100 + i) for i in range(20))


async def test_symbols_do_not_block_each_other(client: httpx.AsyncClient) -> None:
    symbols = ["BTC-USD", "ETH-USD", "SOL-USD"]
    await asyncio.gather(
        *(
            post_trade(client, trade_id=f"{s}-{i}", symbol=s, quantity="1")
            for s in symbols
            for i in range(5)
        )
    )

    for symbol in symbols:
        assert (await position(client, symbol))["quantity"] == "5"
