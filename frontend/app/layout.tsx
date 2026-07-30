import type { Metadata } from "next";
import { Public_Sans, Martian_Mono, Big_Shoulders } from "next/font/google";
import "./globals.css";

// Voxi Design System v2 — ver Proyectos-Public/_patterns/PATTERN_VOXI_DESIGN.md.
// Reemplaza Manrope/IBM Plex Mono (autohospedadas vía next/font, sin dependencia
// de fonts.googleapis.com en runtime — coherente con un producto que se instala
// on-prem). Big Shoulders es nueva: solo para nameplates/headings de marca
// (sidebar, landing), nunca para cuerpo de texto de UI densa.
const publicSans = Public_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-public-sans",
  display: "swap",
});
const martianMono = Martian_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-martian-mono",
  display: "swap",
});
const bigShoulders = Big_Shoulders({
  subsets: ["latin"],
  weight: ["700", "800"],
  variable: "--font-big-shoulders",
  display: "swap",
});

export const metadata: Metadata = {
  title: "VoxiKam",
  description: "Plataforma de Billing SIP Class 4 — Carriers, Clientes y CDRs",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={`${publicSans.variable} ${martianMono.variable} ${bigShoulders.variable}`}>
      <body>{children}</body>
    </html>
  );
}
