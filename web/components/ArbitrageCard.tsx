"use client";
import clsx from "clsx";
import type { Arbitrage } from "../lib/types";

export default function ArbitrageCard({ arb }: { arb: Arbitrage }) {
  return (
    <div className="rounded-lg border border-jade/20 bg-jade-glow relative overflow-hidden p-4">
      {/* Top accent bar */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-jade/60 via-jade-bright/80 to-jade/60" />

      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-2xs uppercase tracking-[0.15em] text-jade-bright mono">Profit garanti</span>
          </div>
          <p className="text-fg font-semibold text-sm">
            {arb.home_team} <span className="text-fg-faint font-normal">vs</span> {arb.away_team}
          </p>
          <p className="text-fg-soft text-xs mt-0.5">{arb.league} · {arb.market}</p>
        </div>
        <div className="text-right shrink-0">
          <p className="mono text-2xl font-medium text-jade-bright glow-jade leading-none">
            +{arb.profit_pct.toFixed(2)}%
          </p>
          <p className="mono text-xs text-jade mt-0.5">+€{arb.guaranteed_profit.toFixed(2)}</p>
        </div>
      </div>

      {/* Outcome breakdown */}
      <div className={clsx("grid gap-2", `grid-cols-${Math.min(arb.outcomes.length, 3)}`)}>
        {arb.outcomes.map((outcome, i) => (
          <div key={i} className="rounded border border-border bg-bg-card/60 p-2.5">
            <p className="text-2xs uppercase tracking-[0.12em] text-fg-faint mono mb-1">{outcome}</p>
            <p className="mono text-sm text-fg font-medium">@{arb.odds[i].toFixed(2)}</p>
            <p className="mono text-xs text-fg-soft mt-0.5">
              Mise: <span className="text-jade">€{arb.stakes[i].toFixed(2)}</span>
            </p>
            {arb.bookmakers[i] && arb.bookmakers[i] !== "1xbet" && (
              <p className="text-2xs text-fg-faint mt-1 mono">{arb.bookmakers[i]}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
