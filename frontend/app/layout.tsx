import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Governance AI · IEEE SMCS",
  description: "Authority-aware IEEE SMCS governance assistant",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
