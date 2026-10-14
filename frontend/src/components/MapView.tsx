import L from "leaflet";
import { Fragment, useEffect, useMemo, useRef } from "react";
import { CircleMarker, MapContainer, Marker, Pane, Polyline, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import { formatDateTime } from "../lib/format";
import { sliceByMiles, truckPosition } from "../lib/geometry";
import type { Bounds } from "../lib/raster";
import { ROUTE_COLORS, riskColor } from "../lib/risk";
import type { Checkpoint, PlanResponse, Route } from "../lib/types";

type Props = {
  plan: PlanResponse | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  heat: { bounds: Bounds; frames: string[] } | null;
  hourIndex: number;
  showHeat: boolean;
  heatOpacity: number;
  truckTime: number | null;
  focus: Checkpoint | null;
};

const pinIcon = (kind: "origin" | "destination") =>
  L.divIcon({
    className: "",
    html: `<div class="map-pin map-pin--${kind}"><span>${kind === "origin" ? "A" : "B"}</span></div>`,
    iconSize: [28, 36],
    iconAnchor: [14, 34],
  });

const truckIcon = L.divIcon({
  className: "",
  html: `<div class="truck-marker" title="Truck position at the selected forecast hour">🚚</div>`,
  iconSize: [34, 34],
  iconAnchor: [17, 17],
});

function FitToPlan({ plan }: { plan: PlanResponse | null }) {
  const map = useMap();
  useEffect(() => {
    if (!plan) return;
    const pts = plan.routes.flatMap((r) => r.geometry.map((p) => [p[0], p[1]] as [number, number]));
    if (pts.length) map.fitBounds(L.latLngBounds(pts), { padding: [40, 40], maxZoom: 9 });
  }, [plan, map]);
  return null;
}

function FlyToCheckpoint({ focus }: { focus: Checkpoint | null }) {
  const map = useMap();
  useEffect(() => {
    if (focus) map.flyTo([focus.lat, focus.lon], Math.max(map.getZoom(), 8), { duration: 0.6 });
  }, [focus, map]);
  return null;
}

/**
 * Weather heatmap as a single image overlay. All 49 hourly frames are
 * pre-rendered and preloaded, so moving the slider only swaps the image URL.
 */
function HeatOverlay({ heat, hourIndex, visible, opacity }: { heat: Props["heat"]; hourIndex: number; visible: boolean; opacity: number }) {
  const map = useMap();
  const layerRef = useRef<L.ImageOverlay | null>(null);

  useEffect(() => {
    if (!heat || !heat.frames.length) return;
    heat.frames.forEach((src) => {
      const img = new Image();
      img.src = src; // warm the browser cache so swaps don't flicker
    });
    const layer = L.imageOverlay(heat.frames[0], heat.bounds, {
      opacity,
      pane: "heat",
      className: "heat-image",
      interactive: false,
    });
    layerRef.current = layer;
    return () => {
      layer.remove();
      layerRef.current = null;
    };
  }, [heat]);

  useEffect(() => {
    const layer = layerRef.current;
    if (!layer) return;
    if (visible && !map.hasLayer(layer)) layer.addTo(map);
    if (!visible && map.hasLayer(layer)) layer.remove();
  }, [visible, map, heat]);

  useEffect(() => {
    if (layerRef.current && heat) layerRef.current.setUrl(heat.frames[Math.min(hourIndex, heat.frames.length - 1)]);
  }, [hourIndex, heat]);

  useEffect(() => {
    layerRef.current?.setOpacity(opacity);
  }, [opacity]);

  return null;
}

function CheckpointPopup({ c }: { c: Checkpoint }) {
  const w = c.weather;
  return (
    <div className="cp-popup">
      <div className="cp-popup__head">
        <strong>Mile {Math.round(c.mile)}</strong>
        <span className="risk-chip risk-chip--sm" style={{ background: riskColor(c.risk?.level ?? 0) }}>
          {c.risk?.level_name ?? "Low"}
        </span>
      </div>
      <div className="cp-popup__eta">ETA {formatDateTime(c.eta)}</div>
      {w?.available ? (
        <dl>
          <dt>Wind</dt>
          <dd>
            {w.wind_mph.toFixed(0)} mph{w.gust_mph != null ? ` (gusts ${w.gust_mph.toFixed(0)})` : ""}
          </dd>
          <dt>Rain</dt>
          <dd>{w.rain_in_hr.toFixed(2)} in/hr</dd>
          <dt>Snow</dt>
          <dd>{w.snow_in_hr.toFixed(2)} in/hr</dd>
          {w.temp_f != null && (
            <>
              <dt>Temp</dt>
              <dd>{w.temp_f.toFixed(0)}°F</dd>
            </>
          )}
        </dl>
      ) : (
        <p className="muted">No forecast for this time.</p>
      )}
      {!!c.risk?.reasons.length && (
        <ul className="cp-popup__reasons">
          {c.risk.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SelectedRoute({ route }: { route: Route }) {
  const segments = useMemo(
    () =>
      route.risk.segments.map((s, i) => ({
        key: i,
        level: s.level,
        positions: sliceByMiles(route.geometry, s.from_mile, s.to_mile),
      })),
    [route],
  );
  const full = useMemo(() => route.geometry.map((p) => [p[0], p[1]] as [number, number]), [route]);
  return (
    <>
      <Polyline positions={full} pathOptions={{ color: "#ffffff", weight: 11, opacity: 0.95 }} interactive={false} />
      <Polyline positions={full} pathOptions={{ color: ROUTE_COLORS[route.id], weight: 9, opacity: 0.35 }} interactive={false} />
      {segments.map((s) => (
        <Polyline key={s.key} positions={s.positions} pathOptions={{ color: riskColor(s.level), weight: 6, opacity: 1 }} />
      ))}
      {route.checkpoints.map((c) => (
        <CircleMarker
          key={c.index}
          center={[c.lat, c.lon]}
          radius={c.risk && c.risk.level >= 2 ? 7 : 5}
          pathOptions={{ color: "#fff", weight: 2, fillColor: riskColor(c.risk?.level ?? 0), fillOpacity: 1 }}
        >
          <Popup>
            <CheckpointPopup c={c} />
          </Popup>
        </CircleMarker>
      ))}
    </>
  );
}

export default function MapView({ plan, selectedId, onSelect, heat, hourIndex, showHeat, heatOpacity, truckTime, focus }: Props) {
  const selected = plan?.routes.find((r) => r.id === selectedId) ?? null;
  const truck = selected && truckTime != null ? truckPosition(selected.geometry, selected.checkpoints, truckTime) : null;

  return (
    <MapContainer center={[39.5, -98.35]} zoom={4} className="map" zoomControl preferCanvas={false} worldCopyJump>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        subdomains="abcd"
        maxZoom={19}
      />
      <Pane name="heat" style={{ zIndex: 350 }} />
      <HeatOverlay heat={heat} hourIndex={hourIndex} visible={showHeat} opacity={heatOpacity} />
      <FitToPlan plan={plan} />
      <FlyToCheckpoint focus={focus} />

      {plan?.routes
        .filter((r) => r.id !== selectedId)
        .map((r) => (
          <Fragment key={r.id}>
            {/* Wide invisible line makes thin alternatives easy to click. */}
            <Polyline
              positions={r.geometry.map((p) => [p[0], p[1]] as [number, number])}
              pathOptions={{ color: "#000", weight: 16, opacity: 0 }}
              eventHandlers={{ click: () => onSelect(r.id) }}
            >
              <Tooltip sticky>
                {r.label} · click to inspect
              </Tooltip>
            </Polyline>
            <Polyline
              positions={r.geometry.map((p) => [p[0], p[1]] as [number, number])}
              pathOptions={{ color: ROUTE_COLORS[r.id], weight: 4, opacity: 0.7, dashArray: "8 7" }}
              interactive={false}
            />
          </Fragment>
        ))}

      {selected && <SelectedRoute route={selected} />}

      {plan && (
        <>
          <Marker position={[plan.request.origin.lat, plan.request.origin.lon]} icon={pinIcon("origin")}>
            <Tooltip direction="top" offset={[0, -30]}>{plan.request.origin.label}</Tooltip>
          </Marker>
          <Marker position={[plan.request.destination.lat, plan.request.destination.lon]} icon={pinIcon("destination")}>
            <Tooltip direction="top" offset={[0, -30]}>{plan.request.destination.label}</Tooltip>
          </Marker>
        </>
      )}

      {truck && <Marker position={truck} icon={truckIcon} interactive={false} zIndexOffset={1000} />}
    </MapContainer>
  );
}
