import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForecastControls from "./components/ForecastControls";
import MapView from "./components/MapView";
import RouteCard from "./components/RouteCard";
import RouteDetails from "./components/RouteDetails";
import TripForm from "./components/TripForm";
import { ApiError, fetchHeatmap, planTrip } from "./lib/api";
import { formatDateTime } from "./lib/format";
import { buildGrid, renderFrames, type Bounds } from "./lib/raster";
import type { Checkpoint, HeatmapResponse, PlanInput, PlanResponse } from "./lib/types";

type HeatFrames = { bounds: Bounds; frames: string[] };

export default function App() {
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focus, setFocus] = useState<Checkpoint | null>(null);

  const [heatData, setHeatData] = useState<HeatmapResponse | null>(null);
  const [heat, setHeat] = useState<HeatFrames | null>(null);
  const [heatLoading, setHeatLoading] = useState(false);
  const [heatError, setHeatError] = useState<string | null>(null);
  const [hourIndex, setHourIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [showHeat, setShowHeat] = useState(true);
  const [opacity, setOpacity] = useState(0.85);

  const abortRef = useRef<AbortController | null>(null);

  const handleSubmit = useCallback(async (input: PlanInput) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true);
    setError(null);
    setPlaying(false);
    setHeat(null);
    setHeatData(null);
    setHeatError(null);
    setFocus(null);
    let stage: "plan" | "heat" = "plan";
    try {
      const result = await planTrip(input, ctrl.signal);
      setPlan(result);
      setSelectedId(result.recommended_route_id);
      setHourIndex(0);
      setLoading(false);
      stage = "heat";

      // The heatmap is a second request so routes appear as soon as they're ready.
      setHeatLoading(true);
      const hm = await fetchHeatmap(result.corridor, result.request.departure, result.request.load_lb, ctrl.signal);
      setHeatData(hm);
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      const msg = err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
      if (stage === "plan") setError(msg);
      else setHeatError("Heatmap unavailable: " + msg);
    } finally {
      if (abortRef.current === ctrl) {
        setLoading(false);
        setHeatLoading(false);
      }
    }
  }, []);

  // Render all hourly heatmap frames once per forecast (off the click handler).
  useEffect(() => {
    if (!heatData) return;
    const id = window.setTimeout(() => {
      const grid = buildGrid(heatData.points);
      setHeat({ bounds: grid.bounds, frames: renderFrames(grid, heatData.intensity) });
    }, 0);
    return () => window.clearTimeout(id);
  }, [heatData]);

  const selected = useMemo(() => plan?.routes.find((r) => r.id === selectedId) ?? null, [plan, selectedId]);
  const orderedRoutes = useMemo(() => (plan ? [...plan.routes].sort((a, b) => a.rank - b.rank) : []), [plan]);
  const truckTime = heatData?.times[hourIndex] ? new Date(heatData.times[hourIndex]).getTime() : null;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand__logo" aria-hidden>🚚</span>
          <div>
            <h1>Weather-Aware Truck Routing</h1>
            <p>Pick the safest route using forecast weather at the time you'll actually be there.</p>
          </div>
        </div>
      </header>

      <main className="layout">
        <aside className="sidebar">
          <section className="card">
            <h2 className="card__title">Plan a trip</h2>
            <TripForm loading={loading} onSubmit={handleSubmit} />
          </section>

          {error && (
            <div className="alert alert--error" role="alert">
              <strong>Couldn't plan this trip.</strong> {error}
            </div>
          )}

          {plan && (
            <>
              <section className="card recommendation">
                <div className="recommendation__head">
                  <span className="eyebrow">Recommended</span>
                  <h2>Route {plan.recommended_route_id}</h2>
                </div>
                <p>{plan.recommendation_reason}</p>
                {plan.departure_advice && (
                  <div className="alert alert--advice">
                    <strong>Consider leaving later.</strong> {plan.departure_advice.message} Suggested departure:{" "}
                    {formatDateTime(plan.departure_advice.suggested_departure)}.
                  </div>
                )}
                {plan.warnings.map((w) => (
                  <div key={w} className="alert alert--warn">{w}</div>
                ))}
              </section>

              <section className="routes" aria-label="Route options">
                {orderedRoutes.map((r) => (
                  <RouteCard key={r.id} route={r} selected={r.id === selectedId} onSelect={() => setSelectedId(r.id)} />
                ))}
              </section>

              {selected && <RouteDetails route={selected} onFocusCheckpoint={setFocus} />}
            </>
          )}

          {!plan && !error && (
            <section className="card how">
              <h2 className="card__title">How it works</h2>
              <ol>
                <li>We fetch up to three route options for a truck.</li>
                <li>Weather is sampled every 10, 25 or 50 miles at the hour the truck reaches each point.</li>
                <li>Each checkpoint is rated Low → No Travel using wind, rain, snow and load rules.</li>
                <li>The best route has the fewest Severe miles, then High miles, then the lowest average risk, then the shortest time.</li>
              </ol>
            </section>
          )}
        </aside>

        <section className="map-area">
          <MapView
            plan={plan}
            selectedId={selectedId}
            onSelect={setSelectedId}
            heat={heat}
            hourIndex={hourIndex}
            showHeat={showHeat}
            heatOpacity={opacity}
            truckTime={truckTime}
            focus={focus}
          />
          {!plan && !loading && (
            <div className="map-empty">
              <strong>No trip yet</strong>
              <span>Enter an origin and destination to compare routes.</span>
            </div>
          )}
          {loading && (
            <div className="map-loading">
              <span className="spinner" /> Building routes and checking the forecast…
            </div>
          )}
          {plan && (
            <ForecastControls
              times={heatData?.times ?? []}
              hourIndex={hourIndex}
              onHourChange={setHourIndex}
              playing={playing}
              onPlayingChange={setPlaying}
              showHeat={showHeat}
              onShowHeatChange={setShowHeat}
              opacity={opacity}
              onOpacityChange={setOpacity}
              loading={heatLoading || (!!heatData && !heat)}
              error={heatError}
              departure={plan.request.departure}
              arrival={selected?.arrival ?? null}
            />
          )}
        </section>
      </main>
    </div>
  );
}
