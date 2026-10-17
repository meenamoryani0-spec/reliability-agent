import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

export const metadata: Metadata = {
  title: "Reliability — AI Reliability Agent",
  description: "An evidence-led local workspace for service health, investigation, and verified recovery.",
  robots: { index: false, follow: false },
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}><body>{children}</body></html>;
}
