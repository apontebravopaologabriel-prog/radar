"use client";

import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import type { FeatureCollection, MultiPolygon, Polygon } from "geojson";
import { DISTRICT_GEOJSON_URL, districtKey } from "../lib/districts";
import type { Job } from "../types";
import type { MapViewProps } from "./MapView";

const INITIAL_CENTER: L.LatLngExpression = [-12.046, -77.043];
const DISTRICT_COLORS = ["#182329", "#1d3439", "#25504d", "#2f7770", "#43a89b", "#65d4c0"];

function colorForCount(count: number, max: number) {
  if (!count || !max) return DISTRICT_COLORS[0];
  return DISTRICT_COLORS[Math.min(DISTRICT_COLORS.length - 1, Math.ceil((count / max) * (DISTRICT_COLORS.length - 1)))];
}

function jobsByDistrict(jobs: Job[]) {
  const counts = new Map<string, number>();
  for (const job of jobs) {
    const key = districtKey(job.district);
    if (key) counts.set(key, (counts.get(key) || 0) + 1);
  }
  return counts;
}

export default function LeafletMapView({ jobs, mode, radarCenter, radarRadiusKm, selectedDistrictKey, onSelectJob, onSelectDistrict }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const districtsRef = useRef<FeatureCollection<Polygon | MultiPolygon, Record<string, unknown>> | null>(null);
  const [districtVersion, setDistrictVersion] = useState(0);

  useEffect(() => {
    if (!containerRef.current) return;
    const map = L.map(containerRef.current, { minZoom: 9, maxZoom: 17 }).setView(INITIAL_CENTER, 10.7);
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", { attribution: "© OpenStreetMap contributors © CARTO", maxZoom: 19 }).addTo(map);
    mapRef.current = map;
    fetch(DISTRICT_GEOJSON_URL)
      .then((response) => response.json())
      .then((payload: FeatureCollection<Polygon | MultiPolygon, Record<string, unknown>>) => {
        districtsRef.current = payload;
        setDistrictVersion((version) => version + 1);
      })
      .catch(() => undefined);
    return () => { map.remove(); mapRef.current = null; };
    // The map instance must survive mode/filter changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const lockRadarCenter = mode === "radar";
    for (const handler of [map.dragging, map.scrollWheelZoom, map.doubleClickZoom, map.boxZoom, map.keyboard, map.touchZoom]) {
      if (lockRadarCenter) handler.disable();
      else handler.enable();
    }
    map.eachLayer((layer) => { if (!(layer instanceof L.TileLayer)) map.removeLayer(layer); });
    const counts = jobsByDistrict(jobs);
    const maxCount = Math.max(0, ...Array.from(counts.values()));

    if (mode === "heatmap" && districtsRef.current) {
      L.geoJSON(districtsRef.current, {
        style: (feature) => {
          const raw = String(feature?.properties?.distrito2 || feature?.properties?.distrito || "");
          const key = districtKey(raw);
          const selected = key !== null && key === selectedDistrictKey;
          return { color: selected ? "#45c7b5" : "#53706f", weight: selected ? 3.2 : 0.8, fillColor: colorForCount(key ? counts.get(key) || 0 : 0, maxCount), fillOpacity: selected ? 0.86 : 0.62 };
        },
        onEachFeature: (feature, layer) => {
          const raw = String(feature.properties?.distrito2 || feature.properties?.distrito || "");
          const key = districtKey(raw);
          const count = key ? counts.get(key) || 0 : 0;
          if (count) layer.bindTooltip(`${raw}<br>${count} ofertas`, { permanent: true, direction: "center", className: "district-tooltip" });
          if (key) layer.on("click", () => onSelectDistrict(key));
        },
      }).addTo(map);
    }

    if (mode !== "heatmap") {
      for (const job of jobs) {
        if (job.latitude === null || job.longitude === null) continue;
        const marker = L.circleMarker([job.latitude, job.longitude], { radius: 7, color: "#ffffff", weight: 2, fillColor: mode === "radar" ? "#4f46e5" : "#0f766e", fillOpacity: 0.95 });
        marker.bindTooltip(job.title || "Oferta laboral");
        marker.on("click", () => onSelectJob(job.id));
        marker.addTo(map);
      }
    }

    if (mode === "radar") {
      for (const radius of [2, 5, 10]) L.circle([radarCenter.latitude, radarCenter.longitude], { radius: radius * 1000, color: "#8c83ff", weight: radius === radarRadiusKm ? 3 : 1.2, opacity: radius === radarRadiusKm ? 0.95 : 0.45, dashArray: "5 5", fillColor: "#4f46e5", fillOpacity: radius === radarRadiusKm ? 0.08 : 0.02 }).addTo(map);
      L.circleMarker([radarCenter.latitude, radarCenter.longitude], { radius: 15, color: "#72d8bd", weight: 1, fillColor: "#10a37f", fillOpacity: 0.18 }).addTo(map);
      L.circleMarker([radarCenter.latitude, radarCenter.longitude], { radius: 6, color: "#ffffff", weight: 2, fillColor: "#4f46e5", fillOpacity: 1 }).addTo(map);
      map.setView([radarCenter.latitude, radarCenter.longitude], 13, { animate: true, duration: 0.7 });
    }
    if (selectedDistrictKey) {
      const selected = jobs.find((job) => districtKey(job.district) === selectedDistrictKey && job.latitude !== null && job.longitude !== null);
      if (selected) map.setView([selected.latitude as number, selected.longitude as number], Math.max(map.getZoom(), 12));
    }
  }, [jobs, mode, radarCenter, selectedDistrictKey, onSelectDistrict, onSelectJob, districtVersion]);

  return <div ref={containerRef} className="map-canvas leaflet-map" aria-label="Mapa de ofertas laborales de Lima" />;
}
