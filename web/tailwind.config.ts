import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          base: "#0a0f0d",
          card: "#0f1511",
          raised: "#161d19",
          overlay: "#1c2520",
        },
        jade: {
          DEFAULT: "#2A9E6A",
          bright: "#34c47f",
          dim: "#1a6344",
          glow: "rgba(42,158,106,0.12)",
        },
        coral: {
          DEFAULT: "#E8412A",
          dim: "#7a1f12",
          glow: "rgba(232,65,42,0.12)",
        },
        gold: {
          DEFAULT: "#D4920A",
          dim: "#7a520a",
          glow: "rgba(212,146,10,0.12)",
        },
        border: {
          DEFAULT: "rgba(255,255,255,0.055)",
          strong: "rgba(255,255,255,0.10)",
          jade: "rgba(42,158,106,0.25)",
        },
        fg: {
          DEFAULT: "#d4dbd6",
          soft: "rgba(212,219,214,0.55)",
          faint: "rgba(212,219,214,0.22)",
        },
      },
      fontFamily: {
        sans: ["var(--font-syne)", "system-ui", "sans-serif"],
        mono: ["var(--font-ibm-mono)", "monospace"],
      },
      fontSize: {
        "2xs": ["0.65rem", { lineHeight: "1rem" }],
      },
      backgroundImage: {
        "scanline": "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 4px)",
        "grid-fade": "radial-gradient(ellipse 80% 60% at 50% 0%, rgba(42,158,106,0.07) 0%, transparent 70%)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4,0,0.6,1) infinite",
        "fade-in": "fadeIn 0.4s ease forwards",
        "slide-up": "slideUp 0.35s ease forwards",
      },
      keyframes: {
        fadeIn: { from: { opacity: "0" }, to: { opacity: "1" } },
        slideUp: { from: { opacity: "0", transform: "translateY(8px)" }, to: { opacity: "1", transform: "translateY(0)" } },
      },
    },
  },
  plugins: [],
};

export default config;
