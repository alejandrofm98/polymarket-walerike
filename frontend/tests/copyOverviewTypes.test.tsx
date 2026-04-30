import { createElement } from "react";
import { CopyOverview } from "../src/components/overview/CopyOverview";
import type { CopyOverviewPayload } from "../src/types";

const payload: CopyOverviewPayload = {
  runtime: { running: true, paused: false, paper_mode: true },
  summary: {
    wallet_count: 1,
    open_positions: 1,
    closed_trades: 1,
    realized_pnl: 12.5,
  },
  wallets: [
    {
      address: "0xleader",
      configured: {
        address: "0xleader",
        enabled: true,
        sizing_mode: "leader_percent",
        fixed_amount: 0,
      },
      tracked_balance: {
        address: "0xleader",
        enabled: true,
        cash: 10,
        positions_value: 5,
        total: 15,
      },
      open_positions: [
        {
          trade_id: "open-1",
          market: "btc",
          asset: "BTC",
          side: "YES",
          size: 2,
          status: "OPEN",
          pnl: 0,
          entry_price: 0.45,
          metadata: { copy_trade: true, leader_wallet: "0xleader", timeframe: "5m", market_slug: "btc-123" },
        },
      ],
      closed_trades: [
        {
          trade_id: "closed-1",
          market: "btc",
          asset: "BTC",
          side: "NO",
          status: "CLOSED",
          size: 1,
          pnl: 12.5,
          entry_price: 0.4,
          exit_price: 0.6,
          opened_at: 1,
          closed_at: 2,
          metadata: { copy_trade: true, leader_wallet: "0xleader", timeframe: "5m", market_slug: "btc-123" },
        },
      ],
      stats: {
        realized_pnl: 12.5,
        closed_count: 1,
      },
    },
  ],
};

createElement(CopyOverview, {
  overview: payload,
  logs: ["12:00:00 ws connected"],
  onClearLogs: () => undefined,
});
