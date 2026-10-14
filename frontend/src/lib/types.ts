export type Place = { label: string; lat: number; lon: number };

/** 0 Low · 1 Moderate · 2 High · 3 Severe · 4 No Travel */
export type RiskLevel = 0 | 1 | 2 | 3 | 4;

export type CheckpointWeather = {
  available: boolean;
  wind_mph: number;
  gust_mph: number | null;
  rain_in_hr: number;
  snow_in_hr: number;
  temp_f: number | null;
  weather_code: number | null;
};

export type CheckpointRisk = {
  level: RiskLevel;
  level_key: string;
  level_name: string;
  components: { wind: string; rain: string; snow: string };
  reasons: string[];
};

export type Checkpoint = {
  index: number;
  mile: number;
  lat: number;
  lon: number;
  eta: string;
  weather: CheckpointWeather | null;
  risk: CheckpointRisk | null;
};

export type RiskSegment = { from_mile: number; to_mile: number; level: RiskLevel };

export type RouteRisk = {
  miles_by_level: Record<"low" | "moderate" | "high" | "severe" | "no_travel", number>;
  avg_risk: number;
  max_level: RiskLevel;
  max_level_name: string;
  segments: RiskSegment[];
};

/** [lat, lon, cumulative mile] */
export type GeometryPoint = [number, number, number];

export type Route = {
  id: string;
  label: string;
  summary: string;
  source: string;
  distance_mi: number;
  duration_s: number;
  arrival: string;
  geometry: GeometryPoint[];
  checkpoints: Checkpoint[];
  risk: RouteRisk;
  rank: number;
  recommended: boolean;
};

export type DepartureAdvice = {
  suggested_departure: string;
  delay_hours: number;
  route_id: string;
  no_travel_miles: number;
  severe_miles: number;
  high_miles: number;
  message: string;
};

export type PlanResponse = {
  request: {
    origin: Place;
    destination: Place;
    departure: string;
    load_lb: number;
    interval_mi: number;
  };
  routes: Route[];
  recommended_route_id: string;
  recommendation_reason: string;
  departure_advice: DepartureAdvice | null;
  corridor: [number, number][];
  warnings: string[];
};

export type HeatmapResponse = {
  points: [number, number][];
  times: string[];
  intensity: number[][];
  levels: number[][];
};

export type PlaceValue = Place | string;

export type PlanInput = {
  origin: PlaceValue;
  destination: PlaceValue;
  departure: string; // ISO
  load_lb: number;
  interval_mi: 10 | 25 | 50;
};
