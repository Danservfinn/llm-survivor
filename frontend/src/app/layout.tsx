import type { Metadata } from "next";
import { ModeTabs } from "@/components/navigation/ModeTabs";
import "./globals.css";

export const metadata: Metadata = {
  title: "LLM Survivor",
  description: "Benchmark LLM survivor games and run paid social strategy arena rooms",
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
