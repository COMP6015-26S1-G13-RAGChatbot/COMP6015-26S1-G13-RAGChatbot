import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "IEEE RAG Assistant",
  description: "IEEE/SMCS Governance Document QA System",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}