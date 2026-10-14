import type { Checkpoint, GeometryPoint } from "./types";

type LatLng = [number, number];

function interpolate(a: GeometryPoint, b: GeometryPoint, mile: number): LatLng {
  const span = b[2] - a[2];
  const t = span > 0 ? (mile - a[2]) / span : 0;
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

/** Position on the route at a given mile. */
export function pointAtMile(geometry: GeometryPoint[], mile: number): LatLng {
  if (!geometry.length) return [0, 0];
  if (mile <= 0) return [geometry[0][0], geometry[0][1]];
  for (let i = 1; i < geometry.length; i++) {
    if (geometry[i][2] >= mile) return interpolate(geometry[i - 1], geometry[i], mile);
  }
  const last = geometry[geometry.length - 1];
  return [last[0], last[1]];
}

/** The part of the route between two miles, with interpolated ends so colours meet cleanly. */
export function sliceByMiles(geometry: GeometryPoint[], from: number, to: number): LatLng[] {
  const out: LatLng[] = [pointAtMile(geometry, from)];
  for (const p of geometry) {
    if (p[2] > from && p[2] < to) out.push([p[0], p[1]]);
  }
  out.push(pointAtMile(geometry, to));
  return out;
}

/** Where the truck is at time `t` (ms), using checkpoint ETAs; null if not on the road. */
export function truckPosition(geometry: GeometryPoint[], checkpoints: Checkpoint[], t: number): LatLng | null {
  if (checkpoints.length < 2) return null;
  const times = checkpoints.map((c) => new Date(c.eta).getTime());
  if (t < times[0] || t > times[times.length - 1]) return null;
  for (let i = 1; i < times.length; i++) {
    if (t <= times[i]) {
      const span = times[i] - times[i - 1];
      const f = span > 0 ? (t - times[i - 1]) / span : 0;
      const mile = checkpoints[i - 1].mile + (checkpoints[i].mile - checkpoints[i - 1].mile) * f;
      return pointAtMile(geometry, mile);
    }
  }
  return null;
}
