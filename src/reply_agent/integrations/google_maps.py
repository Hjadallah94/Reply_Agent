"""Live transit-time estimation for delivery-estimation reasoning (Doc 2 Section 9.1/9.5).

Uses the Routes API's Compute Route Matrix endpoint, not the legacy Distance Matrix API —
Google has marked Distance Matrix "Legacy" and recommends Routes API for new integrations
(verified against Google's own current docs before writing this, not assumed). Addresses are
passed as plain text waypoints (the API resolves them itself) — no separate geocoding call.

Real per-call cost, unlike every Meta API used elsewhere in this project — see Doc 5 Section 3.5
(deliberately left unpriced there pending real investigation, per instruction).
"""

import httpx

from reply_agent.config import get_settings

ROUTE_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"


class GoogleMapsError(RuntimeError):
    pass


async def estimate_transit_minutes(origin: str, destination: str) -> int:
    """Live, traffic-aware driving time between two addresses, in whole minutes."""
    settings = get_settings()
    payload = {
        "origins": [{"waypoint": {"address": origin}}],
        "destinations": [{"waypoint": {"address": destination}}],
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": "originIndex,destinationIndex,duration,distanceMeters,status,condition",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(ROUTE_MATRIX_URL, json=payload, headers=headers)

    if response.status_code >= 400:
        raise GoogleMapsError(
            f"Route matrix request failed ({response.status_code}): {response.text}"
        )

    results = response.json()
    if not results or results[0].get("condition") != "ROUTE_EXISTS":
        raise GoogleMapsError(f"No route found between {origin!r} and {destination!r}: {results}")

    duration_seconds = int(results[0]["duration"].rstrip("s"))
    return duration_seconds // 60
