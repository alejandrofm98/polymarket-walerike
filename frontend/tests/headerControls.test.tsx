import { createElement } from "react";
import { Header } from "../src/components/Header";

createElement(Header, {
  activeView: "overview",
  onViewChange: () => undefined,
  runtime: { running: true, paused: false },
  socketOnline: true,
  onExport: () => undefined,
  totalPnl: 0,
  openPositions: 0,
  trackedWallets: 1,
});
