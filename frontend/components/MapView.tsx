"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl, { type Map as MapLibreMap, type MapMouseEvent } from "maplibre-gl";
import type { Feature, FeatureCollection, MultiPolygon, Point, Polygon } from "geojson";
import { DISTRICT_GEOJSON_URL, districtKey } from "../lib/districts";
import type { Job, MapMode } from "../types";
import LeafletMapView from "./LeafletMapView";

type RadarCenter = { longitude: number; latitude: number };
export type MapViewProps = {
  jobs: Job[];
  mode: MapMode;
  radarCenter: RadarCenter;
  radarRadiusKm: number;
  selectedDistrictKey: string | null;
  onSelectJob: (jobId: string) => void;
  onSelectDistrict: (districtKey: string) => void;
};

const INITIAL_CENTER: [number, number] = [-77.043, -12.046];

function supportsWebGL2(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2"));
  } catch {
    return false;
  }
}

function pointFeatures(jobs: Job[]): FeatureCollection<Point, Job> {
  return {
    type: "FeatureCollection",
    features: jobs
      .filter((job) => job.latitude !== null && job.longitude !== null)
      .map((job) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [job.longitude as number, job.latitude as number] },
        properties: job,
      })),
  };
}

function circlePolygon(center: RadarCenter, radiusKm: number): Feature<Polygon> {
  const points: [number, number][] = [];
  const earthRadiusKm = 6371;
  const angularDistance = radiusKm / earthRadiusKm;
  const latitude = (center.latitude * Math.PI) / 180;
  const longitude = (center.longitude * Math.PI) / 180;
  for (let bearing = 0; bearing <= 360; bearing += 5) {
    const bearingRadians = (bearing * Math.PI) / 180;
    const pointLatitude = Math.asin(
      Math.sin(latitude) * Math.cos(angularDistance) +
        Math.cos(latitude) * Math.sin(angularDistance) * Math.cos(bearingRadians),
    );
    const pointLongitude =
      longitude +
      Math.atan2(
        Math.sin(bearingRadians) * Math.sin(angularDistance) * Math.cos(latitude),
        Math.cos(angularDistance) - Math.sin(latitude) * Math.sin(pointLatitude),
      );
    points.push([(pointLongitude * 180) / Math.PI, (pointLatitude * 180) / Math.PI]);
  }
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [points] } };
}

function radarFeatures(center: RadarCenter, activeRadius: number): FeatureCollection<Polygon> {
  return { type: "FeatureCollection", features: [2, 5, 10].map((radius) => ({ ...circlePolygon(center, radius), properties: { radiusKm: radius, active: radius === activeRadius } })) };
}

function RadarOverlay({ mode, activeRadius }: { mode: MapMode; activeRadius: number }) {
  if (mode !== "radar") return null;
  return (
    <div className="radar-overlay" aria-hidden="true">
      {[10, 5, 2].map((radius) => <span key={radius} className={`radar-overlay-ring radar-overlay-ring-${radius} ${activeRadius === radius ? "active" : ""}`} />)}
      <span className="radar-overlay-center" />
    </div>
  );
}

type DistrictCount = { district: string; districtKey: string; job_count: number };

function districtCountFeatures(jobs: Job[]): FeatureCollection<Point, DistrictCount> {
  const groups = new Map<string, { district: string; count: number; latitude: number; longitude: number }>();
  for (const job of jobs) {
    const key = districtKey(job.district);
    if (!key || job.latitude === null || job.longitude === null) continue;
    const current = groups.get(key);
    if (current) {
      current.count += 1;
      current.latitude = (current.latitude * (current.count - 1) + job.latitude) / current.count;
      current.longitude = (current.longitude * (current.count - 1) + job.longitude) / current.count;
    } else {
      groups.set(key, { district: job.district as string, count: 1, latitude: job.latitude, longitude: job.longitude });
    }
  }
  return {
    type: "FeatureCollection",
    features: [...groups.entries()].map(([key, group]) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [group.longitude, group.latitude] },
      properties: { district: group.district, districtKey: key, job_count: group.count },
    })),
  };
}

type DistrictProperties = Record<string, unknown> & { district_key?: string | null; district_label?: string };

function normalizeDistrictGeoJson(payload: FeatureCollection<Polygon | MultiPolygon, Record<string, unknown>>) {
  return {
    ...payload,
    features: payload.features.map((feature) => {
      const raw = String(feature.properties?.distrito2 || feature.properties?.distrito || "");
      return {
        ...feature,
        properties: { ...(feature.properties || {}), district_key: districtKey(raw), district_label: raw } as DistrictProperties,
      };
    }),
  };
}

export default function MapView(props: MapViewProps) {
  const { jobs, mode, radarCenter, radarRadiusKm, selectedDistrictKey, onSelectJob, onSelectDistrict } = props;
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const modeRef = useRef(mode);
  const jobsRef = useRef(jobs);
  const selectedDistrictRef = useRef(selectedDistrictKey);
  const districtsReadyRef = useRef(false);
  const districtStateKeysRef = useRef(new Set<string>());
  const [webglAvailable, setWebglAvailable] = useState<boolean | null>(null);

  useEffect(() => { setWebglAvailable(supportsWebGL2()); }, []);

  useEffect(() => { modeRef.current = mode; }, [mode]);
  useEffect(() => { jobsRef.current = jobs; }, [jobs]);
  useEffect(() => { selectedDistrictRef.current = selectedDistrictKey; }, [selectedDistrictKey]);

  function focusDistrict(map: MapLibreMap, key: string | null) {
    if (!key) return;
    const summary = districtCountFeatures(jobsRef.current).features.find((feature) => feature.properties?.districtKey === key);
    if (summary) map.easeTo({ center: summary.geometry.coordinates as [number, number], zoom: Math.max(map.getZoom(), 12) });
  }

  function syncDistrictState(map: MapLibreMap, currentJobs: Job[], selectedKey: string | null) {
    if (!districtsReadyRef.current) return;
    for (const key of districtStateKeysRef.current) {
      map.setFeatureState({ source: "districts", id: key }, { job_count: 0, selected: false });
    }
    const counts = new Map<string, number>();
    for (const job of currentJobs) {
      const key = districtKey(job.district);
      if (key) counts.set(key, (counts.get(key) || 0) + 1);
    }
    for (const [key, count] of counts) {
      map.setFeatureState({ source: "districts", id: key }, { job_count: count, selected: key === selectedKey });
    }
    if (selectedKey) map.setFeatureState({ source: "districts", id: selectedKey }, { selected: true, job_count: counts.get(selectedKey) || 0 });
    districtStateKeysRef.current = new Set([...counts.keys(), ...(selectedKey ? [selectedKey] : [])]);
  }

  function setModeVisibility(map: MapLibreMap, nextMode: MapMode) {
    const showDistricts = nextMode === "heatmap";
    for (const layer of ["district-fill", "district-labels"]) {
      if (map.getLayer(layer)) map.setLayoutProperty(layer, "visibility", showDistricts ? "visible" : "none");
    }
    if (map.getLayer("district-outline")) map.setLayoutProperty("district-outline", "visibility", showDistricts || Boolean(selectedDistrictRef.current) ? "visible" : "none");
    for (const layer of ["clusters", "cluster-count", "job-points"]) {
      if (map.getLayer(layer)) map.setLayoutProperty(layer, "visibility", nextMode === "heatmap" ? "none" : "visible");
    }
    if (map.getLayer("jobs-heat")) map.setLayoutProperty("jobs-heat", "visibility", "none");
    for (const layer of ["radar-fill", "radar-lines", "radar-center-halo", "radar-center-point"]) {
      if (map.getLayer(layer)) map.setLayoutProperty(layer, "visibility", nextMode === "radar" ? "visible" : "none");
    }
  }

  function setRadarInteractionLock(map: MapLibreMap, locked: boolean) {
    const handlers = [map.dragPan, map.scrollZoom, map.boxZoom, map.doubleClickZoom, map.touchZoomRotate, map.keyboard];
    for (const handler of handlers) {
      if (locked) handler.disable();
      else handler.enable();
    }
  }

  useEffect(() => {
    if (webglAvailable !== true) return;
    if (!containerRef.current) return;
    const map = new maplibregl.Map({ container: containerRef.current, style: "https://tiles.openfreemap.org/styles/dark", center: INITIAL_CENTER, zoom: 10.7, minZoom: 9, maxZoom: 17 });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;

    map.on("load", () => {
      map.addSource("districts", { type: "geojson", data: { type: "FeatureCollection", features: [] }, promoteId: "district_key" });
      map.addLayer({
        id: "district-fill",
        type: "fill",
        source: "districts",
        paint: {
          "fill-color": ["interpolate", ["linear"], ["coalesce", ["feature-state", "job_count"], 0], 0, "#182329", 1, "#1d3439", 3, "#25504d", 8, "#2f7770", 15, "#43a89b", 30, "#65d4c0"],
          "fill-opacity": ["case", ["boolean", ["feature-state", "selected"], false], 0.86, 0.62],
        },
      });
      map.addLayer({
        id: "district-outline",
        type: "line",
        source: "districts",
        paint: {
          "line-color": ["case", ["boolean", ["feature-state", "selected"], false], "#45c7b5", "#53706f"],
          "line-width": ["case", ["boolean", ["feature-state", "selected"], false], 3.2, 0.8],
          "line-opacity": ["case", ["boolean", ["feature-state", "selected"], false], 1, 0.62],
        },
      });
      map.addSource("district-counts", { type: "geojson", data: districtCountFeatures(jobs) });
      map.addLayer({
        id: "district-labels",
        type: "symbol",
        source: "district-counts",
        layout: { "text-field": ["concat", ["get", "district"], "\n", ["to-string", ["get", "job_count"]], " ofertas"], "text-size": 11, "text-font": ["Open Sans Bold"], "text-anchor": "center", "text-allow-overlap": false },
        paint: { "text-color": "#c9fff7", "text-halo-color": "#102027", "text-halo-width": 1.6 },
      });
      fetch(DISTRICT_GEOJSON_URL)
        .then((response) => response.json())
        .then((payload: FeatureCollection<Polygon | MultiPolygon, Record<string, unknown>>) => {
          const source = map.getSource("districts") as maplibregl.GeoJSONSource;
          source.setData(normalizeDistrictGeoJson(payload));
          districtsReadyRef.current = true;
          window.setTimeout(() => syncDistrictState(map, jobsRef.current, selectedDistrictRef.current), 150);
        })
        .catch(() => undefined);
      map.addSource("jobs", { type: "geojson", data: pointFeatures(jobs), cluster: true, clusterMaxZoom: 13, clusterRadius: 48 });
      map.addLayer({ id: "jobs-heat", type: "heatmap", source: "jobs", maxzoom: 14, paint: { "heatmap-weight": ["interpolate", ["linear"], ["get", "location_confidence"], 0, 0.4, 1, 1], "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 9, 0.8, 14, 2.5], "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 9, 22, 14, 35], "heatmap-opacity": 0.82 } });
      map.addLayer({ id: "clusters", type: "circle", source: "jobs", filter: ["has", "point_count"], paint: { "circle-color": ["step", ["get", "point_count"], "#4f46e5", 10, "#7c3aed", 30, "#db2777"], "circle-radius": ["step", ["get", "point_count"], 20, 10, 25, 30, 31], "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 } });
      map.addLayer({ id: "cluster-count", type: "symbol", source: "jobs", filter: ["has", "point_count"], layout: { "text-field": "{point_count_abbreviated}", "text-size": 12 }, paint: { "text-color": "#ffffff" } });
      map.addLayer({ id: "job-points", type: "circle", source: "jobs", filter: ["!", ["has", "point_count"]], paint: { "circle-color": "#0f766e", "circle-radius": 7, "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 } });
      map.addSource("radar-rings", { type: "geojson", data: radarFeatures(radarCenter, radarRadiusKm) });
      map.addLayer({ id: "radar-fill", type: "fill", source: "radar-rings", paint: { "fill-color": "#4f46e5", "fill-opacity": ["case", ["boolean", ["get", "active"], false], 0.1, 0.012] } });
      map.addLayer({ id: "radar-lines", type: "line", source: "radar-rings", paint: { "line-color": ["case", ["boolean", ["get", "active"], false], "#8c83ff", "#5b5b91"], "line-width": ["case", ["boolean", ["get", "active"], false], 3, 1.3], "line-opacity": ["case", ["boolean", ["get", "active"], false], 0.98, 0.72] } });
      map.addSource("radar-center", { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [radarCenter.longitude, radarCenter.latitude] } } });
      map.addLayer({ id: "radar-center-halo", type: "circle", source: "radar-center", paint: { "circle-color": "#10a37f", "circle-radius": 15, "circle-opacity": 0.18, "circle-stroke-color": "#72d8bd", "circle-stroke-width": 1, "circle-stroke-opacity": 0.8 } });
      map.addLayer({ id: "radar-center-point", type: "circle", source: "radar-center", paint: { "circle-color": "#4f46e5", "circle-radius": 6, "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 } });
      setModeVisibility(map, mode);
      setRadarInteractionLock(map, mode === "radar");
      map.once("idle", () => setModeVisibility(map, modeRef.current));
    });

    map.on("click", "clusters", async (event: MapMouseEvent) => {
      const feature = map.queryRenderedFeatures(event.point, { layers: ["clusters"] })[0];
      if (!feature) return;
      const source = map.getSource("jobs") as maplibregl.GeoJSONSource;
      const zoom = await source.getClusterExpansionZoom(feature.properties?.cluster_id);
      map.easeTo({ center: (feature.geometry as Point).coordinates as [number, number], zoom });
    });
    map.on("click", "job-points", (event) => {
      const feature = map.queryRenderedFeatures(event.point, { layers: ["job-points"] })[0];
      if (feature?.properties?.id) onSelectJob(String(feature.properties.id));
    });
    map.on("click", "district-fill", (event) => {
      const feature = map.queryRenderedFeatures(event.point, { layers: ["district-fill"] })[0];
      if (feature?.properties?.district_key) onSelectDistrict(String(feature.properties.district_key));
    });
    map.on("click", "district-labels", (event) => {
      const feature = map.queryRenderedFeatures(event.point, { layers: ["district-labels"] })[0];
      if (feature?.properties?.districtKey) onSelectDistrict(String(feature.properties.districtKey));
    });
    for (const layer of ["clusters", "job-points", "district-fill", "district-labels"]) {
      map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
    }
    return () => {
      map.remove();
      mapRef.current = null;
    };
    // The map is created once; data and display state are synchronized below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [webglAvailable]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    (map.getSource("jobs") as maplibregl.GeoJSONSource | undefined)?.setData(pointFeatures(jobs));
    (map.getSource("district-counts") as maplibregl.GeoJSONSource | undefined)?.setData(districtCountFeatures(jobs));
    syncDistrictState(map, jobs, selectedDistrictRef.current);
  }, [jobs]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const applyMode = () => {
      if (!map.isStyleLoaded()) return;
      setModeVisibility(map, mode);
      setRadarInteractionLock(map, mode === "radar");
    };
    if (map.isStyleLoaded()) applyMode();
    else map.once("load", applyMode);
    return () => { map.off("load", applyMode); };
  }, [mode]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    syncDistrictState(map, jobsRef.current, selectedDistrictKey);
    setModeVisibility(map, modeRef.current);
    if (selectedDistrictKey) focusDistrict(map, selectedDistrictKey);
  }, [selectedDistrictKey]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const applyRadarState = () => {
      if (!map.isStyleLoaded()) return;
      if (mode === "radar") map.easeTo({ center: [radarCenter.longitude, radarCenter.latitude], zoom: 13, duration: 700 });
      (map.getSource("radar-rings") as maplibregl.GeoJSONSource | undefined)?.setData(radarFeatures(radarCenter, radarRadiusKm));
      (map.getSource("radar-center") as maplibregl.GeoJSONSource | undefined)?.setData({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [radarCenter.longitude, radarCenter.latitude] } });
      setModeVisibility(map, mode);
      setRadarInteractionLock(map, mode === "radar");
    };
    if (map.isStyleLoaded()) applyRadarState();
    else map.once("load", applyRadarState);
    return () => { map.off("load", applyRadarState); };
  }, [mode, radarCenter, radarRadiusKm]);

  if (webglAvailable === false) return <div className="map-canvas"><LeafletMapView {...props} /><RadarOverlay mode={mode} activeRadius={radarRadiusKm} /></div>;
  if (webglAvailable === null) return <div className="map-loading">Preparando mapa…</div>;
  return <div ref={containerRef} className="map-canvas" aria-label="Mapa de ofertas laborales de Lima"><RadarOverlay mode={mode} activeRadius={radarRadiusKm} /></div>;
}
