import type { View } from "../src/types";

const marketsView: View = "markets";
const accountView: View = "account";
const settingsView: View = "settings";

// @ts-expect-error logs are embedded in Markets, not a top-level view.
const logsView: View = "logs";

void marketsView;
void accountView;
void settingsView;
void logsView;
