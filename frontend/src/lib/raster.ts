import { heatColor } from "./risk";

/**
 * Weather heatmap rendering.
 *
 * The API returns a risk intensity (0..1) for a few hundred points along the
 * trip corridor, for every hour 0–48. We turn that into one small image per
 * hour using inverse-distance weighting:
 *
 *  1. Once: for every pixel, find its nearest K sample points and their weights.
 *     Pixels in Web Mercator rows so the image lines up with the map.
 *  2. Per hour: each pixel = weighted sum of K intensities -> colour.
 *
 * Step 1 is the expensive part and only runs when the corridor changes. Step 2
 * is ~K multiplications per pixel, so all 49 frames are ready almost instantly
 * and the slider just swaps pre-rendered images — no work while dragging.
 */

export type Bounds = [[number, number], [number, number]]; // [[south, west], [north, east]]

export type RasterGrid = {
  width: number;
  height: number;
  bounds: Bounds;
  k: number;
  neighbors: Int32Array; // pixel * k -> point index (-1 = none)
  weights: Float32Array; // pixel * k -> normalised weight
  mask: Float32Array; // pixel -> 0..1 opacity factor (fades out away from the corridor)
};

const K = 4;
const MAX_DISTANCE_MI = 32;
const FADE_MI = 10;
const PAD_DEG = 0.45;

const mercY = (lat: number) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
const invMercY = (y: number) => (Math.atan(Math.exp(y)) * 360) / Math.PI - 90;

export function buildGrid(points: [number, number][], maxWidth = 260): RasterGrid {
  let s = 90, n = -90, w = 180, e = -180;
  for (const [lat, lon] of points) {
    s = Math.min(s, lat); n = Math.max(n, lat);
    w = Math.min(w, lon); e = Math.max(e, lon);
  }
  s -= PAD_DEG; n += PAD_DEG; w -= PAD_DEG; e += PAD_DEG;

  const yS = mercY(s), yN = mercY(n);
  const xSpan = ((e - w) * Math.PI) / 180;
  const width = maxWidth;
  const height = Math.max(60, Math.min(400, Math.round((width * (yN - yS)) / xSpan)));

  const P = width * height;
  const neighbors = new Int32Array(P * K).fill(-1);
  const weights = new Float32Array(P * K);
  const mask = new Float32Array(P);

  const bestD = new Float64Array(K);
  const bestI = new Int32Array(K);

  for (let py = 0; py < height; py++) {
    const lat = invMercY(yN - ((py + 0.5) / height) * (yN - yS));
    const cosLat = Math.cos((lat * Math.PI) / 180);
    for (let px = 0; px < width; px++) {
      const lon = w + ((px + 0.5) / width) * (e - w);
      bestD.fill(Infinity);
      bestI.fill(-1);
      for (let i = 0; i < points.length; i++) {
        const dy = (lat - points[i][0]) * 69.0;
        const dx = (lon - points[i][1]) * 69.17 * cosLat;
        const d = dx * dx + dy * dy;
        if (d < bestD[K - 1]) {
          let j = K - 1;
          while (j > 0 && bestD[j - 1] > d) {
            bestD[j] = bestD[j - 1];
            bestI[j] = bestI[j - 1];
            j--;
          }
          bestD[j] = d;
          bestI[j] = i;
        }
      }
      const pix = py * width + px;
      const nearest = Math.sqrt(bestD[0]);
      if (!(nearest < MAX_DISTANCE_MI)) continue;
      mask[pix] = Math.min(1, (MAX_DISTANCE_MI - nearest) / FADE_MI);
      let total = 0;
      for (let j = 0; j < K; j++) {
        if (bestI[j] < 0) continue;
        const wgt = 1 / Math.max(1, bestD[j]); // 1/d², clamped so a sample point doesn't dominate
        weights[pix * K + j] = wgt;
        neighbors[pix * K + j] = bestI[j];
        total += wgt;
      }
      for (let j = 0; j < K; j++) weights[pix * K + j] /= total || 1;
    }
  }
  return { width, height, bounds: [[s, w], [n, e]], k: K, neighbors, weights, mask };
}

// 256-entry colour lookup so the per-pixel loop does no allocation.
const LUT = (() => {
  const t = new Uint8Array(256 * 3);
  for (let i = 0; i < 256; i++) t.set(heatColor(i / 255), i * 3);
  return t;
})();

/** RGBA pixels for one hour of intensities. Pure, so it can be tested without a browser. */
export function renderPixels(grid: RasterGrid, intensity: number[]): Uint8ClampedArray {
  const { width, height, k, neighbors, weights, mask } = grid;
  const out = new Uint8ClampedArray(width * height * 4);
  for (let pix = 0; pix < width * height; pix++) {
    const m = mask[pix];
    if (m <= 0) continue;
    let v = 0;
    for (let j = 0; j < k; j++) {
      const idx = neighbors[pix * k + j];
      if (idx >= 0) v += weights[pix * k + j] * (intensity[idx] ?? 0);
    }
    const c = Math.max(0, Math.min(255, Math.round(v * 255))) * 3;
    const o = pix * 4;
    out[o] = LUT[c];
    out[o + 1] = LUT[c + 1];
    out[o + 2] = LUT[c + 2];
    // Calm weather is a faint wash; risky weather is strong.
    out[o + 3] = Math.round(255 * m * (0.16 + 0.62 * Math.min(1, v * 1.3)));
  }
  return out;
}

/** Encode every hour to a PNG data URL (browser only). */
export function renderFrames(grid: RasterGrid, intensityByHour: number[][]): string[] {
  const canvas = document.createElement("canvas");
  canvas.width = grid.width;
  canvas.height = grid.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return [];
  return intensityByHour.map((row) => {
    const img = ctx.createImageData(grid.width, grid.height);
    img.data.set(renderPixels(grid, row));
    ctx.putImageData(img, 0, 0);
    return canvas.toDataURL("image/png");
  });
}
