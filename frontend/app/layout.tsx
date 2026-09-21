import type { Metadata, Viewport } from "next";
import "./globals.css";
import "maplibre-gl/dist/maplibre-gl.css";
import "leaflet/dist/leaflet.css";

export const metadata: Metadata = {
  title: "Radar · Mercado laboral de Lima",
  description: "Explora la concentración geográfica de empleos en Lima.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon-192.png", apple: "/icon-180.png" },
  appleWebApp: { capable: true, title: "Radar", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#171717" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es" suppressHydrationWarning>
      <head>
        {/* Aplica el modo rendimiento antes de pintar para evitar el parpadeo de efectos. */}
        <script dangerouslySetInnerHTML={{ __html: 'try{if(localStorage.getItem("radar.perf")==="lite")document.documentElement.dataset.perf="lite"}catch(e){}' }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
