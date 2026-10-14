import { formatDateTime, formatTime } from "../lib/format";
import { riskColor } from "../lib/risk";
import type { Checkpoint, Route } from "../lib/types";

type Props = { route: Route; onFocusCheckpoint: (c: Checkpoint) => void };

export default function RouteDetails({ route, onFocusCheckpoint }: Props) {
  return (
    <section className="details" aria-label={`${route.label} checkpoints`}>
      <header className="details__head">
        <h3>{route.label} · weather checkpoints</h3>
        <span className="muted">{route.checkpoints.length} points · arrives {formatDateTime(route.arrival)}</span>
      </header>
      <div className="table-wrap">
        <table className="cp-table">
          <thead>
            <tr>
              <th>Mile</th>
              <th>ETA</th>
              <th>Wind</th>
              <th>Rain</th>
              <th>Snow</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((c) => {
              const w = c.weather;
              const level = c.risk?.level ?? 0;
              return (
                <tr
                  key={c.index}
                  onClick={() => onFocusCheckpoint(c)}
                  title={c.risk?.reasons.join("\n") || "Clear conditions"}
                  className={level >= 3 ? "row-alert" : ""}
                >
                  <td>{Math.round(c.mile)}</td>
                  <td>{formatTime(c.eta)}</td>
                  <td>
                    {w?.available ? `${Math.round(w.wind_mph)}` : "–"}
                    {w?.available && w.gust_mph != null && <span className="muted"> g{Math.round(w.gust_mph)}</span>}
                  </td>
                  <td>{w?.available ? w.rain_in_hr.toFixed(2) : "–"}</td>
                  <td>{w?.available ? w.snow_in_hr.toFixed(2) : "–"}</td>
                  <td>
                    <span className="risk-chip risk-chip--sm" style={{ background: riskColor(level) }}>
                      {c.risk?.level_name ?? "Low"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="table-note muted">Wind mph (g = gusts) · rain and snow in inches per hour at the truck's ETA.</p>
    </section>
  );
}
