"use client";
import clsx from "clsx";

interface KpiCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  accent?: "jade" | "coral" | "gold" | "neutral";
  glow?: boolean;
}

const accentStyles = {
  jade:    { border: "border-jade/30",  val: "text-jade-bright glow-jade",   bg: "bg-jade-glow" },
  coral:   { border: "border-coral/30", val: "text-coral glow-coral",        bg: "bg-coral-glow" },
  gold:    { border: "border-gold/30",  val: "text-gold glow-gold",          bg: "bg-gold-glow" },
  neutral: { border: "border-border",   val: "text-fg",                      bg: "" },
};

export default function KpiCard({ title, value, subtitle, accent = "neutral", glow = false }: KpiCardProps) {
  const s = accentStyles[accent];
  return (
    <div className={clsx(
      "relative rounded-lg border p-4 bg-bg-card overflow-hidden",
      s.border, glow && s.bg,
    )}>
      {/* Top rule */}
      <div className={clsx("absolute top-0 left-0 right-0 h-px", {
        "bg-jade/40": accent === "jade",
        "bg-coral/40": accent === "coral",
        "bg-gold/40": accent === "gold",
        "bg-border-strong": accent === "neutral",
      })} />

      <p className="text-2xs uppercase tracking-[0.18em] text-fg-soft mb-2 font-mono">{title}</p>
      <p className={clsx("mono text-2xl font-medium leading-none", s.val)}>{value}</p>
      {subtitle && (
        <p className="text-2xs text-fg-faint mt-1.5 mono">{subtitle}</p>
      )}
    </div>
  );
}
