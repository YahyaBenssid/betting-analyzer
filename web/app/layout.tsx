import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Betting Analyzer Pro",
  description: "Value bet & arbitrage detection — outil éducatif",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body className="bg-bg-base min-h-screen relative">
        {children}
      </body>
    </html>
  );
}
