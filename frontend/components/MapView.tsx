"use client";

import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { Map as MapLibreMap, MapMouseEvent } from "maplibre-gl";
import type { Feature, FeatureCollection, MultiPolygon, Point, Polygon } from "geojson";
import { loadDistrictGeoJson, districtKey } from "../lib/districts";
import type { Job, MapMode } from "../types";
import LeafletMapView from "./LeafletMapView";

type RadarCenter = { longitude: number; latitude: number };
export type MapViewProps = {
  jobs: Job[];
  mode: MapMode;
  radarCenter: RadarCenter;
  radarRadiusKm: number;
  radarDistrictKey: string | null;
  selectedDistrictKey: string | null;
  onSelectJob: (jobId: string) => void;
  onSelectDistrict: (districtKey: string) => void;
  radarCounts?: Record<number, number>;
  onPickRadarCenter?: (center: RadarCenter) => void;
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

function radarLabelFeatures(center: RadarCenter, counts: Record<number, number> | undefined, activeRadius: number): FeatureCollection<Point> {
  return {
    type: "FeatureCollection",
    features: [2, 5, 10].map((radius) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [center.longitude, center.latitude + radius / 111.32] },
      properties: { label: `${radius} km · ${counts?.[radius] ?? 0}`, active: radius === activeRadius },
    })),
  };
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
  const { jobs, mode, radarCenter, radarRadiusKm, radarDistrictKey, selectedDistrictKey, onSelectJob, onSelectDistrict, radarCounts, onPickRadarCenter } = props;
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const modeRef = useRef(mode);
  const jobsRef = useRef(jobs);
  const radarDistrictKeyRef = useRef(radarDistrictKey);
  const selectedDistrictRef = useRef(selectedDistrictKey);
  const selectJobRef = useRef(onSelectJob);
  const selectDistrictRef = useRef(onSelectDistrict);
  const pickCenterRef = useRef(onPickRadarCenter);
  const districtsReadyRef = useRef(false);
  const districtStateKeysRef = useRef(new Set<string>());
  const [webglAvailable, setWebglAvailable] = useState<boolean | null>(null);
  const [mapReady, setMapReady] = useState(false);

  useEffect(() => { setWebglAvailable(supportsWebGL2()); }, []);

  useEffect(() => { modeRef.current = mode; }, [mode]);
  useEffect(() => { selectJobRef.current = onSelectJob; selectDistrictRef.current = onSelectDistrict; pickCenterRef.current = onPickRadarCenter; });
  useEffect(() => { jobsRef.current = jobs; }, [jobs]);
  useEffect(() => { radarDistrictKeyRef.current = radarDistrictKey; }, [radarDistrictKey]);
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

  function setModeVisibility(map: MapLibreMap, nextMode: MapMode, radarActive = Boolean(radarDistrictKeyRef.current)) {
    const showDistricts = nextMode === "heatmap" || nextMode === "radar";
    // Distritos is intentionally a clean choropleth: offer bubbles belong to
    // the detail popup, not on top of the district geometry.
    const showJobLayers = nextMode === "jobs";
    for (const layer of ["district-fill", "district-labels"]) {
      if (map.getLayer(layer)) map.setLayoutProperty(layer, "visibility", showDistricts ? "visible" : "none");
    }
    if (map.getLayer("district-outline")) map.setLayoutProperty("district-outline", "visibility", showDistricts || Boolean(selectedDistrictRef.current) ? "visible" : "none");
    for (const layer of ["clusters", "cluster-count", "job-points"]) {
      if (map.getLayer(layer)) map.setLayoutProperty(layer, "visibility", showJobLayers ? "visible" : "none");
    }
    for (const layer of ["radar-fill", "radar-lines", "radar-labels"]) {
      if (map.getLayer(layer)) map.setLayoutProperty(layer, "visibility", nextMode === "radar" && radarActive ? "visible" : "none");
    }
  }

  useEffect(() => {
    if (webglAvailable !== true) return;
    if (!containerRef.current) return;
    maplibregl.setWorkerUrl(`${window.location.origin}/maplibre/maplibre-gl-worker.mjs`); // ver scripts/copy-maplibre-worker.mjs
    const map = new maplibregl.Map({ container: containerRef.current, style: "https://tiles.openfreemap.org/styles/dark", center: INITIAL_CENTER, zoom: 10.7, minZoom: 9, maxZoom: 17, fadeDuration: 0, renderWorldCopies: false, maxTileCacheSize: 60, pixelRatio: Math.min(window.devicePixelRatio || 1, 2) });
    mapRef.current = map;
    const setMoving = (moving: boolean) => document.body.classList.toggle("is-map-moving", moving);
    map.on("movestart", () => setMoving(true));
    map.on("moveend", () => setMoving(false));

    map.on("load", () => {
      map.addSource("districts", { type: "geojson", data: { type: "FeatureCollection", features: [] }, promoteId: "district_key", tolerance: 0.5, buffer: 32 });
      map.addLayer({
        id: "district-fill",
        type: "fill",
        source: "districts",
        paint: {
          "fill-color": ["interpolate", ["linear"], ["coalesce", ["feature-state", "job_count"], 0], 0, "#080808", 1, "#171717", 3, "#303030", 8, "#555555", 15, "#878787", 30, "#c8c8c8"],
          "fill-opacity": ["case", ["boolean", ["feature-state", "selected"], false], 0.86, 0.62],
        },
      });
      map.addLayer({
        id: "district-outline",
        type: "line",
        source: "districts",
        paint: {
          "line-color": ["case", ["boolean", ["feature-state", "selected"], false], "#f4f4f4", "#737373"],
          "line-width": ["case", ["boolean", ["feature-state", "selected"], false], 3.2, 0.8],
          "line-opacity": ["case", ["boolean", ["feature-state", "selected"], false], 1, 0.62],
        },
      });
      map.addSource("district-counts", { type: "geojson", data: districtCountFeatures(jobsRef.current) });
      map.addLayer({
        id: "district-labels",
        type: "symbol",
        source: "district-counts",
        // Every counted district must remain discoverable; MapLibre's default
        // collision handling could silently hide labels such as La Victoria.
        minzoom: 10.5,
        layout: { "text-field": ["concat", ["get", "district"], " · ", ["to-string", ["get", "job_count"]]], "text-size": 10, "text-font": ["Noto Sans Regular"], "text-anchor": "center", "text-allow-overlap": true, "text-ignore-placement": true },
        paint: { "text-color": "#bdbdbd", "text-halo-color": "#050505", "text-halo-width": 1.2 },
      });
      loadDistrictGeoJson()
        .then((payload) => {
          const source = map.getSource("districts") as maplibregl.GeoJSONSource;
          source.setData(normalizeDistrictGeoJson(payload));
          districtsReadyRef.current = true;
          setModeVisibility(map, modeRef.current, Boolean(radarDistrictKeyRef.current));
          window.setTimeout(() => syncDistrictState(map, jobsRef.current, selectedDistrictRef.current), 150);
        })
        .catch(() => undefined);
      map.addSource("jobs", { type: "geojson", data: pointFeatures(jobsRef.current), cluster: true, clusterMaxZoom: 13, clusterRadius: 48 });
      map.addLayer({ id: "clusters", type: "circle", source: "jobs", filter: ["has", "point_count"], paint: { "circle-color": ["step", ["get", "point_count"], "#5d5d5d", 10, "#8c8c8c", 30, "#d7d7d7"], "circle-radius": ["step", ["get", "point_count"], 20, 10, 25, 30, 31], "circle-stroke-color": "#eeeeee", "circle-stroke-width": 1.5, "circle-opacity": 0.9 } });
      map.addLayer({ id: "cluster-count", type: "symbol", source: "jobs", filter: ["has", "point_count"], layout: { "text-field": "{point_count_abbreviated}", "text-size": 12 }, paint: { "text-color": "#ffffff" } });
      map.addLayer({ id: "job-points", type: "circle", source: "jobs", filter: ["!", ["has", "point_count"]], paint: { "circle-color": "#f0f0f0", "circle-radius": 6, "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.5, "circle-opacity": 0.95 } });
      map.addSource("radar-rings", { type: "geojson", data: radarFeatures(radarCenter, radarRadiusKm) });
      map.addLayer({ id: "radar-fill", type: "fill", source: "radar-rings", paint: { "fill-color": "#d5d5d5", "fill-opacity": ["case", ["boolean", ["get", "active"], false], 0.08, 0.008] } });
      map.addLayer({ id: "radar-lines", type: "line", source: "radar-rings", paint: { "line-color": ["case", ["boolean", ["get", "active"], false], "#ffffff", "#858585"], "line-width": ["case", ["boolean", ["get", "active"], false], 2.4, 1], "line-opacity": ["case", ["boolean", ["get", "active"], false], 0.98, 0.72], "line-dasharray": [2, 2] } });
      map.addSource("radar-labels", { type: "geojson", data: radarLabelFeatures(radarCenter, radarCounts, radarRadiusKm) });
      map.addLayer({ id: "radar-labels", type: "symbol", source: "radar-labels", layout: { "text-field": ["get", "label"], "text-size": 11, "text-font": ["Noto Sans Regular"], "text-anchor": "bottom", "text-offset": [0, -0.3], "text-allow-overlap": true, "text-ignore-placement": true }, paint: { "text-color": ["case", ["boolean", ["get", "active"], false], "#ffffff", "#9a9a9a"], "text-halo-color": "#050505", "text-halo-width": 1.4 } });
      setModeVisibility(map, mode, Boolean(radarDistrictKey));
      setMapReady(true);
      map.once("idle", () => setModeVisibility(map, modeRef.current, Boolean(radarDistrictKeyRef.current)));
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
      if (feature?.properties?.id) selectJobRef.current(String(feature.properties.id));
    });
    map.on("click", "district-fill", (event) => {
      if (modeRef.current === "radar" && pickCenterRef.current) return;
      const feature = map.queryRenderedFeatures(event.point, { layers: ["district-fill"] })[0];
      if (feature?.properties?.district_key) selectDistrictRef.current(String(feature.properties.district_key));
    });
    map.on("click", "district-labels", (event) => {
      if (modeRef.current === "radar" && pickCenterRef.current) return;
      const feature = map.queryRenderedFeatures(event.point, { layers: ["district-labels"] })[0];
      if (feature?.properties?.districtKey) selectDistrictRef.current(String(feature.properties.districtKey));
    });
    map.on("click", (event: MapMouseEvent) => {
      if (modeRef.current !== "radar" || !pickCenterRef.current) return;
      if (map.queryRenderedFeatures(event.point, { layers: ["clusters", "job-points"] }).length) return;
      pickCenterRef.current({ longitude: event.lngLat.lng, latitude: event.lngLat.lat });
    });
    for (const layer of ["clusters", "job-points", "district-fill", "district-labels"]) {
      map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
    }
    return () => {
      document.body.classList.remove("is-map-moving");
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
    setModeVisibility(map, modeRef.current, Boolean(radarDistrictKeyRef.current));
  }, [jobs]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const applyMode = () => {
      if (!map.isStyleLoaded()) return;
      setModeVisibility(map, mode, Boolean(radarDistrictKey));
    };
    const reapplyWhenIdle = () => applyMode();
    if (map.isStyleLoaded()) {
      applyMode();
      map.once("idle", reapplyWhenIdle);
    }
    else map.once("load", applyMode);
    return () => { map.off("load", applyMode); map.off("idle", reapplyWhenIdle); };
  }, [mode, radarDistrictKey]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    syncDistrictState(map, jobsRef.current, selectedDistrictKey);
    setModeVisibility(map, modeRef.current, Boolean(radarDistrictKeyRef.current));
    if (selectedDistrictKey) focusDistrict(map, selectedDistrictKey);
  }, [selectedDistrictKey]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const syncRadarState = () => {
      const source = map.getSource("radar-rings") as maplibregl.GeoJSONSource | undefined;
      if (!source) return;
      source.setData(radarFeatures(radarCenter, radarRadiusKm));
      (map.getSource("radar-labels") as maplibregl.GeoJSONSource | undefined)?.setData(radarLabelFeatures(radarCenter, radarCounts, radarRadiusKm));
      setModeVisibility(map, mode, Boolean(radarDistrictKey));
      map.triggerRepaint();
    };
    if (map.getSource("radar-rings")) {
      syncRadarState();
      map.once("idle", syncRadarState);
    } else {
      map.once("load", syncRadarState);
    }
    return () => {
      map.off("load", syncRadarState);
      map.off("idle", syncRadarState);
    };
  }, [mode, radarCenter, radarRadiusKm, radarDistrictKey, radarCounts, mapReady]);

  if (webglAvailable === false) return <LeafletMapView {...props} />;
  if (webglAvailable === null) return <div className="map-loading">Preparando mapa…</div>;
  return <div ref={containerRef} className="map-canvas" aria-label="Mapa de ofertas laborales de Lima" />;
}
