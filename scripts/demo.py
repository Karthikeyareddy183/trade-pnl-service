"""Walk through every requirement against a running API and print what happens.

    uvicorn app.main:app            # in one terminal
    python scripts/demo.py          # in another (optionally: --base-url http://host:port)

Each run uses fresh symbols and venues (suffixed with a run id), so it can be repeated
on a database that already holds data. Exit code is 0 only if every check passed.
"""

import argparse
import sys
import time
from typing import Any

import httpx

RUN = time.strftime("%H%M%S")
WORKED = f"DEMO{RUN}-USD"  # worked example symbol
OVERSELL = f"OVR{RUN}-USD"  # oversell scenario symbol
RECON = f"REC{RUN}-USD"  # reconciliation scenario symbol
# Trade ids are unique per venue, so per-run venues keep T1/T2/T3 from clashing with
# trades sent earlier (by hand or by a previous run).
VENUE = f"demo-{RUN}"
RECON_VENUE = f"demo-{RUN}-recon"  # reconciliation compares a whole venue, so isolate it

failures: list[str] = []


def heading(number: int, title: str, explanation: str) -> None:
    print(f"\n{'=' * 78}\n {number}. {title}\n{'=' * 78}")
    print(f" {explanation}\n")


def step(text: str) -> None:
    print(f"  -> {text}")


def check(label: str, actual: Any, expected: Any) -> None:
    ok = actual == expected
    mark = "PASS" if ok else "FAIL"
    print(f"     [{mark}] {label}: got {actual!r}" + ("" if ok else f", expected {expected!r}"))
    if not ok:
        failures.append(label)


def trade(trade_id: str, symbol: str, side: str, qty: str, price: str, **extra: Any) -> dict:
    return {
        "venue": extra.pop("venue", VENUE),
        "trade_id": trade_id,
        "symbol": symbol,
        "side": side,
        "quantity": qty,
        "price": price,
        "timestamp": extra.pop("timestamp", "2026-10-29T10:00:00Z"),
        **extra,
    }


def post_trade(client: httpx.Client, body: dict) -> httpx.Response:
    response = client.post("/trades", json=body)
    step(
        f"POST /trades  {body['venue']}/{body['trade_id']}  {body['side']} "
        f"{body['quantity']} {body['symbol']} @ {body['price']}  ->  HTTP {response.status_code}"
    )
    return response


def position(client: httpx.Client, symbol: str) -> dict:
    return client.get(f"/positions/{symbol}").json()


def pnl_row(client: httpx.Client, symbol: str) -> dict:
    report = client.get("/pnl", params={"symbol": symbol}).json()
    return report["positions"][0]


def worked_example(client: httpx.Client) -> None:
    heading(
        1,
        "Worked example: positions and PnL",
        "BUY 10 @ 100, BUY 10 @ 110, SELL 5 @ 120, then set the latest price to 125.",
    )
    post_trade(client, trade("T1", WORKED, "BUY", "10", "100"))
    post_trade(client, trade("T2", WORKED, "BUY", "10", "110"))
    post_trade(client, trade("T3", WORKED, "SELL", "5", "120"))
    response = client.put(f"/prices/{WORKED}", json={"price": "125"})
    step(f"PUT /prices/{WORKED}  price 125  ->  HTTP {response.status_code}")

    print("\n  GET /pnl (average cost method):")
    row = pnl_row(client, WORKED)
    check("quantity", row["quantity"], "15")
    check("average cost", row["avg_cost"], "105")
    check("realized PnL", row["realized_pnl"], "75")
    check("unrealized PnL", row["unrealized_pnl"], "300")


def idempotency(client: httpx.Client) -> None:
    heading(
        2,
        "Idempotency: the same (venue, trade_id) twice is counted once",
        "Re-send T1 exactly as before. It must be recognised as a duplicate.",
    )
    response = post_trade(client, trade("T1", WORKED, "BUY", "10", "100"))
    check("HTTP status", response.status_code, 200)
    check("duplicate flag", response.json()["duplicate"], True)
    check("position quantity unchanged", position(client, WORKED)["quantity"], "15")

    print("\n  Same trade_id but different data is not a retry, it is a conflict:")
    response = post_trade(client, trade("T1", WORKED, "BUY", "11", "100"))
    check("HTTP status", response.status_code, 409)
    check("error code", response.json()["error"]["code"], "IDEMPOTENCY_CONFLICT")


def oversell(client: httpx.Client) -> None:
    heading(
        3,
        "Oversell check: a SELL may not take the position below zero",
        "Hold 10, try to SELL 15. Expect a clear error and the position to stay 10.",
    )
    post_trade(client, trade("B1", OVERSELL, "BUY", "10", "100"))
    response = post_trade(client, trade("S1", OVERSELL, "SELL", "15", "120"))
    error = response.json()["error"]
    check("HTTP status", response.status_code, 422)
    check("error code", error["code"], "INSUFFICIENT_POSITION")
    print(f"     message: {error['message']}")
    check("position still", position(client, OVERSELL)["quantity"], "10")
    stored = client.get(f"/trades/{VENUE}/S1").status_code
    check("rejected SELL was not stored (GET -> 404)", stored, 404)


def reconciliation(client: httpx.Client) -> None:
    heading(
        4,
        "Reconciliation: compare a venue statement with our records",
        "We store T1 (10 @ 100) and T2 (5 @ 101). The venue reports T1 (10 @ 100), "
        "T2 (6 @ 101), T3 (1 @ 99).",
    )
    post_trade(client, trade("T1", RECON, "BUY", "10", "100", venue=RECON_VENUE))
    post_trade(client, trade("T2", RECON, "BUY", "5", "101", venue=RECON_VENUE))

    statement = [
        {k: v for k, v in trade(tid, RECON, "BUY", q, p).items() if k != "venue"}
        for tid, q, p in [("T1", "10", "100"), ("T2", "6", "101"), ("T3", "1", "99")]
    ]
    report = client.post(f"/reconciliations/{RECON_VENUE}", json={"trades": statement}).json()
    step(f"POST /reconciliations/{RECON_VENUE}  (3 statement lines)")

    check("missing from our records", [t["trade_id"] for t in report["missing"]], ["T3"])
    check("extra in our records", [t["trade_id"] for t in report["extra"]], [])
    mismatches = {
        m["trade_id"]: [(d["field"], d["recorded"], d["statement"]) for d in m["differences"]]
        for m in report["mismatched"]
    }
    check("mismatched", mismatches, {"T2": [("quantity", "5", "6")]})


def validation(client: httpx.Client) -> None:
    heading(
        5,
        "Validation: bad input is rejected before it reaches the database",
        "Negative quantity, an unknown side, and a JSON float (floats lose precision).",
    )
    cases = [
        ("negative quantity", {"quantity": "-5"}, "body.quantity"),
        ("side HOLD", {"side": "HOLD"}, "body.side"),
        ("float price 100.1", {"price": 100.1}, "body.price"),
    ]
    for label, override, field in cases:
        body = trade("V1", WORKED, "BUY", "1", "100") | override
        response = client.post("/trades", json=body)
        fields = [p["field"] for p in response.json()["error"]["details"]]
        step(f"{label}  ->  HTTP {response.status_code}, field {fields}")
        check(f"{label} rejected", (response.status_code, field in fields), (422, True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url, timeout=10) as client:
        try:
            health = client.get("/health").json()
        except httpx.ConnectError:
            print(f"Cannot reach {args.base_url}. Start the API first: uvicorn app.main:app")
            return 2
        print(f"API at {args.base_url}: {health}   (run id {RUN})")

        worked_example(client)
        idempotency(client)
        oversell(client)
        reconciliation(client)
        validation(client)

    print(f"\n{'=' * 78}")
    if failures:
        print(f" {len(failures)} check(s) FAILED: {failures}")
        return 1
    print(" All checks passed. Every requirement behaves as specified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
