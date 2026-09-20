"use client";

import { useEffect, useRef } from "react";
import L from "leaflet";
import type { MapPlace } from "../../lib/mobile-api";

type Props = {
  places: MapPlace[];
  selected: string;
  radiusKm: number;
  height: number;
  onSelect: (name: string) => void;
};

const PERU_BOUNDS: L.LatLngBoundsExpression = [[-18.4, -81.4], [-0.1, -68.6]];
const zoomFor = (km: number) => (km <= 2 ? 13 : km <= 5 ? 12 : km <= 10 ? 11 : km <= 25 ? 10 : 8);

/** Mapa ligero: un punto por lugar (no por oferta), lienzo (canvas) y sin controles de escritorio. */
export default function PlacesMap({ places, selected, radiusKm, height, onSelect }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  const select = useRef(onSelect);
  select.current = onSelect;

  useEffect(() => {
    if (!box.current) return;
    const instance = L.map(box.current, { zoomControl: false, preferCanvas: true, minZoom: 5, maxZoom: 16, attributionControl: true }).fitBounds(PERU_BOUNDS);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "© OpenStreetMap contributors", maxZoom: 19 }).addTo(instance);
    layer.current = L.layerGroup().addTo(instance);
    map.current = instance;
    return () => { instance.remove(); map.current = null; };
  }, []);

  useEffect(() => { map.current?.invalidateSize(); }, [height]);

  useEffect(() => {
    const instance = map.current; const group = layer.current;
    if (!instance || !group) return;
    group.clearLayers();
    const target = places.find((p) => p.name === selected);
    for (const place of places) {
      const active = place.name === selected;
      const marker = L.circleMarker([place.latitude, place.longitude], {
        radius: Math.min(22, 5 + Math.sqrt(place.count) * 2.4),
        color: active ? "#ffffff" : "#a6a6a6", weight: active ? 2.5 : 1,
        dashArray: place.precision === "department" ? "3 3" : undefined,
        fillColor: active ? "#ffffff" : "#6f6f6f", fillOpacity: active ? 0.85 : 0.55,
      }).on("click", () => select.current(place.name));
      if (place.count >= 3) marker.bindTooltip(String(place.count), { permanent: true, direction: "center", className: "m-map-count" });
      marker.addTo(group);
    }
    if (target && radiusKm > 0 && radiusKm <= 100) {
      L.circle([target.latitude, target.longitude], { radius: radiusKm * 1000, color: "#ececec", weight: 1, dashArray: "4 4", fillOpacity: 0.04, interactive: false }).addTo(group);
    }
    if (target && radiusKm < 500) instance.setView([target.latitude, target.longitude], zoomFor(radiusKm));
    else instance.fitBounds(PERU_BOUNDS);
  }, [places, selected, radiusKm]);

  return <div ref={box} className="m-map" style={{ height }} role="application" aria-label="Mapa de ofertas por lugar" />;
}
