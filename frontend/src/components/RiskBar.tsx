import { RISK_LEVELS } from "../lib/risk";
import type { RouteRisk } from "../lib/types";

/** Stacked bar showing how many route miles fall in each risk level. */
export default function RiskBar({ risk, total }: { risk: RouteRisk; total: number }) {
  const parts = RISK_LEVELS.map((l) => ({ ...l, miles: risk.miles_by_level[l.key as keyof RouteRisk["miles_by_level"]] || 0 }));
  const sum = parts.reduce((a, p) => a + p.miles, 0) || total || 1;
  return (
    <div className="risk-bar" role="img" aria-label={parts.map((p) => `${p.name} ${Math.round(p.miles)} mi`).join(", ")}>
      {parts
        .filter((p) => p.miles > 0)
        .map((p) => (
          <span
            key={p.key}
            style={{ width: `${(p.miles / sum) * 100}%`, background: p.color }}
            title={`${p.name}: ${Math.round(p.miles)} mi`}
          />
        ))}
    </div>
  );
}
