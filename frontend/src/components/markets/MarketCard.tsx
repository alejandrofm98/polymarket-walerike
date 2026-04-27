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
            A ${formatNumber(distance, 4)} del Target
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
