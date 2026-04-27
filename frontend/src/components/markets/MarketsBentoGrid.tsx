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