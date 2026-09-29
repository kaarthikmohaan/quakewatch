"""Public example locations and safe defaults for the USGS batch extractor."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Site:
    name: str
    latitude: float
    longitude: float
    radius_km: float = 250.0


SITES = {
    "seattle": Site("Seattle", 47.6062, -122.3321),
    "san-francisco": Site("San Francisco", 37.7749, -122.4194),
    "anchorage": Site("Anchorage", 61.2181, -149.9003),
}

USGS_QUERY_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
USGS_COUNT_URL = "https://earthquake.usgs.gov/fdsnws/event/1/count"
USER_AGENT = "QuakeWatch/0.1 (educational batch data project)"
REQUEST_TIMEOUT_SECONDS = 30.0
MAX_RESULTS_PER_WINDOW = 20_000
PARSER_VERSION = "1"

EVENT_HORIZON_YEARS = 5
