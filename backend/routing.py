"""
FoodLink AI — Route Optimization Module
Integrates OSRM Table and Route APIs for real road-distance calculations.
Falls back gracefully to Haversine approximation when OSRM is unavailable.

Features:
  - OSRM Table API for distance/duration matrices
  - OSRM Route API for full GeoJSON driving geometry
  - Permutation-based stop ordering (≤6 stops) or nearest-neighbor greedy (>6)
  - Per-leg and cumulative estimated delivery times
  - Collection deadline violation warnings
  - Labeled routing mode (OSRM vs Haversine fallback)
"""

import requests
import itertools
import logging
from datetime import datetime, timedelta
from config import Config
from backend.matching import haversine_distance
from backend.food_safety import parse_iso_or_local

logger = logging.getLogger(__name__)


def get_osrm_distance_matrix(coordinates: list, timeout: int = None) -> tuple:
    """
    Calls OSRM Table API for driving distance and duration matrices.
    
    Args:
        coordinates: list of [longitude, latitude] pairs.
        timeout: request timeout in seconds.
        
    Returns:
        (distances_matrix, durations_matrix) or (None, None) on failure.
        distances are in meters, durations in seconds.
    """
    timeout = timeout or Config.OSRM_TIMEOUT
    coord_str = ";".join([f"{lon:.6f},{lat:.6f}" for lon, lat in coordinates])
    url = f"{Config.OSRM_BASE_URL}/table/v1/driving/{coord_str}?annotations=distance,duration"

    try:
        logger.info(f"OSRM Table API request: {len(coordinates)} points, timeout={timeout}s")
        resp = requests.get(url, timeout=timeout)
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "Ok":
                logger.info("OSRM Table API returned successfully.")
                return data.get("distances"), data.get("durations")
            else:
                logger.warning(f"OSRM Table API returned code: {data.get('code')}, message: {data.get('message', 'N/A')}")
        else:
            logger.warning(f"OSRM Table API HTTP {resp.status_code}: {resp.text[:200]}")

    except requests.exceptions.Timeout:
        logger.warning(f"OSRM Table API timed out after {timeout}s. Using Haversine fallback.")
    except requests.exceptions.ConnectionError as ce:
        logger.warning(f"OSRM Table API connection error: {ce}. Server may be unreachable.")
    except requests.exceptions.RequestException as re:
        logger.warning(f"OSRM Table API request error: {re}")
    except Exception as e:
        logger.error(f"Unexpected error calling OSRM Table API: {e}")

    return None, None


def get_osrm_route_geometry(ordered_coords: list, timeout: int = None) -> dict:
    """
    Calls OSRM Route API to get full polyline GeoJSON geometry for ordered stops.
    
    Args:
        ordered_coords: list of [longitude, latitude] in delivery order.
        timeout: request timeout in seconds.
        
    Returns:
        dict with geometry, distance_meters, duration_seconds, legs or None on failure.
    """
    timeout = timeout or Config.OSRM_TIMEOUT
    coord_str = ";".join([f"{lon:.6f},{lat:.6f}" for lon, lat in ordered_coords])
    url = f"{Config.OSRM_BASE_URL}/route/v1/driving/{coord_str}?overview=full&geometries=geojson&steps=false"

    try:
        logger.info(f"OSRM Route API request: {len(ordered_coords)} waypoints, timeout={timeout}s")
        resp = requests.get(url, timeout=timeout)

        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "Ok" and data.get("routes"):
                best_route = data["routes"][0]
                legs_data = best_route.get("legs", [])
                logger.info(f"OSRM Route API returned: {round(best_route.get('distance', 0)/1000, 2)} km, "
                           f"{round(best_route.get('duration', 0)/60, 1)} min, {len(legs_data)} legs")
                return {
                    "geometry": best_route.get("geometry"),
                    "distance_meters": best_route.get("distance", 0),
                    "duration_seconds": best_route.get("duration", 0),
                    "legs": [{
                        "distance_meters": leg.get("distance", 0),
                        "duration_seconds": leg.get("duration", 0),
                        "summary": leg.get("summary", "")
                    } for leg in legs_data]
                }
            else:
                logger.warning(f"OSRM Route API code: {data.get('code')}, message: {data.get('message', 'N/A')}")
        else:
            logger.warning(f"OSRM Route API HTTP {resp.status_code}")

    except requests.exceptions.Timeout:
        logger.warning(f"OSRM Route API timed out after {timeout}s.")
    except requests.exceptions.ConnectionError:
        logger.warning("OSRM Route API unreachable. Falling back to straight-line geometry.")
    except requests.exceptions.RequestException as re:
        logger.warning(f"OSRM Route API request error: {re}")
    except Exception as e:
        logger.error(f"Unexpected error calling OSRM Route API: {e}")

    return None


def optimize_delivery_route(donor_info: dict, recipient_stops: list, departure_time: datetime = None) -> dict:
    """
    Calculates ordered route from donor to 1 or more recipient NGOs.
    Prioritizes real OSRM road distance and geometry with graceful Haversine fallback.
    
    Returns comprehensive route data including:
      - Ordered stops with ETAs and cumulative distances
      - Per-leg distance/duration breakdown
      - GeoJSON route geometry for Leaflet rendering
      - Delivery deadline warnings
      - Estimated delivery completion time
    """
    departure_time = departure_time or datetime.now()
    all_points = [donor_info] + list(recipient_stops)
    n = len(all_points)

    if n <= 1:
        return {
            "status": "error",
            "error": "At least one recipient stop is required for route optimization."
        }

    # Prepare coordinates as [lon, lat] for OSRM
    coords = [[float(p.get("longitude", 0)), float(p.get("latitude", 0))] for p in all_points]

    # Try OSRM Table API for distance/duration matrix
    dist_matrix, dur_matrix = get_osrm_distance_matrix(coords)
    is_osrm = (dist_matrix is not None and dur_matrix is not None)
    osrm_table_error = None

    # If OSRM table is unavailable, build fallback matrices using Haversine × 1.30 road winding factor
    if not is_osrm:
        osrm_table_error = "OSRM Table API unavailable. Using Haversine approximation with 1.3x road winding factor."
        logger.info(osrm_table_error)
        dist_matrix = [[0.0] * n for _ in range(n)]
        dur_matrix = [[0.0] * n for _ in range(n)]
        # Average urban speed in Tricity ~ 25 km/h = ~6.94 m/s
        avg_speed_mps = 6.94
        for i in range(n):
            for j in range(n):
                if i != j:
                    h_km = haversine_distance(
                        all_points[i]["latitude"], all_points[i]["longitude"],
                        all_points[j]["latitude"], all_points[j]["longitude"]
                    )
                    road_m = h_km * 1000.0 * 1.30  # 1.3x road winding factor
                    dist_matrix[i][j] = road_m
                    dur_matrix[i][j] = road_m / avg_speed_mps

    # Route Optimization Algorithm
    # Start node is fixed at index 0 (Donor)
    recipient_indices = list(range(1, n))
    best_order = []
    best_cost = float("inf")
    algorithm_used = ""

    if len(recipient_indices) <= 6:
        # Exact permutation search for small number of stops (reliably optimal for ≤6 stops)
        algorithm_used = "Exhaustive Permutation Search (exact)"
        for perm in itertools.permutations(recipient_indices):
            seq = [0] + list(perm)
            cost = sum(dur_matrix[seq[k]][seq[k+1]] for k in range(len(seq) - 1))
            if cost < best_cost:
                best_cost = cost
                best_order = seq
    else:
        # Nearest neighbor greedy algorithm for larger stop counts
        algorithm_used = "Nearest Neighbor Greedy Heuristic"
        current = 0
        unvisited = set(recipient_indices)
        best_order = [0]
        while unvisited:
            next_node = min(unvisited, key=lambda x: dur_matrix[current][x])
            unvisited.remove(next_node)
            best_order.append(next_node)
            current = next_node

    # Build ordered stop details and calculate cumulative arrival times
    ordered_stops = []
    cumulative_seconds = 0
    cumulative_distance_meters = 0
    deadline_warnings = []
    legs_info = []

    ordered_coords = [coords[idx] for idx in best_order]

    # Fetch geometry from OSRM Route API if the table API worked
    route_geom_data = None
    osrm_route_error = None
    if is_osrm:
        route_geom_data = get_osrm_route_geometry(ordered_coords)
        if not route_geom_data:
            osrm_route_error = "OSRM Route API call failed. Geometry will use straight-line fallback."

    for i, idx in enumerate(best_order):
        point = all_points[idx]
        is_donor = (idx == 0)

        leg_dist = 0
        leg_dur = 0

        if i > 0:
            prev_idx = best_order[i - 1]
            leg_dur = dur_matrix[prev_idx][idx]
            leg_dist = dist_matrix[prev_idx][idx]

            # Use OSRM Route API leg data if available for more accurate per-leg info
            if route_geom_data and route_geom_data.get("legs") and (i - 1) < len(route_geom_data["legs"]):
                osrm_leg = route_geom_data["legs"][i - 1]
                leg_dist = osrm_leg.get("distance_meters", leg_dist)
                leg_dur = osrm_leg.get("duration_seconds", leg_dur)

            cumulative_seconds += leg_dur
            cumulative_distance_meters += leg_dist

            leg_duration_min = round(leg_dur / 60.0, 1)
            leg_arrival = departure_time + timedelta(seconds=cumulative_seconds)

            legs_info.append({
                "from_stop": all_points[prev_idx].get("name", f"Stop {i-1}"),
                "to_stop": point.get("name", f"Stop {i}"),
                "distance_km": round(leg_dist / 1000.0, 2),
                "duration_min": leg_duration_min,
                "arrival_time": leg_arrival.strftime("%Y-%m-%d %H:%M"),
                "road_summary": ""
            })

        eta = departure_time + timedelta(seconds=cumulative_seconds)

        # Check deadlines
        stop_deadline_raw = point.get("collection_deadline")
        deadline_status = "ok"
        if stop_deadline_raw:
            deadline_dt = parse_iso_or_local(stop_deadline_raw)
            if deadline_dt:
                time_to_deadline_min = round((deadline_dt - eta).total_seconds() / 60.0, 1)
                if eta > deadline_dt:
                    deadline_status = "overdue"
                    deadline_warnings.append(
                        f"Warning: Estimated arrival at '{point.get('name')}' ({eta.strftime('%H:%M')}) "
                        f"is {abs(time_to_deadline_min)} min after deadline ({deadline_dt.strftime('%H:%M')})."
                    )
                elif time_to_deadline_min < 30:
                    deadline_status = "tight"
                    deadline_warnings.append(
                        f"Caution: Only {time_to_deadline_min} minutes margin at '{point.get('name')}' before deadline."
                    )

        ordered_stops.append({
            "stop_sequence": i,
            "type": "donor" if is_donor else "recipient",
            "id": point.get("id"),
            "name": point.get("name"),
            "address": point.get("address", ""),
            "latitude": point.get("latitude"),
            "longitude": point.get("longitude"),
            "meals_allocated": point.get("meals_allocated", point.get("quantity", 0)),
            "eta": eta.strftime("%Y-%m-%d %H:%M"),
            "eta_display": eta.strftime("%I:%M %p"),
            "cumulative_distance_km": round(cumulative_distance_meters / 1000.0, 2),
            "cumulative_travel_minutes": round(cumulative_seconds / 60.0, 1),
            "leg_duration_min": round(leg_dur / 60.0, 1) if i > 0 else 0,
            "leg_distance_km": round(leg_dist / 1000.0, 2) if i > 0 else 0,
            "deadline_status": deadline_status
        })

    # Prepare GeoJSON geometry
    if route_geom_data and route_geom_data.get("geometry"):
        geojson_geometry = route_geom_data["geometry"]
        total_dist_km = round(route_geom_data["distance_meters"] / 1000.0, 2)
        total_dur_min = round(route_geom_data["duration_seconds"] / 60.0, 1)
        routing_mode = "OSRM OpenStreetMap Driving API"
    else:
        # Fallback straight-line polyline
        geojson_geometry = {
            "type": "LineString",
            "coordinates": ordered_coords
        }
        total_dist_km = round(cumulative_distance_meters / 1000.0, 2)
        total_dur_min = round(cumulative_seconds / 60.0, 1)
        routing_mode = "Haversine Urban Distance Approximation (1.3x Road Factor — OSRM unavailable)"

    # Calculate estimated delivery completion
    completion_time = departure_time + timedelta(seconds=cumulative_seconds)

    return {
        "status": "success",
        "routing_mode": routing_mode,
        "is_osrm": bool(is_osrm and route_geom_data),
        "algorithm": algorithm_used,
        "total_distance_km": total_dist_km,
        "total_duration_minutes": total_dur_min,
        "departure_time": departure_time.strftime("%Y-%m-%d %H:%M"),
        "estimated_completion": completion_time.strftime("%Y-%m-%d %H:%M"),
        "estimated_completion_display": completion_time.strftime("%I:%M %p"),
        "stops_count": len(ordered_stops),
        "ordered_stops": ordered_stops,
        "legs": legs_info,
        "deadline_warnings": deadline_warnings,
        "fallback_notices": [msg for msg in [osrm_table_error, osrm_route_error] if msg],
        "geojson": {
            "type": "Feature",
            "properties": {
                "name": "FoodLink Delivery Route",
                "distance_km": total_dist_km,
                "duration_min": total_dur_min,
                "mode": routing_mode
            },
            "geometry": geojson_geometry
        }
    }
