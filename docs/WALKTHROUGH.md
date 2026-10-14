# Loom walkthrough script (about 7–8 minutes)

Rough talking points, not a script to read word for word. Speak naturally and show the screen.

## 1. Intro (30 s)

- "This is a weather-aware truck routing app built with React and Django."
- "The driver enters where they're going, when they leave and how heavy the load is, and it recommends the safest route using the forecast at the time the truck will actually be at each point."

## 2. Demo the app (2–3 min)

1. Click a sample trip (e.g. **Chicago → Denver**), set a departure and a load of **35,000 lb**, leave the interval on **25 mi**, then click **Find safest route**.
2. Point out the **recommendation card** and read the reason out loud.
3. Show the **three route cards**: drive time, distance, arrival, the coloured bar of miles per risk level, and the max risk chip.
4. On the map: the recommended route is **coloured by risk**, the alternatives are dashed. Click an alternative to select it.
5. Click a **checkpoint**: ETA, wind and gusts, rain, snow, temperature, and the reasons it got that level.
6. Click a row in the **checkpoint table** to fly to it.
7. **Heatmap:** drag the slider from +0 h to +48 h, then press play. Point out the shaded band that shows when the truck is on the road, and the 🚚 marker moving along the route.
8. Change the load to **45,000 lb** and plan again to show the load rules changing the result (if the forecast has some wind).

## 3. How it works (3 min) — show the code

- `backend/trips/core/risk.py` — the threshold tables and the three load rules. "Lower bounds are inclusive; the worst of wind, rain and snow wins."
- `backend/trips/core/checkpoints.py` — "Checkpoints every 10/25/50 miles. ETA = departure + time to reach that mile, interpolated along the route."
- `backend/trips/clients/osrm.py` — "OSRM often returns fewer than three alternatives, so I add detours through via-points and keep only routes that are meaningfully different and not much slower. Times are capped at 65 mph for a truck."
- `backend/trips/clients/weather.py` — "Open-Meteo, batched and parallel, units checked."
- `backend/trips/core/recommend.py` — "Each stretch takes the worse of its two ends. Ranking: No Travel miles, then Severe, then High, then average risk, then time, exactly as in the brief."
- `frontend/src/lib/raster.ts` — "For a smooth heatmap I precompute each pixel's nearest points once, render all 49 hourly frames up front, and the slider only swaps images."

## 4. Quality (1 min)

- Run `python manage.py test trips` and show the tests passing.
- "The core logic has no Django or network imports, so it's tested offline with fake routes and weather."
- "There's CI on GitHub, a Render blueprint for the API and Vercel for the frontend, with no API keys needed."

## 5. Trade-offs and what's next (30–60 s)

- Sustained wind drives the rules; gusts are shown but not scored.
- Free public routing and weather services are rate limited, so there's caching and retries. In production I'd self-host OSRM with a real truck profile (height, weight, hazmat) and add hours-of-service rest stops.
- "Thanks for watching."
