import math
from datetime import datetime
import json
from config import Config
from backend.food_safety import parse_iso_or_local

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance between two points in kilometers."""
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    except (ValueError, TypeError):
        return 999.0
    
    R = 6371.0 # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

def evaluate_ngo_match(donation: dict, ngo: dict, now: datetime = None) -> dict:
    """
    Evaluates an NGO against a donation.
    Returns:
        dict: {
            'eligible': bool,
            'rejection_reasons': list[str],
            'matching_score': float,
            'distance_km': float,
            'factors': dict,
            'explanation': str,
            'proposed_meals': int
        }
    """
    now = now or datetime.now()
    reasons = []

    # 1. Hard Constraints Check
    # A. Donation safety status
    if donation.get("safety_status") == "Rejected":
        reasons.append("Donation was rejected by food safety validation.")

    # B. Expiration / Collection window
    deadline = parse_iso_or_local(donation.get("collection_deadline"))
    if deadline and deadline < now:
        reasons.append("Donation collection deadline has passed.")

    # C. Capacity check
    daily_cap = int(ngo.get("daily_capacity", 0))
    occupancy = int(ngo.get("current_occupancy", 0))
    available_capacity = max(0, daily_cap - occupancy)

    if available_capacity <= 0:
        reasons.append(f"NGO '{ngo.get('name')}' has reached full capacity ({occupancy}/{daily_cap} meals).")

    # D. Dietary Compatibility
    # Donation classification: 'Vegetarian', 'Vegan', 'Non-Veg', 'Halal', 'Any'
    don_diet = (donation.get("dietary_classification") or "Any").strip()
    ngo_diet_raw = ngo.get("dietary_preferences") or "[]"
    
    if isinstance(ngo_diet_raw, str):
        try:
            ngo_diet_list = json.loads(ngo_diet_raw)
        except Exception:
            ngo_diet_list = [d.strip() for d in ngo_diet_raw.split(",") if d.strip()]
    else:
        ngo_diet_list = list(ngo_diet_raw)

    if not ngo_diet_list or "Any" in ngo_diet_list:
        dietary_compatible = True
    else:
        # Check strict rules
        if don_diet == "Non-Veg" and not ("Non-Veg" in ngo_diet_list or "Any" in ngo_diet_list):
            dietary_compatible = False
            reasons.append(f"Dietary mismatch: donation is '{don_diet}' but NGO only accepts {ngo_diet_list}.")
        elif don_diet == "Vegetarian" and ("Vegan" in ngo_diet_list and len(ngo_diet_list) == 1):
            # NGO only accepts strictly Vegan
            dietary_compatible = False
            reasons.append("Dietary mismatch: donation is Vegetarian (contains dairy) while NGO requires strict Vegan.")
        else:
            dietary_compatible = True

    # If any hard constraint failed, return non-eligible
    if reasons:
        return {
            "eligible": False,
            "rejection_reasons": reasons,
            "matching_score": 0.0,
            "distance_km": haversine_distance(
                donation.get("donor_latitude", 0), donation.get("donor_longitude", 0),
                ngo.get("latitude", 0), ngo.get("longitude", 0)
            ),
            "factors": {},
            "explanation": f"Ineligible for donation: {'; '.join(reasons)}",
            "proposed_meals": 0
        }

    # 2. Individual Factor Scoring (Each normalized 0-100)
    # Factor A: Distance Suitability (30%)
    donor_lat = donation.get("donor_latitude")
    donor_lon = donation.get("donor_longitude")
    ngo_lat = ngo.get("latitude")
    ngo_lon = ngo.get("longitude")
    dist_km = haversine_distance(donor_lat, donor_lon, ngo_lat, ngo_lon)

    # 0 to 25 km scale; 0 km -> 100, 25+ km -> 0
    distance_score = max(0.0, min(100.0, 100.0 - (dist_km * 4.0)))

    # Factor B: Quantity Compatibility (25%)
    unallocated_qty = max(0, int(donation.get("quantity", 0)) - int(donation.get("allocated_quantity", 0)))
    if unallocated_qty <= 0:
        unallocated_qty = int(donation.get("quantity", 1))

    # How well does the unallocated surplus match NGO remaining capacity?
    if unallocated_qty <= available_capacity:
        # NGO can take entire donation
        quantity_score = 100.0
    else:
        # NGO can take a partial batch
        quantity_score = max(30.0, (available_capacity / unallocated_qty) * 100.0)
    quantity_score = min(100.0, quantity_score)

    # Factor C: Urgency / Time Suitability (20%)
    remaining_hours = 4.0
    if deadline:
        remaining_hours = max(0.1, (deadline - now).total_seconds() / 3600.0)

    # If deadline is very tight (< 2 hours), distance matters even more
    if remaining_hours <= 2.0:
        urgency_score = 100.0 if dist_km <= 5.0 else max(10.0, 100.0 - (dist_km * 7.0))
    elif remaining_hours <= 5.0:
        urgency_score = max(40.0, 100.0 - (dist_km * 3.5))
    else:
        urgency_score = 85.0 # Plentiful time window

    # Factor D: Food Category / Preference Match (15%)
    don_category = donation.get("food_category", "Cooked Meals")
    ngo_req_raw = ngo.get("food_requirements") or "[]"
    if isinstance(ngo_req_raw, str):
        try:
            ngo_req_list = json.loads(ngo_req_raw)
        except Exception:
            ngo_req_list = [r.strip() for r in ngo_req_raw.split(",") if r.strip()]
    else:
        ngo_req_list = list(ngo_req_raw)

    if not ngo_req_list or don_category in ngo_req_list:
        preference_score = 100.0
    else:
        preference_score = 60.0 # Can accept with secondary priority

    # Factor E: Recipient Capacity Suitability (10%)
    headroom_ratio = available_capacity / max(1, daily_cap)
    capacity_score = min(100.0, max(20.0, headroom_ratio * 100.0))

    # 3. Weighted Final Composite Score
    w_dist = Config.MATCH_WEIGHT_DISTANCE
    w_qty = Config.MATCH_WEIGHT_QUANTITY
    w_urg = Config.MATCH_WEIGHT_URGENCY
    w_pref = Config.MATCH_WEIGHT_DIETARY
    w_cap = Config.MATCH_WEIGHT_CAPACITY

    final_score = round(
        (distance_score * w_dist) +
        (quantity_score * w_qty) +
        (urgency_score * w_urg) +
        (preference_score * w_pref) +
        (capacity_score * w_cap),
        1
    )

    # 4. Propose safe quantity allocation (capped by NGO capacity and donation surplus)
    proposed_meals = min(unallocated_qty, available_capacity)

    # 5. Natural Language Backend Explanation
    explanation_parts = [
        f"Recipient scored {final_score}/100.",
        f"Proximity: {dist_km} km away ({round(distance_score, 1)} pts).",
        f"Capacity headroom: can absorb {proposed_meals} of {unallocated_qty} available meals ({available_capacity} capacity remaining).",
        f"Time sensitivity: {round(remaining_hours, 1)} hrs before deadline ({round(urgency_score, 1)} pts)."
    ]
    if preference_score == 100.0:
        explanation_parts.append(f"Strong preference match for '{don_category}'.")

    return {
        "eligible": True,
        "rejection_reasons": [],
        "matching_score": final_score,
        "distance_km": dist_km,
        "factors": {
            "distance_score": round(distance_score, 1),
            "quantity_score": round(quantity_score, 1),
            "urgency_score": round(urgency_score, 1),
            "preference_score": round(preference_score, 1),
            "capacity_score": round(capacity_score, 1)
        },
        "explanation": " ".join(explanation_parts),
        "proposed_meals": proposed_meals
    }

def rank_ngos_for_donation(donation: dict, ngos: list, now: datetime = None) -> list:
    """
    Ranks all candidate NGOs for a given donation.
    Filters out ineligible candidates, sorts eligible by matching score descending.
    """
    scored = []
    for ngo in ngos:
        evaluation = evaluate_ngo_match(donation, ngo, now=now)
        result_item = {
            "ngo_id": ngo["id"],
            "ngo_name": ngo["name"],
            "address": ngo.get("address", ""),
            "latitude": ngo.get("latitude"),
            "longitude": ngo.get("longitude"),
            "daily_capacity": ngo.get("daily_capacity"),
            "current_occupancy": ngo.get("current_occupancy"),
            "available_capacity": max(0, ngo.get("daily_capacity", 0) - ngo.get("current_occupancy", 0)),
            "dietary_preferences": ngo.get("dietary_preferences"),
            **evaluation
        }
        scored.append(result_item)

    # Sort: Eligible first (highest score descending), then Ineligible
    scored.sort(key=lambda x: (1 if x["eligible"] else 0, x["matching_score"]), reverse=True)
    return scored

def compute_multi_ngo_split(donation: dict, ranked_ngos: list) -> dict:
    """
    Computes a multi-recipient allocation split across top-ranked eligible NGOs.
    
    Guarantees:
      1. Total allocated meals NEVER exceeds the available unallocated donation surplus.
      2. No NGO receives more meals than its remaining available capacity headroom.
      3. Allocations follow matching score priority (highest matching score first).
      4. Proposed status prevents double allocation of the same batch.
    """
    total_quantity = int(donation.get("quantity", 0))
    already_allocated = int(donation.get("allocated_quantity", 0))
    surplus_available = max(0, total_quantity - already_allocated)

    if surplus_available <= 0:
        return {
            "status": "depleted",
            "message": "Donation has already been fully allocated.",
            "total_available": surplus_available,
            "total_allocated": 0,
            "remaining_unallocated": 0,
            "distribution_plan": []
        }

    remaining_surplus = surplus_available
    distribution_plan = []

    # Filter only eligible candidate NGOs
    eligible_ngos = [ngo for ngo in ranked_ngos if ngo.get("eligible")]

    for candidate in eligible_ngos:
        if remaining_surplus <= 0:
            break

        ngo_capacity = int(candidate.get("available_capacity", 0))
        if ngo_capacity <= 0:
            continue

        # Allocate minimum of remaining surplus and recipient capacity
        meals_for_ngo = min(remaining_surplus, ngo_capacity)

        distribution_plan.append({
            "ngo_id": candidate["ngo_id"],
            "ngo_name": candidate["ngo_name"],
            "distance_km": candidate.get("distance_km", 0.0),
            "matching_score": candidate.get("matching_score", 0.0),
            "allocated_meals": meals_for_ngo,
            "ngo_capacity_before": ngo_capacity,
            "ngo_capacity_after": ngo_capacity - meals_for_ngo,
            "status": "Proposed"
        })

        remaining_surplus -= meals_for_ngo

    total_planned = surplus_available - remaining_surplus

    # Verification check: sum must not exceed surplus
    assert total_planned <= surplus_available, "Invariant violated: allocated quantity exceeds surplus!"

    return {
        "status": "success",
        "donation_id": donation.get("id"),
        "food_name": donation.get("food_name"),
        "total_available": surplus_available,
        "total_allocated": total_planned,
        "remaining_unallocated": remaining_surplus,
        "recipient_count": len(distribution_plan),
        "distribution_plan": distribution_plan
    }
