import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Onboarding Console",
  description: "Take a SaaS customer from configuration through go-live.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="topbar">
          <Link href="/" className="brand">
            Onboarding Console <span>· Customer integration</span>
          </Link>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
