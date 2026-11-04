"use client";

import type { Market } from "../lib/markets-api";
import "./market-controls.css";

export default function MarketControls({ markets, marketId, onMarket }: {
  markets: Market[]; marketId: string; onMarket: (id: string) => void;
}) {
  return <section className="market-controls" aria-label="Mercado">
    <label>Mercado<select value={marketId} disabled={!markets.length} onChange={(e) => onMarket(e.target.value)}>
      {!markets.length && <option value={marketId}>Cargando mercados…</option>}
      {markets.map((market) => <option key={market.id} value={market.id}>{market.name}</option>)}
    </select></label>
  </section>;
}
