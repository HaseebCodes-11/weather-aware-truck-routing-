import type { HeatmapResponse, Place, PlanInput, PlanResponse } from "./types";

const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/** Turn DRF validation errors ({field: ["msg"]}) or {error} into one readable line. */
function messageFrom(body: unknown, status: number): string {
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    if (typeof b.error === "string") return b.error;
    const parts = Object.entries(b).map(([field, val]) => {
      const msg = Array.isArray(val) ? val.join(" ") : typeof val === "string" ? val : JSON.stringify(val);
      return field === "non_field_errors" ? msg : `${field.replace(/_/g, " ")}: ${msg}`;
    });
    if (parts.length) return parts.join(" · ");
  }
  return status >= 500 ? "The server had a problem. Please try again." : `Request failed (${status}).`;
}

async function request<T>(path: string, init?: RequestInit & { signal?: AbortSignal }): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("Can't reach the API. Check your connection or the server URL.", 0);
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(messageFrom(body, res.status), res.status);
  return body as T;
}

export function searchPlaces(q: string, signal?: AbortSignal): Promise<Place[]> {
  return request<{ results: Place[] }>(`/api/geocode/?q=${encodeURIComponent(q)}`, { signal }).then((r) => r.results);
}

export function planTrip(input: PlanInput, signal?: AbortSignal): Promise<PlanResponse> {
  return request<PlanResponse>("/api/plan/", { method: "POST", body: JSON.stringify(input), signal });
}

export function fetchHeatmap(
  points: [number, number][],
  start: string,
  loadLb: number,
  signal?: AbortSignal,
): Promise<HeatmapResponse> {
  return request<HeatmapResponse>("/api/heatmap/", {
    method: "POST",
    body: JSON.stringify({ points, start, hours: 48, load_lb: loadLb }),
    signal,
  });
}
