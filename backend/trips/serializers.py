from datetime import datetime, timedelta, timezone

from rest_framework import serializers

from .core.checkpoints import ALLOWED_INTERVALS_MI

MAX_DEPARTURE_DAYS_AHEAD = 14


class PlaceField(serializers.Field):
    """Either a free-text query or an already-geocoded {"label", "lat", "lon"} object."""

    def to_internal_value(self, data):
        if isinstance(data, str):
            if len(data.strip()) < 2:
                raise serializers.ValidationError("Enter a location.")
            return {"query": data.strip()}
        if isinstance(data, dict):
            try:
                lat, lon = float(data["lat"]), float(data["lon"])
            except (KeyError, TypeError, ValueError):
                raise serializers.ValidationError("Location needs numeric lat and lon.")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise serializers.ValidationError("Coordinates out of range.")
            return {"label": str(data.get("label") or f"{lat:.4f}, {lon:.4f}"), "lat": lat, "lon": lon}
        raise serializers.ValidationError("Invalid location.")

    def to_representation(self, value):
        return value


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceField()
    destination = PlaceField()
    departure = serializers.DateTimeField()
    load_lb = serializers.FloatField(min_value=1, max_value=200_000)
    interval_mi = serializers.ChoiceField(choices=ALLOWED_INTERVALS_MI, default=25)

    def validate_departure(self, value):
        value = _aware(value)
        now = datetime.now(timezone.utc)
        if value < now - timedelta(hours=1):
            raise serializers.ValidationError("Departure can't be in the past.")
        if value > now + timedelta(days=MAX_DEPARTURE_DAYS_AHEAD):
            raise serializers.ValidationError(f"Forecasts only cover the next {MAX_DEPARTURE_DAYS_AHEAD} days.")
        return value


class HeatmapRequestSerializer(serializers.Serializer):
    points = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2),
        min_length=1,
        max_length=400,
    )
    start = serializers.DateTimeField()
    hours = serializers.IntegerField(min_value=1, max_value=48, default=48)
    load_lb = serializers.FloatField(min_value=1, max_value=200_000)

    def validate_start(self, value):
        return _aware(value)
