import { formatDuration, formatMiles, formatTime } from "../lib/format";
import { RISK_LEVELS, ROUTE_COLORS, riskColor } from "../lib/risk";
import type { Route } from "../lib/types";
import RiskBar from "./RiskBar";

type Props = { route: Route; selected: boolean; onSelect: () => void };

export default function RouteCard({ route, selected, onSelect }: Props) {
  const m = route.risk.miles_by_level;
  const flagged = RISK_LEVELS.filter((l) => l.level >= 2 && m[l.key as keyof typeof m] > 0);

  return (
    <button
      type="button"
      className={`route-card ${selected ? "selected" : ""} ${route.recommended ? "recommended" : ""}`}
      onClick={onSelect}
      aria-pressed={selected}
    >
      <div className="route-card__head">
        <span className="route-swatch" style={{ background: ROUTE_COLORS[route.id] }} />
        <strong>{route.label}</strong>
        {route.recommended ? <span className="badge badge--best">Recommended</span> : <span className="rank">#{route.rank}</span>}
        <span className="risk-chip" style={{ background: riskColor(route.risk.max_level) }}>
          {route.risk.max_level_name}
        </span>
      </div>

      <div className="route-card__stats">
        <div>
          <span className="stat-value">{formatDuration(route.duration_s)}</span>
          <span className="stat-label">Drive time</span>
        </div>
        <div>
          <span className="stat-value">{formatMiles(route.distance_mi)}</span>
          <span className="stat-label">Distance</span>
        </div>
        <div>
          <span className="stat-value">{formatTime(route.arrival)}</span>
          <span className="stat-label">Arrival</span>
        </div>
      </div>

      <RiskBar risk={route.risk} total={route.distance_mi} />

      <div className="route-card__foot">
        {flagged.length ? (
          flagged.map((l) => (
            <span key={l.key} className="mini-stat">
              <i style={{ background: l.color }} />
              {Math.round(m[l.key as keyof typeof m])} mi {l.name}
            </span>
          ))
        ) : (
          <span className="mini-stat mini-stat--ok">No High or worse conditions</span>
        )}
        <span className="mini-stat muted">avg risk {route.risk.avg_risk.toFixed(2)}</span>
      </div>
      {route.summary && <p className="route-via">via {route.summary}</p>}
    </button>
  );
}
