# Weather-Aware Truck Routing

A React + Django web app that helps a truck driver pick the safest route between two places, based on the **forecast weather at the time the truck will actually be at each point**, the **load weight**, and **travel time**.

- **Live app:** _add your Vercel URL here_
- **API:** _add your Render URL here_ (`/api/health/`)
- **Walkthrough:** _add your Loom link here_

---

## What it does

1. The driver enters an origin, a destination, a departure date/time and the load weight.
2. The API fetches **three route options** for the trip.
3. Each route gets a **weather checkpoint every 10, 25 or 50 miles** (user's choice). For each checkpoint we work out the truck's **ETA** and look up the forecast **for that hour**, not for "now".
4. Every checkpoint is rated **Low / Moderate / High / Severe / No Travel** using the wind, rain and snow thresholds plus the load rules from the brief.
5. Routes are ranked and the app **recommends one**, with a plain-English reason ("Route A is 12 min faster but has 48 Severe miles").
6. The map shows all routes, the recommended route coloured by risk, every checkpoint (click for wind / rain / snow / ETA / reasons) and a **weather-risk heatmap over the trip corridor with a 0–48 h forecast slider**. A truck icon shows where the truck would be at the selected hour.

Extras that fall out of the same data:

- **Departure advice:** if the best route still has Severe or No Travel miles, the API checks the next 48 hours and suggests a later departure that avoids them.
- **Clear warnings** when every route is No Travel, when a checkpoint is beyond the forecast window, or when fewer than three distinct routes exist.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React 18, TypeScript, Vite, Leaflet / react-leaflet | Fast build, typed data contracts, lightweight map |
| Backend | Django 5 + Django REST Framework | Required by the brief; DRF gives validation and clean errors |
| Routing | [OSRM](https://project-osrm.org/) (public server, configurable) | Free, no API key, supports alternatives and per-segment timings |
| Weather | [Open-Meteo](https://open-meteo.com/) hourly forecast | Free, no API key, 16-day hourly forecast, many locations per request |
| Geocoding | [Photon](https://photon.komoot.io/) with Nominatim fallback | Free OpenStreetMap search with autocomplete |
| Hosting | Render (API) + Vercel (frontend) | Free tiers, config included |

No API keys are needed anywhere, so a reviewer can clone and run it immediately.

## Architecture

```
React (Vite)                                 Django API
┌──────────────────────┐   POST /api/plan/   ┌───────────────────────────────────────────┐
│ TripForm             │ ──────────────────▶ │ serializers.py   validate input            │
│ RouteCards / Details │                     │ planner.plan_trip                          │
│ MapView (Leaflet)    │ ◀────────────────── │   osrm.get_routes ─▶ 3 distinct routes     │
│ ForecastControls     │   routes + corridor │   checkpoints.place_checkpoints (+ ETAs)   │
│ raster.ts (heatmap)  │                     │   weather.forecast_hourly (batched)        │
│                      │  POST /api/heatmap/ │   risk.assess  ─▶ level per checkpoint     │
│                      │ ──────────────────▶ │   recommend.summarize / ranking_key        │
│                      │ ◀── 49 h × N grid   │ planner.build_heatmap                      │
└──────────────────────┘                     └───────────────────────────────────────────┘
```

The core logic (`backend/trips/core/`) is plain Python with no Django or network imports. External services are passed in as functions, so the whole pipeline is tested offline with fakes.

```
backend/
  config/                Django settings, urls, wsgi
  trips/
    core/
      risk.py            thresholds, load rules, heat intensity        (pure)
      geo.py             haversine, polyline, interpolation, overlap   (pure)
      checkpoints.py     checkpoint placement and ETAs                 (pure)
      recommend.py       miles per level, ranking, explanation         (pure)
      planner.py         pipeline + departure advice + heatmap grid
    clients/             OSRM, Open-Meteo, Photon/Nominatim, HTTP cache/retry
    serializers.py, views.py, urls.py
    tests/               unit tests + API tests with mocked services
frontend/
  src/
    components/          TripForm, PlaceInput, RouteCard, RouteDetails, MapView, ForecastControls
    lib/                 api client, types, risk colours, geometry, heatmap raster
```

## How the logic works

### 1. Three route options

OSRM is asked for alternatives first. It often returns only one or two, so the API also requests **detour candidates through via-points** offset 15% and 30% of the trip length to either side of the straight line. A candidate is kept only if:

- it is not more than 60% slower than the fastest route, and
- it differs from every chosen route on at least 20% of its length (sampled overlap check).

**Truck timing:** OSRM's driving profile is for cars, so every segment's time is capped at **65 mph** (`TRUCK_MAX_SPEED_MPH`). This only ever makes times longer, never shorter.

### 2. Checkpoints and ETAs

Checkpoints are placed at mile 0, every 10 / 25 / 50 miles, and at the destination (a tiny final stretch is merged into the previous one). For each checkpoint, the position and elapsed time are **interpolated along the route geometry** using per-segment travel times, so:

```
ETA(checkpoint) = departure + time to reach that mile
```

Nearby checkpoints from different routes share one forecast lookup (~1 km grid), and all locations go to Open-Meteo in batched, parallel requests.

### 3. Weather → risk

Weather is the forecast **hour nearest the ETA**: sustained wind (mph), rain (in/hr) and snowfall (in/hr). Units are requested as mph and inches, and the returned units are still checked and converted, so the thresholds can't silently break.

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | < 25 | 25–34 | 35–44 | 45–54 | ≥ 55 |
| Rain (in/hr) | < 0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow (in/hr) | < 0.5 | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

Lower bounds are inclusive (25 mph is Moderate; 0.25 in/hr is High; exactly 1.00 in/hr rain is still Severe).

Load rules (applied to wind):

- wind ≥ 55 mph → **No Travel** for any load
- 45–54 mph and load **> 30,000 lb** → **No Travel**
- 35–44 mph and load **> 40,000 lb** → **Severe**

A checkpoint's level is the **worst** of wind (after load rules), rain and snow, and the API returns human-readable reasons for it.

### 4. Route risk and recommendation

Each stretch between two checkpoints takes the **worse level of its two ends**. This is deliberately conservative: if conditions are bad at either end, the driver should treat the whole stretch as bad. From this we get miles per level and a distance-weighted average risk (0–4).

Routes are ranked lexicographically, exactly as the brief asks:

1. Fewest **No Travel** miles (a route the rules forbid can't be "best")
2. Fewest **Severe** miles
3. Fewest **High** miles
4. Lowest **average risk**
5. Shortest **travel time**

Miles are rounded to 0.1 and average risk to 0.01 so tiny floating-point differences can't decide a tie that should go to travel time.

### 5. Heatmap and 48 h slider

The plan response includes a **corridor**: points along every route plus points 25 miles to either side. The frontend requests a risk intensity (0–1, same colour scale as the levels) for each point and each hour from departure to +48 h.

To keep the slider smooth:

- The browser computes, **once**, each pixel's nearest 4 corridor points and their inverse-distance weights (rows are spaced in Web Mercator so the image lines up with the map).
- It then renders **all 49 hourly frames up front** (the pixel maths for all 49 takes about 50 ms) and preloads them.
- Moving the slider or pressing play only **swaps a pre-rendered image**, so there's no computation while dragging.

## API

| Method | Path | Body / params | Returns |
|---|---|---|---|
| GET | `/api/health/` | – | `{ "status": "ok" }` |
| GET | `/api/geocode/?q=Denver` | – | `{ results: [{ label, lat, lon }] }` |
| POST | `/api/plan/` | `{ origin, destination, departure, load_lb, interval_mi }` | routes, checkpoints, risk, recommendation, departure advice, corridor, warnings |
| POST | `/api/heatmap/` | `{ points, start, hours (≤48), load_lb }` | `{ points, times, intensity[h][p], levels[h][p] }` |

`origin` / `destination` can be `{ "label", "lat", "lon" }` (from autocomplete) or a plain string, which the API geocodes. `interval_mi` must be 10, 25 or 50. Errors from external services come back as `{ "error", "service" }` with a 502 (or 404 / 422 when the input is the problem).

## Running locally

**Backend** (Python 3.11+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py test trips      # all tests, external services mocked
python manage.py runserver       # http://localhost:8000
```

**Frontend** (Node 18+):

```bash
cd frontend
cp .env.example .env             # VITE_API_URL=http://localhost:8000
npm install
npm run dev                      # http://localhost:5173
```

## Deployment

**API on Render**

1. Push the repo to GitHub.
2. In Render: **New → Blueprint**, pick the repo. `render.yaml` creates the service from `backend/`.
3. Set `CORS_ALLOWED_ORIGINS` to your Vercel URL (e.g. `https://truck-routing.vercel.app`).
4. Check `https://<your-api>.onrender.com/api/health/`.

**Frontend on Vercel**

1. **New Project** → import the repo → set **Root Directory** to `frontend`.
2. Framework: Vite (auto-detected). Add env var `VITE_API_URL=https://<your-api>.onrender.com`.
3. Deploy, then put the final URL back into `CORS_ALLOWED_ORIGINS` on Render.

> The free Render tier sleeps when idle, so the first request after a while can take ~30–50 s.

## Assumptions and trade-offs

- **Weather at the hour nearest the ETA**, using sustained wind for the wind thresholds. Gusts are shown for context but don't change the level (the brief gives one wind threshold; gusts would make every route look worse).
- **Segment level = worse of its two checkpoints** (conservative). A 10-mile interval gives the most precise picture; 50 miles is faster and coarser.
- **Truck speed** is OSRM's car timing capped at 65 mph. Rest breaks and hours-of-service rules are out of scope.
- **Missing forecast** (beyond about 15 days) is treated as Low and flagged in the response and the UI, rather than failing the whole plan.
- **Public free services** are rate limited. Responses are cached for 15 minutes and transient failures are retried. For production you'd self-host OSRM with a truck profile (heights, weights, hazmat).

## Tests

`backend/trips/tests/` covers:

- every threshold boundary for wind, rain and snow
- all three load rules, including the "over 30,000 / 40,000 lb" edges
- checkpoint spacing and ETAs for 10 / 25 / 50 mile intervals
- segment miles and the full ranking order (Severe beats speed, time breaks ties)
- end-to-end planning with fake routes and weather: storms moving the recommendation, heavy loads turning Severe into No Travel, departure advice when a storm passes, and checkpoints reading the forecast at their own ETA
- API validation and clean upstream error handling

CI (`.github/workflows/ci.yml`) runs the backend tests and the frontend build on every push.
