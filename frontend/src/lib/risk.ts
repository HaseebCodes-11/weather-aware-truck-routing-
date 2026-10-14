import type { RiskLevel } from "./types";

export const RISK_LEVELS: { level: RiskLevel; key: string; name: string; color: string }[] = [
  { level: 0, key: "low", name: "Low", color: "#2f9e62" },
  { level: 1, key: "moderate", name: "Moderate", color: "#e0b100" },
  { level: 2, key: "high", name: "High", color: "#f0812a" },
  { level: 3, key: "severe", name: "Severe", color: "#d93838" },
  { level: 4, key: "no_travel", name: "No Travel", color: "#7a2390" },
];

export const riskColor = (level: number) => RISK_LEVELS[Math.max(0, Math.min(4, level))].color;
export const riskName = (level: number) => RISK_LEVELS[Math.max(0, Math.min(4, level))].name;

/** Distinct, colour-blind-friendly hues for the three route options. */
export const ROUTE_COLORS: Record<string, string> = { A: "#2563eb", B: "#0f9d9a", C: "#9333ea" };

/** Heatmap colour stops; intensity = (level + position inside band) / 4. */
export const HEAT_STOPS: [number, [number, number, number]][] = [
  [0.0, [47, 158, 98]],
  [0.25, [224, 177, 0]],
  [0.5, [240, 129, 42]],
  [0.75, [217, 56, 56]],
  [1.0, [122, 35, 144]],
];

export function heatColor(v: number): [number, number, number] {
  const x = Math.max(0, Math.min(1, v));
  for (let i = 1; i < HEAT_STOPS.length; i++) {
    const [p1, c1] = HEAT_STOPS[i];
    const [p0, c0] = HEAT_STOPS[i - 1];
    if (x <= p1) {
      const t = (x - p0) / (p1 - p0);
      return [0, 1, 2].map((k) => Math.round(c0[k] + (c1[k] - c0[k]) * t)) as [number, number, number];
    }
  }
  return HEAT_STOPS[HEAT_STOPS.length - 1][1];
}
