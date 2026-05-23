export interface ValueBet {
  match_id: string;
  home_team: string;
  away_team: string;
  league: string;
  sport: string;
  market: string;
  outcome: string;
  odd_value: number;
  ev_pct: number;
  kelly_pct: number;
  stake: number;
  confidence: number;
  stats_source: "real_stats" | "poisson_avg" | "fair_prob";
  is_recommended: boolean;
}

export interface Arbitrage {
  match_id: string;
  home_team: string;
  away_team: string;
  league: string;
  market: string;
  profit_pct: number;
  guaranteed_profit: number;
  outcomes: string[];
  odds: number[];
  stakes: number[];
  bookmakers: string[];
}

export interface ScanResponse {
  value_bets: ValueBet[];
  arbitrages: Arbitrage[];
  total_matches: number;
  sport: string;
  bankroll: number;
}

export type SortKey = keyof Pick<ValueBet, "ev_pct" | "kelly_pct" | "confidence" | "odd_value" | "stake">;
export type SortDir = "asc" | "desc";
