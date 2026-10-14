"""Place search via Photon (OpenStreetMap data, no API key), Nominatim as fallback."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .http import UpstreamError, get_json

PHOTON_URL = os.getenv("PHOTON_URL", "https://photon.komoot.io/api/")
NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")

_COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


@dataclass
class Place:
    label: str
    lat: float
    lon: float

    def to_dict(self) -> dict:
        return {"label": self.label, "lat": self.lat, "lon": self.lon}


def parse_coordinates(text: str) -> Place | None:
    """Accept raw "lat, lon" input so the app works even if search is down."""
    m = _COORD_RE.match(text or "")
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return Place(f"{lat:.4f}, {lon:.4f}", lat, lon)
    return None


def _photon_label(props: dict) -> str:
    parts = [props.get("name"), props.get("city"), props.get("state"), props.get("country")]
    seen, out = set(), []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return ", ".join(out)


def search(query: str, limit: int = 5) -> list[Place]:
    query = (query or "").strip()
    if len(query) < 2:
        return []
    coords = parse_coordinates(query)
    if coords:
        return [coords]
    try:
        data = get_json("geocoding", PHOTON_URL, {"q": query, "limit": limit, "lang": "en"})
        places = []
        for f in data.get("features", []):
            lon, lat = f["geometry"]["coordinates"][:2]
            places.append(Place(_photon_label(f.get("properties", {})), float(lat), float(lon)))
        if places:
            return places
    except (UpstreamError, KeyError, TypeError, ValueError):
        pass
    data = get_json("geocoding", NOMINATIM_URL, {"q": query, "format": "jsonv2", "limit": limit})
    return [Place(d.get("display_name", query), float(d["lat"]), float(d["lon"])) for d in data]


def resolve(query: str) -> Place:
    results = search(query, limit=1)
    if not results:
        raise UpstreamError("geocoding", f'could not find "{query}"', 404)
    return results[0]
