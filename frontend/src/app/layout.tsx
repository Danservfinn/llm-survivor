import type { Metadata } from "next";
import { ModeTabs } from "@/components/navigation/ModeTabs";
import "./globals.css";

export const metadata: Metadata = {
  title: "LLM Survivor — 16-model social strategy benchmark",
  description: "Sixteen LLMs compete through challenges, alliances, votes, jury pressure, and public replay telemetry.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <ModeTabs />
        {children}
      </body>
    </html>
  );
}
