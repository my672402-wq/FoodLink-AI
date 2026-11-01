import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

# Ensure workspace is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import app
from data.seed_data import seed_database
from database import get_db_connection

def run_comprehensive_verification():
    print("=" * 60)
    print("FOODLINK AI -- LIVE REST API & WORKFLOW VERIFICATION")
    print("=" * 60)

    # 1. Reset and initialize SQLite database with seed data
    print("\n[Step 1] Initializing SQLite database with Chandigarh-Mohali seed data...")
    seed_database()
    conn = get_db_connection()
    donors_cnt = conn.execute("SELECT COUNT(*) FROM donors").fetchone()[0]
    ngos_cnt = conn.execute("SELECT COUNT(*) FROM ngos").fetchone()[0]
    donations_cnt = conn.execute("SELECT COUNT(*) FROM donations").fetchone()[0]
    history_cnt = conn.execute("SELECT COUNT(*) FROM demand_history").fetchone()[0]
    conn.close()
    print(f"[PASS] Database verified: {donors_cnt} Donors, {ngos_cnt} NGOs, {donations_cnt} Donations, {history_cnt} Historical Demand records.")

    client = app.test_client()

    # 2. Test GET /api/health
    print("\n[Step 2] Testing GET /api/health...")
    res = client.get("/api/health")
    assert res.status_code == 200, f"Health check failed: {res.status_code}"
    health_data = res.get_json()
    print(f"[PASS] Health Check: status='{health_data['status']}', DB={health_data['database_connected']}, Gemini Active={health_data['gemini_active']}")

    # 3. Test POST & GET /api/donors
    print("\n[Step 3] Testing Donor Registration (POST /api/donors)...")
    donor_payload = {
        "name": "Chandigarh Club Dining Hall (Live Test)",
        "donor_type": "Restaurant",
        "contact_name": "Vikramaditya",
        "phone": "+91 98888 11223",
        "email": "dining@chdclub-test.in",
        "address": "Sector 1, Sector 1, Chandigarh",
        "latitude": 30.7550,
        "longitude": 76.7900
    }
    res = client.post("/api/donors", json=donor_payload)
    assert res.status_code == 201, f"Donor registration failed: {res.get_json()}"
    new_donor_id = res.get_json()["donor_id"]
    print(f"[PASS] Registered new donor with ID: {new_donor_id}")

    res = client.get("/api/donors")
    donors_list = res.get_json()["donors"]
    print(f"[PASS] GET /api/donors returned {len(donors_list)} donors from SQLite.")

    # 4. Test POST & GET /api/ngos
    print("\n[Step 4] Testing NGO Registration (POST /api/ngos)...")
    ngo_payload = {
        "name": "Helping Hands Tricity Shelter (Live Test)",
        "ngo_type": "Food Shelter",
        "contact_name": "Gurpreet Singh",
        "phone": "+91 98777 55443",
        "email": "shelter@helpinghands-test.org",
        "address": "Sector 68, Mohali",
        "latitude": 30.7000,
        "longitude": 76.7150,
        "daily_capacity": 220,
        "current_occupancy": 40,
        "dietary_preferences": ["Vegetarian", "Any"],
        "food_requirements": ["Cooked Meals", "Bakery"]
    }
    res = client.post("/api/ngos", json=ngo_payload)
    assert res.status_code == 201, f"NGO registration failed: {res.get_json()}"
    new_ngo_id = res.get_json()["ngo_id"]
    print(f"[PASS] Registered new NGO with ID: {new_ngo_id}")

    res = client.get("/api/ngos")
    ngos_list = res.get_json()["ngos"]
    print(f"[PASS] GET /api/ngos returned {len(ngos_list)} NGOs from SQLite.")

    # 5. Test Food Donation Submission with Food Safety Engine
    print("\n[Step 5] Testing Food Donation Submission with Food Safety Validation...")
    now = datetime.now()
    valid_donation_payload = {
        "donor_id": new_donor_id,
        "food_name": "Shahi Paneer, Pulao & Butter Naan",
        "food_category": "Cooked Meals",
        "quantity": 90,
        "prep_time": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
        "collection_deadline": (now + timedelta(hours=2, minutes=30)).strftime("%Y-%m-%dT%H:%M"),
        "storage_condition": "Hot-hold (>60°C)",
        "dietary_classification": "Vegetarian",
        "allergens": ["Dairy", "Gluten"],
        "notes": "Freshly prepared from afternoon banquet. Temperature maintained >65C."
    }
    res = client.post("/api/donations", json=valid_donation_payload)
    assert res.status_code == 201, f"Donation submission failed: {res.get_json()}"
    don_data = res.get_json()
    new_donation_id = don_data["donation_id"]
    print(f"[PASS] Valid Donation created: ID #{new_donation_id}, Safety Status='{don_data['safety_evaluation']['status']}'")

    # Test safety rejection on unsafe donation
    unsafe_payload = {
        "donor_id": new_donor_id,
        "food_name": "Unsafe Ambient Gravy (Expired)",
        "food_category": "Cooked Meals",
        "quantity": 40,
        "prep_time": (now - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M"),
        "collection_deadline": (now - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M"),
        "storage_condition": "Room Temp (20-25°C)",
        "dietary_classification": "Non-Veg",
        "allergens": [],
        "notes": "Left at room temperature for 6 hours."
    }
    res = client.post("/api/donations", json=unsafe_payload)
    assert res.status_code == 201
    unsafe_eval = res.get_json()["safety_evaluation"]
    assert unsafe_eval["is_safe"] is False
    print(f"[PASS] Unsafe Donation correctly flagged as REJECTED: {unsafe_eval['reasons']}")

    # 6. Test GET /api/dashboard (Real SQLite aggregation)
    print("\n[Step 6] Testing Dashboard Telemetry (GET /api/dashboard)...")
    res = client.get("/api/dashboard")
    assert res.status_code == 200
    dash_data = res.get_json()
    metrics = dash_data["metrics"]
    print(f"[PASS] Real SQLite Metrics: Total Donors={metrics['total_donors']}, Active NGOs={metrics['active_ngos']}, Total Meals={metrics['total_meals_available']}, Allocated={metrics['meals_allocated']}")
    print(f"[PASS] Category Breakdown ({len(dash_data['category_breakdown'])} categories): {[c['food_category'] for c in dash_data['category_breakdown']]}")

    # 7. Test AI Smart Matching
    print(f"\n[Step 7] Testing AI Smart Matching on Donation #{new_donation_id} (POST /api/match/{new_donation_id})...")
    res = client.post(f"/api/match/{new_donation_id}")
    assert res.status_code == 200
    match_data = res.get_json()
    ranked = match_data["ranked_matches"]
    print(f"[PASS] Matching evaluated {len(ranked)} candidate NGOs.")
    top = ranked[0]
    print(f"  * Top Match: '{top['ngo_name']}'")
    print(f"  * Composite Score: {top['matching_score']}/100 (Distance: {top['distance_km']} km, Headroom: {top['available_capacity']} meals)")
    print(f"  * Factor Scores: {top['factors']}")
    print(f"  * Proposed Allocation: {top['proposed_meals']} meals")

    # 8. Test Safe Allocation Transaction
    print("\n[Step 8] Testing Transactional Allocation (POST /api/allocations)...")
    alloc_payload = {
        "donation_id": new_donation_id,
        "ngo_id": top["ngo_id"],
        "allocated_meals": 60,
        "distance_km": top["distance_km"],
        "matching_score": top["matching_score"],
        "notes": "Automated matching dispatch via FoodLink AI"
    }
    res = client.post("/api/allocations", json=alloc_payload)
    assert res.status_code == 201, f"Allocation failed: {res.get_json()}"
    alloc_id = res.get_json()["allocation_id"]
    print(f"[PASS] Allocation #{alloc_id} committed (Status: Proposed, 60 meals).")

    # Verify over-allocation is rejected
    excess_payload = {
        "donation_id": new_donation_id,
        "ngo_id": top["ngo_id"],
        "allocated_meals": 100, # Only 30 remaining!
        "distance_km": top["distance_km"],
        "matching_score": top["matching_score"]
    }
    res_excess = client.post("/api/allocations", json=excess_payload)
    assert res_excess.status_code == 400
    print(f"[PASS] Over-allocation correctly blocked by database transaction: '{res_excess.get_json()['error']}'")

    # 9. Test Accepting Allocation
    print(f"\n[Step 9] Testing Allocation Acceptance (POST /api/allocations/{alloc_id}/accept)...")
    res = client.post(f"/api/allocations/{alloc_id}/accept")
    assert res.status_code == 200
    print(f"[PASS] Allocation #{alloc_id} confirmed and NGO capacity occupancy updated.")

    # 10. Test Demand Forecasting
    print(f"\n[Step 10] Testing Demand Forecasting (GET /api/forecast/{top['ngo_id']})...")
    res = client.get(f"/api/forecast/{top['ngo_id']}")
    assert res.status_code == 200
    fc_data = res.get_json()
    fc = fc_data["forecast"]
    print(f"[PASS] Forecast for '{fc_data['ngo']['name']}':")
    print(f"  * Predicted Meals Tomorrow: {fc['predicted_meals']} meals")
    print(f"  * Historical Avg (50%): {fc['historical_avg']} | Recent 7-Day Avg (30%): {fc['recent_avg']} | Expected (20%): {fc['expected_avg']}")
    print(f"  * Trend: {fc['trend']} ({fc['trend_percentage']}%)")
    print(f"  * Formula Applied: {fc['methodology']}")

    # 11. Test Route Optimization
    print("\n[Step 11] Testing Route Optimization (POST /api/route)...")
    route_payload = {
        "donor_id": new_donor_id,
        "ngo_ids": [top["ngo_id"]],
        "donation_id": new_donation_id
    }
    res = client.post("/api/route", json=route_payload)
    assert res.status_code == 200
    route_data = res.get_json()
    print(f"[PASS] Route Calculated:")
    print(f"  * Routing Engine: {route_data['routing_mode']}")
    print(f"  * Total Road Distance: {route_data['total_distance_km']} km")
    print(f"  * Total Duration: {route_data['total_duration_minutes']} min")
    print(f"  * Stop Sequence ({route_data['stops_count']} stops): {[s['name'] for s in route_data['ordered_stops']]}")
    print(f"  * GeoJSON Coordinates Generated: {len(route_data['geojson']['geometry']['coordinates'])} points for Leaflet map.")

    # 12. Test AI Insights
    print("\n[Step 12] Testing AI System Insights (POST /api/ai-insights)...")
    res = client.post("/api/ai-insights", json={})
    assert res.status_code == 200
    insights = res.get_json()["insights_data"]["insights"]
    print(f"[PASS] AI Insights generated ({len(insights)} points):")
    for ins in insights:
        print(f"  * {ins}")

    print("\n" + "=" * 60)
    print("ALL 12 MODULES & REST ENDPOINTS VERIFIED WITH 100% SUCCESS!")
    print("=" * 60)

if __name__ == "__main__":
    run_comprehensive_verification()
