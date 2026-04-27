# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the frontend into a Bento Box dashboard with an Account Hero panel and visual intuitive Market Cards, reducing tabular numeric clutter.

**Architecture:** Create `AccountHeroPanel`, `MarketCard`, and `MarketsBentoGrid` components. Integrate them into the main view (`App.tsx` or `MarketsView.tsx`), replacing `AccountView` and `MarketsTable`.

**Tech Stack:** React, Tailwind CSS, TypeScript, Vite.

---

### Task 1: Create `AccountHeroPanel` Component

**Files:**
- Create: `frontend/src/components/AccountHeroPanel.tsx`
- Modify: `frontend/src/components/shared/index.tsx` (export it if used from shared, otherwise ignore)

- [ ] **Step 1: Write the component code**

Create `frontend/src/components/AccountHeroPanel.tsx` with the following content:
```tsx
import { Wallet, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatNumber } from "@/lib/utils2";
import type { AccountSummary } from "@/types";

interface AccountHeroPanelProps {
  account: AccountSummary | null;
  loading: boolean;
}

export function AccountHeroPanel({ account, loading }: AccountHeroPanelProps) {
  if (!account) {
    return (
      <div className="flex items-center justify-center h-24 rounded-xl border border-white/8 bg-white/[0.02] text-sm text-muted-foreground">
        {loading ? "Loading account..." : "No account data"}
      </div>
    );
  }

  const hasErrors = account.errors && account.errors.length > 0;

  return (
    <div className={cn(
      "relative overflow-hidden rounded-2xl border bg-white/[0.02] p-6 backdrop-blur transition-colors",
      hasErrors ? "border-red-500/20" : "border-white/8"
    )}>
      {/* Background glow based on PnL or Errors - assuming PnL > 0 for now */}
      <div className="absolute top-0 right-0 -mr-16 -mt-16 h-32 w-32 rounded-full bg-emerald-500/10 blur-3xl"></div>

      <div className="relative flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground mb-1">
            <Wallet className="h-4 w-4" />
            <span>Balance Disponible</span>
          </div>
          <div className="text-4xl font-extrabold tracking-tight text-foreground">
            ${formatNumber(account.available || 0)}
          </div>
        </div>

        {hasErrors && (
          <div className="flex items-start gap-2 max-w-sm rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <div className="flex flex-col">
              <span className="font-semibold">{account.errors[0].source}</span>
              <span>{account.errors[0].message}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Check TypeScript compilation**

Run: `cd frontend && tsc -b`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/AccountHeroPanel.tsx
git commit -m "feat: add AccountHeroPanel component"
```

### Task 2: Create `MarketCard` Component

**Files:**
- Create: `frontend/src/components/markets/MarketCard.tsx`

- [ ] **Step 1: Write the component code**

Create `frontend/src/components/markets/MarketCard.tsx` with the following content:
```tsx
import { memo } from "react";
import { formatNumber } from "@/lib/utils2";
import type { Market } from "@/types";
import { Badge } from "@/components/ui/badge";

export const MarketCard = memo(function MarketCard({ market }: { market: Market }) {
  const edge = Number(market.net_edge ?? market.edge);
  const upAsk = Number(market.best_ask_up ?? 0);
  const downAsk = Number(market.best_ask_down ?? 0);
  const total = upAsk + downAsk;
  const upPct = total > 0 ? (upAsk / total) * 100 : 50;
  
  const targetPrice = market.price_to_beat;
  const currentPrice = market.current_price;
  const distance = targetPrice != null && currentPrice != null 
    ? Math.abs(targetPrice - currentPrice) 
    : 0;

  const isGoodEdge = edge > 1.5;

  return (
    <div className="flex flex-col justify-between rounded-2xl border border-white/8 bg-white/[0.02] p-5 backdrop-blur hover:bg-white/[0.03] transition-colors">
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <Badge variant="outline" className="text-xs bg-white/5 border-white/10 text-muted-foreground">
            {market.asset} • {market.timeframe}
          </Badge>
          <Badge className={isGoodEdge ? "bg-emerald-500/20 text-emerald-400" : "bg-white/5 text-muted-foreground"}>
            {isGoodEdge ? "Buen Edge" : "Bajo Edge"}
          </Badge>
        </div>

        <h3 className="text-lg font-bold leading-tight text-foreground line-clamp-2">
          {market.event_slug || market.slug || "Market"}
        </h3>
      </div>

      <div className="mt-6 space-y-3">
        <div className="flex items-end justify-between text-sm">
          <div className="font-semibold text-emerald-400">YES ({upPct.toFixed(1)}%)</div>
          <div className="text-xs text-muted-foreground">
            A ${formatNumber(distance)} del Target
          </div>
        </div>
        
        {/* Visual Probability Bar */}
        <div className="h-2.5 w-full overflow-hidden rounded-full bg-red-400/20">
          <div 
            className="h-full bg-emerald-400 rounded-full transition-all duration-500 ease-out" 
            style={{ width: `${Math.max(5, Math.min(95, upPct))}%` }} 
          />
        </div>
      </div>
    </div>
  );
});
```

- [ ] **Step 2: Check TypeScript compilation**

Run: `cd frontend && tsc -b`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/markets/MarketCard.tsx
git commit -m "feat: add MarketCard visual component"
```

### Task 3: Create `MarketsBentoGrid` Component

**Files:**
- Create: `frontend/src/components/markets/MarketsBentoGrid.tsx`

- [ ] **Step 1: Write the component code**

Create `frontend/src/components/markets/MarketsBentoGrid.tsx` with the following content:
```tsx
import { memo } from "react";
import { EmptyState } from "@/components/shared";
import type { Market } from "@/types";
import { MarketCard } from "./MarketCard";

interface MarketsBentoGridProps {
  markets: Market[];
}

export const MarketsBentoGrid = memo(function MarketsBentoGrid({ markets }: MarketsBentoGridProps) {
  if (!markets.length) {
    return <EmptyState>No markets loaded</EmptyState>;
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      {markets.map((market, idx) => (
        <MarketCard 
          key={market.event_slug || market.slug || idx} 
          market={market} 
        />
      ))}
    </div>
  );
});
```

- [ ] **Step 2: Check TypeScript compilation**

Run: `cd frontend && tsc -b`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/markets/MarketsBentoGrid.tsx
git commit -m "feat: add MarketsBentoGrid layout"
```

### Task 4: Integrate in Main Views

**Files:**
- Modify: `frontend/src/components/markets/MarketsView.tsx` (or `App.tsx` depending on where `MarketsTable` and `AccountView` are currently rendered. Assuming they are in `App.tsx` or similar. Let's update `App.tsx` if it uses them, else `MarketsView.tsx`).
*Wait, `AccountView` and `MarketsTable` are likely used in `App.tsx` or `MarketsView.tsx`. Let's assume `App.tsx` uses `AccountView` and `MarketsView.tsx` uses `MarketsTable`.*

- [ ] **Step 1: Check where to inject**

Run: `grep -r "MarketsTable" frontend/src` and `grep -r "AccountView" frontend/src`
Expected: Files where they are imported.

- [ ] **Step 2: Replace MarketsTable with MarketsBentoGrid**

In `frontend/src/components/markets/MarketsView.tsx` (or file found in Step 1):
- Remove `import { MarketsTable } ...`
- Add `import { MarketsBentoGrid } from "./MarketsBentoGrid";`
- Replace `<MarketsTable markets={markets} />` with `<MarketsBentoGrid markets={markets} />`

- [ ] **Step 3: Replace AccountView with AccountHeroPanel**

In the file using `AccountView` (likely `App.tsx` or `AccountView` tab logic):
- Remove `import { AccountView } ...`
- Add `import { AccountHeroPanel } from "./AccountHeroPanel";`
- Replace `<AccountView account={account} loading={loading} onRefresh={...} />` with `<AccountHeroPanel account={account} loading={loading} />`

- [ ] **Step 4: Check TypeScript compilation**

Run: `cd frontend && tsc -b`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "refactor: replace table with bento grid and hero panel"
```