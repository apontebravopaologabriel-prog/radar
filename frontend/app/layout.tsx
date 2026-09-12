import type { Metadata } from "next";
import "./globals.css";
import "maplibre-gl/dist/maplibre-gl.css";
import "leaflet/dist/leaflet.css";

export const metadata: Metadata = {
  title: "Radar · Mercado laboral de Lima",
  description: "Explora la concentración geográfica de empleos en Lima.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
