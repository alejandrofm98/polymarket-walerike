import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const appSource = readFileSync(resolve(root, "src/App.tsx"), "utf8");
const heroSource = readFileSync(resolve(root, "src/components/AccountHeroPanel.tsx"), "utf8");

assert.match(appSource, /import\s+\{\s*AccountView\s*\}\s+from\s+"@\/components\/AccountView";/);

assert.match(
  appSource,
  /\{activeView === "account" && \([\s\S]*<AccountHeroPanel[\s\S]*<AccountView[\s\S]*\)\}/,
  "account tab should render both hero panel and AccountView"
);

assert.doesNotMatch(heroSource, /Cargando cuenta|Sin datos de cuenta|Balance disponible|Efectivo|Cartera/);
assert.match(heroSource, /Account balance/);
