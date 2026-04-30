import type { View } from "../src/types";

const overviewView: View = "overview";
const accountView: View = "account";
const settingsView: View = "settings";

// @ts-expect-error markets moved to overview.
const marketsView: View = "markets";

// @ts-expect-error logs are embedded in Markets, not a top-level view.
const logsView: View = "logs";

void overviewView;
void accountView;
void settingsView;
void marketsView;
void logsView;
