import httpx

from tests.integration.helpers import make_trade, position, post_trade


async def test_ingest_records_trade_and_opens_position(client: httpx.AsyncClient) -> None:
    response = await post_trade(client, venue="Binance", symbol="btc-usd")

    assert response.status_code == 201
    body = response.json()
    assert body["duplicate"] is False
    assert body["trade"] | {"ingested_at": None} == {
        "id": 1,
        "venue": "binance",
        "trade_id": "T-1001",
        "symbol": "BTC-USD",
        "side": "BUY",
        "quantity": "10",
        "price": "100",
        "timestamp": "2026-10-29T10:00:00Z",
        "ingested_at": None,
    }
    pos = await position(client)
    assert (pos["quantity"], pos["avg_cost"], pos["trade_count"]) == ("10", "100", 1)


class TestIdempotency:
    async def test_same_venue_and_trade_id_twice_leaves_one_trade(
        self, client: httpx.AsyncClient
    ) -> None:
        first = await post_trade(client)
        second = await post_trade(client)

        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json()["duplicate"] is True
        assert second.json()["trade"]["id"] == first.json()["trade"]["id"]
        assert len((await client.get("/trades")).json()["items"]) == 1
        assert (await position(client))["quantity"] == "10"  # not 20

    async def test_equivalent_formatting_counts_as_the_same_trade(
        self, client: httpx.AsyncClient
    ) -> None:
        await post_trade(client)
        replay = await post_trade(
            client, quantity="10.000", price="100.0", timestamp="2026-10-29T15:30:00+05:30"
        )
        assert replay.status_code == 200
        assert replay.json()["duplicate"] is True

    async def test_same_trade_id_on_another_venue_is_a_different_trade(
        self, client: httpx.AsyncClient
    ) -> None:
        await post_trade(client, venue="binance")
        response = await post_trade(client, venue="coinbase")

        assert response.status_code == 201
        assert (await position(client))["quantity"] == "20"

    async def test_same_id_with_different_data_is_a_conflict(
        self, client: httpx.AsyncClient
    ) -> None:
        await post_trade(client)
        response = await post_trade(client, quantity="11")

        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "IDEMPOTENCY_CONFLICT"
        assert error["details"]["differences"] == {"quantity": {"recorded": "10", "received": "11"}}
        assert (await position(client))["quantity"] == "10"


class TestOversell:
    async def test_sell_beyond_position_is_rejected_and_nothing_changes(
        self, client: httpx.AsyncClient
    ) -> None:
        await post_trade(client, trade_id="B1", quantity="10")
        before = await position(client)

        response = await post_trade(client, trade_id="S1", side="SELL", quantity="15", price="120")

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "INSUFFICIENT_POSITION"
        assert error["details"] == {
            "symbol": "BTC-USD",
            "available_quantity": "10",
            "requested_quantity": "15",
        }
        assert await position(client) == before
        assert (await client.get("/trades/binance/S1")).status_code == 404

    async def test_rejected_sell_can_be_resent_once_position_allows(
        self, client: httpx.AsyncClient
    ) -> None:
        await post_trade(client, trade_id="B1", quantity="10")
        assert (await post_trade(client, trade_id="S1", side="SELL", quantity="15")).is_client_error

        await post_trade(client, trade_id="B2", quantity="10")
        retry = await post_trade(client, trade_id="S1", side="SELL", quantity="15")

        assert retry.status_code == 201
        assert (await position(client))["quantity"] == "5"

    async def test_sell_with_no_position(self, client: httpx.AsyncClient) -> None:
        response = await post_trade(client, side="SELL", symbol="ETH-USD")
        assert response.status_code == 422
        assert response.json()["error"]["details"]["available_quantity"] == "0"

    async def test_position_is_shared_across_venues(self, client: httpx.AsyncClient) -> None:
        await post_trade(client, venue="binance", trade_id="B1", quantity="4")
        await post_trade(client, venue="coinbase", trade_id="C1", quantity="6")

        response = await post_trade(
            client, venue="kraken", trade_id="K1", side="SELL", quantity="10"
        )

        assert response.status_code == 201
        pos = await position(client)
        assert (pos["quantity"], pos["avg_cost"]) == ("0", "0")


class TestValidation:
    async def test_errors_use_one_envelope_and_name_the_field(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post("/trades", json=make_trade(quantity="-1", side="HOLD"))

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "VALIDATION_ERROR"
        assert {problem["field"] for problem in error["details"]} == {
            "body.quantity",
            "body.side",
        }

    async def test_json_float_is_rejected(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/trades", json=make_trade(price=100.1))
        assert response.status_code == 422
        assert "precision" in response.json()["error"]["details"][0]["message"]


async def test_list_trades_filters_and_paginates(client: httpx.AsyncClient) -> None:
    for i in range(5):
        await post_trade(client, trade_id=f"B{i}", symbol="BTC-USD")
    await post_trade(client, trade_id="E1", symbol="ETH-USD")

    page = (await client.get("/trades", params={"symbol": "BTC-USD", "limit": 3})).json()
    assert [t["trade_id"] for t in page["items"]] == ["B0", "B1", "B2"]

    rest = (
        await client.get(
            "/trades", params={"symbol": "BTC-USD", "limit": 3, "after_id": page["next_after_id"]}
        )
    ).json()
    assert [t["trade_id"] for t in rest["items"]] == ["B3", "B4"]
    assert rest["next_after_id"] is None


async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.json() == {"status": "ok", "database": "ok"}
    assert "X-Request-ID" in response.headers
