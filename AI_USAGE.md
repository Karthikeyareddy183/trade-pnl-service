# AI Usage

I used **Claude Code** (Anthropic, Claude Opus 5.5) as a pair programmer for this
assignment. This file records what I did, what the AI did, and how the result was checked.

## How the design came together

I started with a rough architecture: a FastAPI service on PostgreSQL that stores every
trade and keeps a position per symbol. I asked the AI to explain its approach before
writing any code, and it refined my outline in a few important ways:

* **Trades table as the source of truth.** Positions are a running summary that can be
  rebuilt from the trades, not a separate record.
* **Idempotency in the database.** A unique key on `(venue, trade_id)`, not a
  "check, then insert" in Python, which fails when two requests arrive together.
* **A row lock per symbol.** Two SELLs at the same moment cannot both pass the oversell
  check.
* **Layers.** The money maths is pure Python, separate from the database and HTTP code, so
  it is easy to test.

I chose PostgreSQL installed locally (over Docker or a hosted database), and asked for
SQLAlchemy ORM for normal queries, with PostgreSQL-specific statements (`ON CONFLICT`,
`FOR UPDATE`) where they are needed.

## Who did what

| Area | AI | Me |
|---|---|---|
| Architecture | Refined my outline (see above) | Proposed the starting design; reviewed the plan before any code was written |
| Code | Wrote the models, services, API and maths | Reviewed it and asked for changes |
| Tests | Wrote unit, integration and concurrency tests | Ran them against my local PostgreSQL |
| Developer tools | Wrote `scripts/demo.py` | Asked for it to see every requirement working |
| Docs | Drafted README and DESIGN.md | Reviewed them |

## How the result was checked

* **The required numbers**: the worked example (quantity 15, average cost 105, realized
  75, unrealized 300), the oversell case, the duplicate case and the reconciliation
  example are all automated tests. `scripts/demo.py` shows them against the
  running API.
* **Concurrency**: tests send many requests at the same moment to a real PostgreSQL. For
  example, 15 copies of one trade must save exactly 1 row.
* **Validation**: invalid input is rejected with a clear error, for example a negative
  quantity, a side other than BUY/SELL, or a price sent as a JSON number instead of a
  string.
