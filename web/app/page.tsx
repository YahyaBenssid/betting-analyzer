"use client";
import { useState, useCallback } from "react";
import useSWR from "swr";
import clsx from "clsx";
import KpiCard from "../components/KpiCard";
import ValueBetsTable from "../components/ValueBetsTable";
import ArbitrageCard from "../components/ArbitrageCard";
import { swrFetcher, scanKey } from "../lib/api";
import type { ScanParams } from "../lib/api";

const SPORTS = ["football", "tennis", "basketball", "hockey", "all"] as const;

export default function Dashboard() {
  const [params, setParams] = useState<ScanParams>({
    sport: "football", min_ev: 3, min_confidence: 55, bankroll: 1000,
  });
  const [pending, setPending] = useState<ScanParams>(params);
  const [tab, setTab] = useState<"bets" | "arb">("bets");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const { data, error, isLoading, mutate, isValidating } = useSWR(
    scanKey(params),
    swrFetcher,
    { refreshInterval: 60_000, revalidateOnFocus: false },
  );

  const apply = useCallback(() => { setParams(pending); setSidebarOpen(false); }, [pending]);

  const bestEv = data?.value_bets.length
    ? Math.max(...data.value_bets.map(b => b.ev_pct))
    : null;
  const recommended = data?.value_bets.filter(b => b.is_recommended).length ?? 0;

  const now = new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

  return (
    <div className="relative min-h-screen bg-bg-base bg-grid-fade">
      {/* ── TOP BAR ─────────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 border-b border-border bg-bg-base/90 backdrop-blur-md">
        <div className="flex items-center justify-between px-5 py-3 max-w-screen-2xl mx-auto">
          <div className="flex items-center gap-3">
            {/* Mobile sidebar toggle */}
            <button
              className="lg:hidden text-fg-soft hover:text-fg mr-1"
              onClick={() => setSidebarOpen(v => !v)}
            >☰</button>
            <span className="text-lg font-bold tracking-tight text-fg">🏆 Betting Analyzer</span>
            <span className="hidden sm:inline text-2xs uppercase tracking-[0.2em] text-fg-faint mono border border-border px-2 py-0.5 rounded">
              PRO
            </span>
          </div>
          <div className="flex items-center gap-4">
            {isValidating && (
              <span className="text-2xs text-jade mono animate-pulse-slow">● LIVE</span>
            )}
            <span className="text-2xs text-fg-faint mono hidden sm:block">
              {data ? `${data.total_matches} matchs · màj ${now}` : "—"}
            </span>
            {error && (
              <span className="text-2xs text-coral mono border border-coral/20 bg-coral-glow px-2 py-0.5 rounded">
                API indisponible
              </span>
            )}
          </div>
        </div>
      </header>

      <div className="max-w-screen-2xl mx-auto flex">
        {/* ── SIDEBAR ─────────────────────────────────────────────── */}
        <aside className={clsx(
          "fixed lg:sticky top-0 lg:top-[49px] z-20 h-screen lg:h-[calc(100vh-49px)] w-64 bg-bg-base border-r border-border flex flex-col",
          "transition-transform duration-200 ease-out",
          sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
        )}>
          {/* Mobile close */}
          <div className="lg:hidden flex justify-between items-center px-4 py-3 border-b border-border">
            <span className="text-xs text-fg-soft mono uppercase tracking-widest">Filtres</span>
            <button className="text-fg-soft" onClick={() => setSidebarOpen(false)}>✕</button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-6">
            {/* Sport */}
            <div>
              <label className="block text-2xs uppercase tracking-[0.16em] text-fg-faint mono mb-2">Sport</label>
              <div className="space-y-1">
                {SPORTS.map(s => (
                  <button
                    key={s}
                    onClick={() => setPending(p => ({ ...p, sport: s }))}
                    className={clsx(
                      "w-full text-left px-3 py-1.5 rounded text-sm transition-colors",
                      pending.sport === s
                        ? "bg-jade/15 text-jade border border-jade/25"
                        : "text-fg-soft hover:text-fg hover:bg-bg-raised border border-transparent",
                    )}
                  >
                    {s === "football" ? "⚽" : s === "tennis" ? "🎾" : s === "basketball" ? "🏀" : s === "hockey" ? "🏒" : "🌐"}&nbsp;
                    {s.charAt(0).toUpperCase() + s.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            {/* EV min */}
            <div>
              <label className="flex justify-between text-2xs uppercase tracking-[0.16em] text-fg-faint mono mb-2">
                <span>EV minimum</span>
                <span className="text-jade mono">{pending.min_ev}%</span>
              </label>
              <input
                type="range" min={0} max={20} step={0.5}
                value={pending.min_ev}
                onChange={e => setPending(p => ({ ...p, min_ev: Number(e.target.value) }))}
                className="w-full accent-jade h-0.5 bg-border rounded cursor-pointer"
              />
              <div className="flex justify-between text-2xs text-fg-faint mono mt-1">
                <span>0%</span><span>20%</span>
              </div>
            </div>

            {/* Confiance min */}
            <div>
              <label className="flex justify-between text-2xs uppercase tracking-[0.16em] text-fg-faint mono mb-2">
                <span>Confiance min</span>
                <span className="text-jade mono">{pending.min_confidence}</span>
              </label>
              <input
                type="range" min={0} max={100} step={5}
                value={pending.min_confidence}
                onChange={e => setPending(p => ({ ...p, min_confidence: Number(e.target.value) }))}
                className="w-full accent-jade h-0.5 bg-border rounded cursor-pointer"
              />
              <div className="flex justify-between text-2xs text-fg-faint mono mt-1">
                <span>0</span><span>100</span>
              </div>
            </div>

            {/* Bankroll */}
            <div>
              <label className="block text-2xs uppercase tracking-[0.16em] text-fg-faint mono mb-2">Bankroll (€)</label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-fg-faint mono text-xs">€</span>
                <input
                  type="number" min={100} step={100}
                  value={pending.bankroll}
                  onChange={e => setPending(p => ({ ...p, bankroll: Number(e.target.value) }))}
                  className="w-full bg-bg-card border border-border rounded px-3 pl-7 py-2 text-sm mono text-fg focus:outline-none focus:border-jade/50"
                />
              </div>
            </div>
          </div>

          {/* Apply button */}
          <div className="p-4 border-t border-border">
            <button
              onClick={apply}
              className="w-full py-2 rounded bg-jade text-bg-base text-sm font-semibold tracking-wide hover:bg-jade-bright transition-colors"
            >
              🔄 Actualiser
            </button>
            <button
              onClick={() => mutate()}
              className="w-full mt-2 py-2 rounded border border-border text-fg-soft text-xs hover:text-fg hover:border-border-strong transition-colors"
            >
              Forcer le rechargement
            </button>
          </div>
        </aside>

        {/* Mobile overlay */}
        {sidebarOpen && (
          <div className="fixed inset-0 bg-black/50 z-10 lg:hidden" onClick={() => setSidebarOpen(false)} />
        )}

        {/* ── MAIN CONTENT ────────────────────────────────────────── */}
        <main className="flex-1 min-w-0 p-4 lg:p-6 space-y-5">
          {/* KPI Row */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            <KpiCard
              title="Matchs analysés"
              value={isLoading ? "…" : (data?.total_matches ?? "—")}
              accent="neutral"
            />
            <KpiCard
              title="Value bets"
              value={isLoading ? "…" : (data?.value_bets.length ?? "—")}
              accent="jade" glow
            />
            <KpiCard
              title="Recommandés"
              value={isLoading ? "…" : recommended}
              subtitle={`≥ EV ${params.min_ev}% & conf ${params.min_confidence}`}
              accent="gold" glow
            />
            <KpiCard
              title="Meilleur EV"
              value={isLoading ? "…" : bestEv != null ? `+${bestEv.toFixed(1)}%` : "—"}
              accent={bestEv != null && bestEv > 0 ? "jade" : "neutral"}
              glow={bestEv != null && bestEv > 5}
            />
            <KpiCard
              title="Arbitrages"
              value={isLoading ? "…" : (data?.arbitrages.length ?? "—")}
              accent={data?.arbitrages.length ? "jade" : "neutral"}
            />
          </div>

          {/* Tabs */}
          <div className="border-b border-border flex gap-0">
            {[
              { id: "bets" as const,  label: "📊 Value Bets", count: data?.value_bets.length },
              { id: "arb"  as const,  label: "⚡ Arbitrages", count: data?.arbitrages.length },
            ].map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={clsx(
                  "px-4 py-2.5 text-sm border-b-2 transition-colors relative -mb-px",
                  tab === t.id
                    ? "border-jade text-jade"
                    : "border-transparent text-fg-soft hover:text-fg",
                )}
              >
                {t.label}
                {t.count != null && t.count > 0 && (
                  <span className={clsx(
                    "ml-2 mono text-2xs px-1.5 py-0.5 rounded",
                    tab === t.id ? "bg-jade/15 text-jade" : "bg-border text-fg-faint",
                  )}>
                    {t.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <div className="rounded-lg border border-border bg-bg-card overflow-hidden">
            {tab === "bets" && (
              <ValueBetsTable bets={data?.value_bets ?? []} loading={isLoading} />
            )}

            {tab === "arb" && (
              <div className="p-4 space-y-3">
                {isLoading ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="skeleton h-28 rounded-lg" />
                  ))
                ) : !data?.arbitrages.length ? (
                  <p className="text-center text-fg-faint text-sm py-16">
                    Aucune opportunité d&apos;arbitrage détectée avec ces critères
                  </p>
                ) : (
                  data.arbitrages.map((arb, i) => (
                    <ArbitrageCard key={`${arb.match_id}-${i}`} arb={arb} />
                  ))
                )}
              </div>
            )}
          </div>

          {/* Disclaimer */}
          <div className="rounded-lg border border-coral/20 bg-coral-glow px-4 py-3 flex gap-3 items-start">
            <span className="text-coral shrink-0 mt-0.5">⚠</span>
            <p className="text-xs text-fg-soft leading-relaxed">
              <span className="text-coral font-semibold">Avertissement :</span>{" "}
              Cet outil est fourni à des fins <strong>éducatives et d&apos;analyse statistique uniquement</strong>.
              Les paris sportifs comportent des risques financiers élevés.
              Ne misez jamais plus que ce que vous pouvez vous permettre de perdre.
              Vérifiez la légalité des paris en ligne dans votre pays.
              Les performances passées ne garantissent pas les résultats futurs.
            </p>
          </div>
        </main>
      </div>
    </div>
  );
}
