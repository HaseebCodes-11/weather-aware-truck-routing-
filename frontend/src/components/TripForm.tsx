import { useState } from "react";
import { nextHour, toLocalInput } from "../lib/format";
import type { PlaceValue, PlanInput } from "../lib/types";
import PlaceInput from "./PlaceInput";

type Props = { loading: boolean; onSubmit: (input: PlanInput) => void };

const SAMPLES: { name: string; origin: PlaceValue; destination: PlaceValue }[] = [
  {
    name: "Chicago → Denver",
    origin: { label: "Chicago, Illinois, United States", lat: 41.8781, lon: -87.6298 },
    destination: { label: "Denver, Colorado, United States", lat: 39.7392, lon: -104.9903 },
  },
  {
    name: "Dallas → Atlanta",
    origin: { label: "Dallas, Texas, United States", lat: 32.7767, lon: -96.797 },
    destination: { label: "Atlanta, Georgia, United States", lat: 33.749, lon: -84.388 },
  },
  {
    name: "Seattle → Salt Lake City",
    origin: { label: "Seattle, Washington, United States", lat: 47.6062, lon: -122.3321 },
    destination: { label: "Salt Lake City, Utah, United States", lat: 40.7608, lon: -111.891 },
  },
];

export default function TripForm({ loading, onSubmit }: Props) {
  const [origin, setOrigin] = useState<PlaceValue>("");
  const [destination, setDestination] = useState<PlaceValue>("");
  const [departure, setDeparture] = useState(toLocalInput(nextHour()));
  const [load, setLoad] = useState("35000");
  const [interval, setCheckpointInterval] = useState<10 | 25 | 50>(25);
  const [error, setError] = useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const loadNum = Number(load.replace(/,/g, ""));
    const hasText = (v: PlaceValue) => (typeof v === "string" ? v.trim().length >= 2 : true);
    if (!hasText(origin) || !hasText(destination)) return setError("Enter both an origin and a destination.");
    if (!departure) return setError("Choose a departure date and time.");
    if (!Number.isFinite(loadNum) || loadNum <= 0 || loadNum > 200000)
      return setError("Load weight must be between 1 and 200,000 lb.");
    setError(null);
    onSubmit({
      origin,
      destination,
      departure: new Date(departure).toISOString(),
      load_lb: loadNum,
      interval_mi: interval,
    });
  };

  const swap = () => {
    setOrigin(destination);
    setDestination(origin);
  };

  return (
    <form className="trip-form" onSubmit={submit} noValidate>
      <div className="place-pair">
        <PlaceInput label="Origin" marker="origin" value={origin} onChange={setOrigin} placeholder="City or address" />
        <button type="button" className="swap-btn" onClick={swap} title="Swap origin and destination" aria-label="Swap">
          ⇅
        </button>
        <PlaceInput
          label="Destination"
          marker="destination"
          value={destination}
          onChange={setDestination}
          placeholder="City or address"
        />
      </div>

      <div className="form-row">
        <div className="field">
          <label htmlFor="departure">Departure</label>
          <input id="departure" type="datetime-local" value={departure} onChange={(e) => setDeparture(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="load">Load weight (lb)</label>
          <input
            id="load"
            inputMode="numeric"
            value={load}
            onChange={(e) => setLoad(e.target.value.replace(/[^\d,]/g, ""))}
            placeholder="35000"
          />
        </div>
      </div>

      <div className="field">
        <span className="field-label">Weather checkpoint every</span>
        <div className="segmented" role="radiogroup" aria-label="Checkpoint interval">
          {([10, 25, 50] as const).map((v) => (
            <button
              type="button"
              key={v}
              role="radio"
              aria-checked={interval === v}
              className={interval === v ? "active" : ""}
              onClick={() => setCheckpointInterval(v)}
            >
              {v} mi
            </button>
          ))}
        </div>
      </div>

      {error && <p className="form-error" role="alert">{error}</p>}

      <button className="primary-btn" type="submit" disabled={loading}>
        {loading ? (
          <>
            <span className="spinner" /> Checking routes and weather…
          </>
        ) : (
          "Find safest route"
        )}
      </button>

      <div className="samples">
        <span>Try:</span>
        {SAMPLES.map((s) => (
          <button
            key={s.name}
            type="button"
            className="link-btn"
            onClick={() => {
              setOrigin(s.origin);
              setDestination(s.destination);
            }}
          >
            {s.name}
          </button>
        ))}
      </div>
    </form>
  );
}
