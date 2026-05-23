"use client";
import { useState } from "react";
import clsx from "clsx";
import type { ValueBet, SortKey, SortDir } from "../lib/types";

interface Props {
  bets: ValueBet[];
  loading?: boolean;
}

const SOURCE_LABEL: Record<string, { label: string; cls: string }> = {
  real_stats:  { label: "real",  cls: "bg-jade/10 text-jade border-jade/20" },
  poisson_avg: { label: "avg",   cls: "bg-fg-faint/10 text-fg-soft border-border" },
  fair_prob:   { label: "fair",  cls: "bg-bg-raised text-fg-faint border-border" },
};

function ConfPill({ v }: { v: number }) {
  const cls =
    v >= 65 ? "bg-jade/15 text-jade-bright border-jade/25" :
    v >= 50 ? "bg-gold/15 text-gold border-gold/25" :
              "bg-coral/10 text-coral/80 border-coral/20";
  return (
    <span className={clsx("mono text-xs px-2 py-0.5 rounded border inline-flex items-center gap-1.5", cls)}>
      <span className="inline-block w-12 h-1 rounded-full bg-current/20 overflow-hidden">
        <span className="block h-full rounded-full bg-current transition-all" style={{ width: `${v}%` }} />
      </span>
      {v.toFixed(0)}
    </span>
  );
}

function SortBtn({ col, active, dir, onClick }: { col: string; active: boolean; dir: SortDir; onClick: () => void }) {
  return (
    <button onClick={onClick} className="flex items-center gap-1 group">
      <span className={clsx("text-2xs uppercase tracking-[0.14em]", active ? "text-jade" : "text-fg-soft group-hover:text-fg")}>
        {col}
      </span>
      <span className={clsx("text-2xs transition-opacity", active ? "opacity-100 text-jade" : "opacity-0 group-hover:opacity-40")}>
        {dir === "desc" ? "↓" : "↑"}
      </span>
    </button>
  );
}

const SKELETON_ROWS = 8;

export default function ValueBetsTable({ bets, loading }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("confidence");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(d => d === "desc" ? "asc" : "desc");
    else { setSortKey(key); setSortDir("desc"); }
  }

  const sorted = [...bets].sort((a, b) => {
    const mul = sortDir === "desc" ? -1 : 1;
    return (a[sortKey] - b[sortKey]) * mul;
  });

  return (
    <div className="relative overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-border-strong">
            {["#", "MATCH", "LIGUE", "MARCHÉ", "OUTCOME"].map(h => (
              <th key={h} className="text-left py-3 px-3 text-2xs uppercase tracking-[0.14em] text-fg-faint font-normal whitespace-nowrap">
                {h}
              </th>
            ))}
            {(["odd_value", "ev_pct", "kelly_pct", "stake", "confidence"] as SortKey[]).map(key => (
              <th key={key} className="text-right py-3 px-3 whitespace-nowrap">
                <div className="flex justify-end">
                  <SortBtn
                    col={key === "odd_value" ? "COTE" : key === "ev_pct" ? "EV%" : key === "kelly_pct" ? "KELLY" : key === "stake" ? "MISE €" : "CONF"}
                    active={sortKey === key} dir={sortDir}
                    onClick={() => toggleSort(key)}
                  />
                </div>
              </th>
            ))}
            <th className="text-left py-3 px-3 text-2xs uppercase tracking-[0.14em] text-fg-faint font-normal">SRC</th>
            <th className="text-center py-3 px-3 text-2xs uppercase tracking-[0.14em] text-fg-faint font-normal">✓</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            Array.from({ length: SKELETON_ROWS }).map((_, i) => (
              <tr key={i} className="border-b border-border">
                {Array.from({ length: 12 }).map((_, j) => (
                  <td key={j} className="py-3 px-3">
                    <div className="skeleton h-3 rounded" style={{ width: `${40 + Math.random() * 50}%`, animationDelay: `${i * 0.05}s` }} />
                  </td>
                ))}
              </tr>
            ))
          ) : sorted.length === 0 ? (
            <tr>
              <td colSpan={12} className="py-16 text-center text-fg-faint text-sm">
                Aucun value bet avec ces critères — baissez les seuils dans la sidebar
              </td>
            </tr>
          ) : (
            sorted.map((bet, i) => {
              const src = SOURCE_LABEL[bet.stats_source] ?? SOURCE_LABEL.fair_prob;
              const evPos = bet.ev_pct > 0;
              return (
                <tr
                  key={`${bet.match_id}-${bet.outcome}-${i}`}
                  className={clsx(
                    "border-b border-border group transition-colors duration-100",
                    "hover:bg-jade-glow/30",
                    bet.is_recommended && "bg-gold-glow/20",
                  )}
                  style={{ animationDelay: `${i * 0.03}s` }}
                >
                  <td className="py-2.5 px-3 mono text-fg-faint text-xs">{i + 1}</td>
                  <td className="py-2.5 px-3 whitespace-nowrap">
                    <span className="text-fg font-medium text-xs">{bet.home_team}</span>
                    <span className="text-fg-faint mx-1">vs</span>
                    <span className="text-fg font-medium text-xs">{bet.away_team}</span>
                  </td>
                  <td className="py-2.5 px-3 text-fg-soft text-xs max-w-[120px] truncate">{bet.league}</td>
                  <td className="py-2.5 px-3 text-fg-soft text-xs">{bet.market}</td>
                  <td className="py-2.5 px-3">
                    <span className={clsx("text-xs font-medium px-2 py-0.5 rounded border", {
                      "bg-jade/10 text-jade border-jade/20":
                        bet.outcome === "Domicile" || bet.outcome.startsWith("Over") || bet.outcome.startsWith("Dom"),
                      "bg-gold/10 text-gold border-gold/20":
                        bet.outcome === "Nul",
                      "bg-fg-faint/10 text-fg-soft border-border":
                        bet.outcome === "Extérieur" || bet.outcome.startsWith("Under") || bet.outcome.startsWith("Ext"),
                    })}>
                      {bet.outcome}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-right mono text-xs text-fg">{bet.odd_value.toFixed(2)}</td>
                  <td className="py-2.5 px-3 text-right">
                    <span className={clsx("mono text-sm font-medium", evPos ? "text-jade-bright glow-jade" : "text-coral")}>
                      {evPos ? "+" : ""}{bet.ev_pct.toFixed(1)}%
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-right mono text-xs text-fg-soft">{bet.kelly_pct.toFixed(1)}%</td>
                  <td className="py-2.5 px-3 text-right mono text-xs text-fg">€{bet.stake.toFixed(0)}</td>
                  <td className="py-2.5 px-3 text-right"><ConfPill v={bet.confidence} /></td>
                  <td className="py-2.5 px-3">
                    <span className={clsx("inline-block text-xs px-1.5 py-0.5 rounded border mono", src.cls)}>
                      {src.label}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-center text-base">
                    {bet.is_recommended ? "✅" : bet.ev_pct > 0 ? "⚠️" : "—"}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
