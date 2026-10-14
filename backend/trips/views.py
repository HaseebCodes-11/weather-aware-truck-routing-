import logging

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .clients import geocoding, osrm, weather
from .clients.http import UpstreamError
from .core.planner import TripRequest, build_heatmap, plan_trip
from .serializers import HeatmapRequestSerializer, PlanRequestSerializer

log = logging.getLogger(__name__)


def _upstream_error(exc: UpstreamError) -> Response:
    log.warning("upstream failure: %s", exc)
    code = exc.status if exc.status in (404, 422) else status.HTTP_502_BAD_GATEWAY
    friendly = {
        "routing": "The routing service couldn't build a route",
        "weather": "The weather service is unavailable",
        "geocoding": "The location search failed",
    }.get(exc.service, "An external service failed")
    return Response({"error": f"{friendly}: {exc.args[0].split(': ', 1)[-1]}", "service": exc.service}, status=code)


@api_view(["GET"])
def health(_request):
    return Response({"status": "ok"})


@api_view(["GET"])
def geocode(request):
    try:
        places = geocoding.search(request.query_params.get("q", ""), limit=6)
    except UpstreamError as exc:
        return _upstream_error(exc)
    return Response({"results": [p.to_dict() for p in places]})


@api_view(["POST"])
def plan(request):
    s = PlanRequestSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    data = s.validated_data
    try:
        origin = data["origin"] if "lat" in data["origin"] else geocoding.resolve(data["origin"]["query"]).to_dict()
        destination = (
            data["destination"] if "lat" in data["destination"] else geocoding.resolve(data["destination"]["query"]).to_dict()
        )
        result = plan_trip(
            TripRequest(origin, destination, data["departure"], data["load_lb"], int(data["interval_mi"])),
            routes_fn=osrm.get_routes,
            weather_fn=weather.forecast_hourly,
        )
    except UpstreamError as exc:
        return _upstream_error(exc)
    return Response(result)


@api_view(["POST"])
def heatmap(request):
    s = HeatmapRequestSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    d = s.validated_data
    try:
        result = build_heatmap(d["points"], d["start"], d["hours"], d["load_lb"], weather.forecast_hourly)
    except UpstreamError as exc:
        return _upstream_error(exc)
    return Response(result)
