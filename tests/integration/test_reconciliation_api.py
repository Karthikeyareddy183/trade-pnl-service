from typing import Any

import httpx

from tests.integration.helpers import post_trade


def line(trade_id: str, qty: str, px: str, **overrides: Any) -> dict[str, Any]:
    entry = {
        "trade_id": trade_id,
        "symbol": "BTC-USD",
        "side": "BUY",
        "quantity": qty,
        "price": px,
        "timestamp": "2026-10-29T10:00:00Z",
    }
    entry.update(overrides)
    return entry


async def _reconcile(client: httpx.AsyncClient, venue: str, **body: Any) -> httpx.Response:
    return await client.post(f"/reconciliations/{venue}", json=body)


async def test_worked_example_from_requirements(client: httpx.AsyncClient) -> None:
    await post_trade(client, trade_id="T1", quantity="10", price="100")
    await post_trade(client, trade_id="T2", quantity="5", price="101")

    response = await _reconcile(
        client,
        "binance",
        trades=[line("T1", "10", "100"), line("T2", "6", "101"), line("T3", "1", "99")],
    )

    assert response.status_code == 200
    report = response.json()
    assert report["is_clean"] is False
    assert report["summary"] == {
        "statement_trades": 3,
        "recorded_trades": 2,
        "matched": 1,
        "missing": 1,
        "extra": 0,
        "mismatched": 1,
    }
    assert [t["trade_id"] for t in report["missing"]] == ["T3"]
    assert report["mismatched"] == [
        {
            "trade_id": "T2",
            "differences": [{"field": "quantity", "recorded": "5", "statement": "6"}],
        }
    ]


async def test_extra_and_clean_cases(client: httpx.AsyncClient) -> None:
    await post_trade(client, trade_id="T1")
    await post_trade(client, trade_id="T2")

    extra = (await _reconcile(client, "binance", trades=[line("T1", "10", "100")])).json()
    assert [t["trade_id"] for t in extra["extra"]] == ["T2"]

    clean = (
        await _reconcile(
            client, "binance", trades=[line("T1", "10", "100"), line("T2", "10.0", "100.00")]
        )
    ).json()
    assert clean["is_clean"] is True


async def test_only_the_named_venue_is_compared(client: httpx.AsyncClient) -> None:
    await post_trade(client, venue="binance", trade_id="T1")
    await post_trade(client, venue="coinbase", trade_id="C1")

    report = (await _reconcile(client, "binance", trades=[line("T1", "10", "100")])).json()

    assert report["is_clean"] is True


async def test_statement_period_limits_recorded_trades(client: httpx.AsyncClient) -> None:
    await post_trade(client, trade_id="OLD", timestamp="2026-10-28T23:59:59Z")
    await post_trade(client, trade_id="T1", timestamp="2026-10-29T10:00:00Z")

    report = (
        await _reconcile(
            client,
            "binance",
            period_start="2026-10-29T00:00:00Z",
            period_end="2026-10-30T00:00:00Z",
            trades=[line("T1", "10", "100")],
        )
    ).json()

    assert report["is_clean"] is True
    assert report["summary"]["recorded_trades"] == 1


async def test_reconciliation_is_read_only(client: httpx.AsyncClient) -> None:
    await post_trade(client, trade_id="T1")

    await _reconcile(client, "binance", trades=[line("T9", "1", "1")])

    trades = (await client.get("/trades")).json()["items"]
    assert [t["trade_id"] for t in trades] == ["T1"]


async def test_duplicate_trade_ids_in_statement_are_rejected(client: httpx.AsyncClient) -> None:
    response = await _reconcile(
        client, "binance", trades=[line("T1", "1", "1"), line("T1", "2", "1")]
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DUPLICATE_STATEMENT_TRADE"
