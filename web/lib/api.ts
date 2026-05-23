import type { ScanResponse } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ScanParams {
  sport?: string;
  min_ev?: number;
  min_confidence?: number;
  bankroll?: number;
  live?: boolean;
  limit?: number;
}

export async function fetchScan(params: ScanParams): Promise<ScanResponse> {
  const qs = new URLSearchParams();
  if (params.sport)          qs.set("sport",          params.sport);
  if (params.min_ev != null) qs.set("min_ev",          String(params.min_ev));
  if (params.min_confidence != null) qs.set("min_confidence", String(params.min_confidence));
  if (params.bankroll != null) qs.set("bankroll",      String(params.bankroll));
  if (params.live)           qs.set("live",            "true");
  if (params.limit)          qs.set("limit",           String(params.limit));

  const res = await fetch(`${BASE}/api/scan?${qs.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

// SWR fetcher key → params tuple
export function scanKey(params: ScanParams): [string, ScanParams] {
  return ["/api/scan", params];
}

export async function swrFetcher([, params]: [string, ScanParams]) {
  return fetchScan(params);
}
