"""Shared HTTP session with retries, timeouts and a small TTL cache.

Free public APIs (OSRM demo server, Open-Meteo, Photon) are rate limited, so we
cache identical requests for a short time and retry transient failures.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = os.getenv("HTTP_USER_AGENT", "weather-aware-truck-routing/1.0 (assessment project)")
DEFAULT_TIMEOUT = float(os.getenv("HTTP_TIMEOUT_SECONDS", "20"))


class UpstreamError(Exception):
    """Raised when a third-party API fails or returns something unusable."""

    def __init__(self, service: str, message: str, status: int | None = None):
        super().__init__(f"{service}: {message}")
        self.service = service
        self.status = status


class TTLCache:
    def __init__(self, ttl_seconds: int = 900, max_items: int = 2000):
        self.ttl = ttl_seconds
        self.max_items = max_items
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            hit = self._data.get(key)
            if not hit:
                return None
            expires, value = hit
            if expires < time.time():
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._data) >= self.max_items:
                # Drop the oldest ~10% to keep memory bounded.
                for k in sorted(self._data, key=lambda k: self._data[k][0])[: self.max_items // 10]:
                    self._data.pop(k, None)
            self._data[key] = (time.time() + self.ttl, value)


_cache = TTLCache(ttl_seconds=int(os.getenv("HTTP_CACHE_TTL_SECONDS", "900")))
_session_local = threading.local()


def _session() -> requests.Session:
    s = getattr(_session_local, "session", None)
    if s is None:
        s = requests.Session()
        retry = Retry(total=3, backoff_factor=0.6, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",))
        s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=16))
        s.mount("http://", HTTPAdapter(max_retries=retry, pool_maxsize=16))
        s.headers["User-Agent"] = USER_AGENT
        _session_local.session = s
    return s


def get_json(service: str, url: str, params: dict | None = None, cache: bool = True) -> Any:
    key = url + "?" + json.dumps(params or {}, sort_keys=True)
    if cache:
        hit = _cache.get(key)
        if hit is not None:
            return hit
    try:
        resp = _session().get(url, params=params, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        raise UpstreamError(service, f"request failed ({exc.__class__.__name__})") from exc
    if resp.status_code >= 400:
        raise UpstreamError(service, f"HTTP {resp.status_code}", resp.status_code)
    try:
        data = resp.json()
    except ValueError as exc:
        raise UpstreamError(service, "invalid JSON") from exc
    if cache:
        _cache.set(key, data)
    return data
