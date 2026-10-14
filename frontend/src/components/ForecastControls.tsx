import { useEffect } from "react";
import { formatDateTime } from "../lib/format";
import { RISK_LEVELS } from "../lib/risk";

type Props = {
  times: string[];
  hourIndex: number;
  onHourChange: (i: number) => void;
  playing: boolean;
  onPlayingChange: (p: boolean) => void;
  showHeat: boolean;
  onShowHeatChange: (v: boolean) => void;
  opacity: number;
  onOpacityChange: (v: number) => void;
  loading: boolean;
  error: string | null;
  departure: string | null;
  arrival: string | null;
};

export default function ForecastControls(props: Props) {
  const { times, hourIndex, onHourChange, playing, onPlayingChange, loading, error } = props;
  const max = Math.max(0, times.length - 1);

  useEffect(() => {
    if (!playing || !times.length) return;
    const id = window.setInterval(() => onHourChange((hourIndex + 1) % times.length), 450);
    return () => window.clearInterval(id);
  }, [playing, hourIndex, times.length, onHourChange]);

  const current = times[hourIndex];
  const dep = props.departure ? new Date(props.departure).getTime() : null;
  const arr = props.arrival ? new Date(props.arrival).getTime() : null;
  const pct = (iso: number) => {
    if (!times.length) return 0;
    const t0 = new Date(times[0]).getTime();
    const t1 = new Date(times[max]).getTime();
    return Math.max(0, Math.min(100, ((iso - t0) / Math.max(1, t1 - t0)) * 100));
  };

  return (
    <div className="forecast" aria-label="Weather forecast controls">
      <div className="forecast__top">
        <div className="forecast__title">
          <strong>Weather risk forecast</strong>
          {loading ? (
            <span className="muted"><span className="spinner spinner--small" /> Loading 48 h forecast…</span>
          ) : error ? (
            <span className="forecast__error">{error}</span>
          ) : current ? (
            <span className="forecast__time">
              {formatDateTime(current)} <span className="muted">· +{hourIndex} h</span>
            </span>
          ) : null}
        </div>
        <div className="forecast__toggles">
          <label className="switch">
            <input type="checkbox" checked={props.showHeat} onChange={(e) => props.onShowHeatChange(e.target.checked)} />
            <span>Heatmap</span>
          </label>
          <input
            className="opacity"
            type="range"
            min={0.3}
            max={1}
            step={0.05}
            value={props.opacity}
            onChange={(e) => props.onOpacityChange(Number(e.target.value))}
            aria-label="Heatmap opacity"
            title="Heatmap opacity"
          />
        </div>
      </div>

      <div className="forecast__slider">
        <button
          type="button"
          className="play-btn"
          onClick={() => onPlayingChange(!playing)}
          disabled={!times.length}
          aria-label={playing ? "Pause" : "Play"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <div className="slider-track">
          {dep != null && arr != null && times.length > 0 && (
            <span
              className="trip-window"
              style={{ left: `${pct(dep)}%`, width: `${Math.max(1, pct(arr) - pct(dep))}%` }}
              title="Selected route is on the road during this window"
            />
          )}
          <input
            type="range"
            min={0}
            max={max}
            step={1}
            value={hourIndex}
            disabled={!times.length}
            onChange={(e) => {
              onPlayingChange(false);
              onHourChange(Number(e.target.value));
            }}
            aria-label="Forecast hour"
          />
          <div className="slider-ticks" aria-hidden>
            {[0, 12, 24, 36, 48].map((h) => (
              <span key={h}>+{h}h</span>
            ))}
          </div>
        </div>
      </div>

      <div className="legend" aria-label="Risk legend">
        {RISK_LEVELS.map((l) => (
          <span key={l.key}>
            <i style={{ background: l.color }} />
            {l.name}
          </span>
        ))}
        <span className="legend__hint muted">🚚 shows where the truck is at this hour</span>
      </div>
    </div>
  );
}
