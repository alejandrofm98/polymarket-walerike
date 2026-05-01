# Polymarket Walerike

Polymarket copytrading dashboard with FastAPI controls.

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
cp .env.example .env
python3 main.py
```

Dashboard: http://127.0.0.1:8000

Dashboard controls start, pause, stop, and solo-log mode; running `main.py` does not auto-trade.

Market reads use Polymarket Gamma API (`POLYMARKET_GAMMA_API_URL`, default `https://gamma-api.polymarket.com`) and public CLOB book endpoints (`POLYMARKET_HOST`, default `https://clob.polymarket.com`). Order placement uses configured CLOB credentials.

The dashboard Config panel selects BTC/ETH/SOL markets by timeframe (`5m`, `15m`, `1h`) and accepts explicit event or market slugs such as `btc-updown-5m-1777069800` or a full Polymarket event URL. `/api/markets` deterministically resolves current 5m/15m slugs, uses hourly Gamma series slugs for 1h markets, and enriches UP/DOWN prices from REST CLOB books.

Run tests:

```bash
python3 -m pytest -q
```

Frontend development:

```bash
python3 main.py
cd frontend
npm install
npm run dev
```

Vite serves the React dashboard at http://127.0.0.1:5173 and proxies `/api` plus `/ws` to FastAPI on port 8000. Production/static serving uses `frontend/dist` when present.

Build and run with Docker:

```bash
docker build -t polymarket-walerike .
docker run --rm -p 8000:8000 -v "$PWD/data:/app/data" polymarket-walerike
```

Or:

```bash
docker compose up --build
```

`py-clob-client-v2` is installed from `requirements.txt` and required for CLOB access. Do not put real private keys in source control. Account cash uses CLOB `/balance-allowance`, while position value and open positions use Polymarket Data API `/value?user=<funder>` and `/positions?user=<funder>`.

## Module Status

- `bot/core/polymarket_client.py`: CLOB wrapper, public Gamma reads, public REST book reads, and websocket payload helpers.
- `bot/core/binance_feed.py`: async Binance ticker feed for BTC/ETH/SOL with testable parse/update and momentum helpers.
- `bot/core/polymarket_rtds_feed.py`: async Polymarket RTDS crypto price feed.
- `bot/core/risk_manager.py`: pure pre-trade risk checks and size adjustment.
- `bot/core/hedge_strategy.py`: signal generation only; no order execution.
- `bot/runtime/copy_engine.py`: async copytrading lifecycle runner behind API controls.
- `bot/web/api_routes.py`: dashboard API controls and Gamma market scan endpoints wired to the runtime engine when present.

Next verification command:

```bash
cd frontend && npm run build && cd .. && python3 -m compileall main.py bot tests && python3 -m pytest -q
```
