import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "la plataforma anterior",
  description: "Plataforma de Billing SIP Class 4/5 — Carriers, Clientes y CDRs",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
