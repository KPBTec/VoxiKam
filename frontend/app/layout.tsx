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

// Setea data-theme ANTES de que React hidrate — sin esto, cada carga
// mostraría un flash del tema Bronce (default) antes de aplicar la
// preferencia guardada del usuario. Script inline bloqueante a propósito,
// mismo patrón que cualquier dark-mode-antes-de-hidratar.
const THEME_INIT_SCRIPT = `
(function () {
  try {
    var t = localStorage.getItem('voxikam_theme');
    if (t && t !== 'bronce') document.documentElement.setAttribute('data-theme', t);
  } catch (e) {}
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={`${publicSans.variable} ${martianMono.variable} ${bigShoulders.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
