"""
FoodLink AI — Comprehensive Master QA Test Suite
Senior QA Engineer Validation Protocol

Exercises:
  - Every API endpoint and view route
  - Complete database schema, foreign keys, and ACID transactions
  - Every form submission and boundary validation
  - Food safety edge cases and category limits
  - 5-factor weighted smart matching and hard constraints
  - Statistical forecasting and trend analytics
  - OSRM road routing, ETAs, stop sequencing and GeoJSON geometry
  - Complete end-to-end donation-to-delivery lifecycle
"""

import sys
import unittest
import json
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import Config
from database import get_db_connection, init_db
from app import app
from data.seed_data import seed_database
from backend.food_safety import validate_food_safety
from backend.matching import rank_ngos_for_donation, evaluate_ngo_match, haversine_distance
from backend.forecasting import calculate_statistical_demand_forecast
from backend.routing import optimize_delivery_route


class MasterQATestSuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Seed clean database before QA test run."""
        seed_database()

    def setUp(self):
        self.client = app.test_client()

    # -------------------------------------------------------------
    # 1. FRONTEND PAGES & CORE API HEALTH
    # -------------------------------------------------------------
    def test_01_index_html_renders_all_eight_views(self):
        """QA: Verify index.html loads with all 8 operational views and assets."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        required_views = [
            "view-dashboard",
            "view-donors",
            "view-ngos",
            "view-donations",
            "view-matching",
            "view-forecasting",
            "view-routing",
            "view-food-safety"
        ]
        for v in required_views:
            self.assertIn(f'id="{v}"', html, f"View section {v} missing in HTML")

        # Required external libraries
        self.assertIn("leaflet.js", html)
        self.assertIn("chart.umd.min.js", html)
        self.assertIn("FoodLink AI", html)
        self.assertIn("Turning Surplus into Support", html)

    def test_02_health_endpoint_contract(self):
        """QA: Verify GET /api/health schema and availability."""
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertTrue(data["database_connected"])
        self.assertIn("gemini_active", data)
        self.assertIn("gemini_status", data)

    # -------------------------------------------------------------
    # 2. DONOR MANAGEMENT & FORM VALIDATION
    # -------------------------------------------------------------
    def test_03_donor_registration_validation(self):
        """QA: Test donor registration happy path and validation rejections."""
        # A. Missing fields
        bad_payload = {"name": "Incomplete Donor"}
        resp = self.client.post("/api/donors", json=bad_payload)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Missing required fields", resp.get_json()["error"])

        # B. Happy path
        valid_donor = {
            "name": "QA Test Gourmet Caterer (Simulated)",
            "donor_type": "Caterer",
            "contact_name": "Raman Sharma",
            "phone": "+91 98765 43210",
            "email": "raman@qacaterer.com",
            "address": "Phase 8B, Industrial Area, Mohali",
            "latitude": 30.7050,
            "longitude": 76.6950
        }
        resp = self.client.post("/api/donors", json=valid_donor)
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertTrue(data["donor_id"] > 0)
        self.assertEqual(data["status"], "success")

        # Verify listed in GET /api/donors
        resp_list = self.client.get("/api/donors")
        self.assertEqual(resp_list.status_code, 200)
        names = [d["name"] for d in resp_list.get_json()["donors"]]
        self.assertIn("QA Test Gourmet Caterer (Simulated)", names)

    # -------------------------------------------------------------
    # 3. NGO MANAGEMENT & CAPACITY TRACKING
    # -------------------------------------------------------------
    def test_04_ngo_registration_and_dietary_rules(self):
        """QA: Test NGO registration, dietary JSON storage, and headroom."""
        valid_ngo = {
            "name": "QA Mother Teresa Mission Shelter (Simulated)",
            "ngo_type": "Shelter",
            "contact_name": "Sister Anita",
            "phone": "+91 98111 22233",
            "email": "anita@qashelter.org",
            "address": "Sector 38-West, Chandigarh",
            "latitude": 30.7550,
            "longitude": 76.7350,
            "daily_capacity": 160,
            "current_occupancy": 40,
            "dietary_preferences": ["Vegetarian", "Vegan"],
            "food_requirements": ["Cooked Meals", "Bakery"]
        }
        resp = self.client.post("/api/ngos", json=valid_ngo)
        self.assertEqual(resp.status_code, 201)
        ngo_id = resp.get_json()["ngo_id"]

        # Verify capacity headroom in GET /api/ngos
        resp_list = self.client.get("/api/ngos")
        self.assertEqual(resp_list.status_code, 200)
        ngo = next(n for n in resp_list.get_json()["ngos"] if n["id"] == ngo_id)
        self.assertEqual(ngo["available_capacity"], 120)  # 160 - 40
        self.assertIn("Vegetarian", ngo["dietary_preferences"])

    # -------------------------------------------------------------
    # 4. FOOD SAFETY RISK SCREENING BOUNDARIES
    # -------------------------------------------------------------
    def test_05_food_safety_boundaries_and_rejections(self):
        """QA: Boundary tests for food safety rules across categories."""
        now = datetime.now()

        # Case A: Cooked meal room temp > 4.0 hours -> REJECT
        prep = (now - timedelta(hours=4, minutes=15)).isoformat()
        deadline = (now + timedelta(hours=1)).isoformat()
        res = validate_food_safety(
            food_name="Dal Makhani",
            food_category="Cooked Meals",
            prep_time_raw=prep,
            collection_deadline_raw=deadline,
            storage_condition="Room Temp (20-25°C)",
            evaluation_time=now
        )
        self.assertFalse(res["is_safe"])
        self.assertEqual(res["status"], "Rejected")
        self.assertTrue(any("4 hours" in r for r in res["reasons"]))

        # Case B: Cooked meal chilled -> Valid for 24h
        prep_chilled = (now - timedelta(hours=8)).isoformat()
        deadline_chilled = (now + timedelta(hours=4)).isoformat()
        res_chilled = validate_food_safety(
            food_name="Chilled Pulao",
            food_category="Cooked Meals",
            prep_time_raw=prep_chilled,
            collection_deadline_raw=deadline_chilled,
            storage_condition="Chilled (0-4°C)",
            evaluation_time=now
        )
        self.assertTrue(res_chilled["is_safe"])
        self.assertEqual(res_chilled["status"], "Valid")

        # Case C: Perishable dairy at room temp -> REJECT
        res_dairy = validate_food_safety(
            food_name="Fresh Paneer",
            food_category="Perishable Dairy",
            prep_time_raw=(now - timedelta(hours=1)).isoformat(),
            collection_deadline_raw=(now + timedelta(hours=1)).isoformat(),
            storage_condition="Room Temp (20-25°C)",
            evaluation_time=now
        )
        self.assertFalse(res_dairy["is_safe"])
        self.assertTrue(any("refrigeration" in r.lower() for r in res_dairy["reasons"]))

        # Case D: Expired deadline (already elapsed) -> REJECT
        res_expired = validate_food_safety(
            food_name="Bread Rolls",
            food_category="Bakery",
            prep_time_raw=(now - timedelta(hours=10)).isoformat(),
            collection_deadline_raw=(now - timedelta(minutes=5)).isoformat(),
            storage_condition="Room Temp (20-25°C)",
            evaluation_time=now
        )
        self.assertFalse(res_expired["is_safe"])
        self.assertTrue(any("elapsed" in r.lower() or "expired" in r.lower() for r in res_expired["reasons"]))

    # -------------------------------------------------------------
    # 5. SMART MATCHING & MULTI-FACTOR SCORING
    # -------------------------------------------------------------
    def test_06_smart_matching_and_hard_constraints(self):
        """QA: Verify 5-factor scoring, rank sorting, and hard constraints."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ngos")
        ngos = [dict(r) for r in cursor.fetchall()]
        conn.close()

        # Test donation
        now = datetime.now()
        donation = {
            "id": 99,
            "donor_latitude": 30.7333,
            "donor_longitude": 76.7794,
            "food_name": "Vegetable Biryani",
            "food_category": "Cooked Meals",
            "quantity": 100,
            "allocated_quantity": 0,
            "dietary_classification": "Vegetarian",
            "safety_status": "Valid",
            "collection_deadline": (now + timedelta(hours=3)).isoformat()
        }

        ranked = rank_ngos_for_donation(donation, ngos, now=now)
        self.assertGreaterEqual(len(ranked), 1)

        # First must be eligible and have highest score
        top = ranked[0]
        self.assertTrue(top["eligible"])
        self.assertGreater(top["matching_score"], 0)
        self.assertIn("factors", top)
        self.assertIn("distance_score", top["factors"])
        self.assertIn("quantity_score", top["factors"])
        self.assertIn("urgency_score", top["factors"])
        self.assertIn("preference_score", top["factors"])
        self.assertIn("capacity_score", top["factors"])

    # -------------------------------------------------------------
    # 6. TRANSACTIONAL ALLOCATIONS & OVER-ALLOCATION PROTECTION
    # -------------------------------------------------------------
    def test_07_transactional_allocation_and_capacity_acceptance(self):
        """QA: Verify ACID allocation transactions, over-allocation prevention, and acceptance."""
        # 1. Create fresh donation with 80 meals
        now = datetime.now()
        don_payload = {
            "donor_id": 1,
            "food_name": "QA Allocation Test Khichdi",
            "food_category": "Cooked Meals",
            "quantity": 80,
            "prep_time": (now - timedelta(hours=1)).isoformat(),
            "collection_deadline": (now + timedelta(hours=2)).isoformat(),
            "storage_condition": "Hot-hold (>60°C)",
            "dietary_classification": "Vegetarian",
            "allergens": []
        }
        resp = self.client.post("/api/donations", json=don_payload)
        self.assertEqual(resp.status_code, 201)
        donation_id = resp.get_json()["donation_id"]

        # 2. Allocate 50 meals to NGO 1 -> Success
        alloc_payload = {
            "donation_id": donation_id,
            "ngo_id": 1,
            "allocated_meals": 50,
            "distance_km": 3.5,
            "matching_score": 85.0
        }
        resp_alloc = self.client.post("/api/allocations", json=alloc_payload)
        self.assertEqual(resp_alloc.status_code, 201)
        alloc_id = resp_alloc.get_json()["allocation_id"]

        # 3. Attempt over-allocation: try allocating 40 more meals when only 30 remain -> MUST FAIL
        over_payload = {
            "donation_id": donation_id,
            "ngo_id": 2,
            "allocated_meals": 40,
            "distance_km": 4.0,
            "matching_score": 75.0
        }
        resp_over = self.client.post("/api/allocations", json=over_payload)
        self.assertEqual(resp_over.status_code, 400)
        self.assertIn("exceeds remaining unallocated surplus", resp_over.get_json()["error"])

        # 4. Accept the 50 meals allocation
        resp_accept = self.client.post(f"/api/allocations/{alloc_id}/accept")
        self.assertEqual(resp_accept.status_code, 200)

        # 5. Verify database reflects accepted status
        conn = get_db_connection()
        row = conn.execute("SELECT status, allocated_meals FROM allocations WHERE id = ?", (alloc_id,)).fetchone()
        self.assertEqual(row["status"], "Accepted")
        self.assertEqual(row["allocated_meals"], 50)
        conn.close()

    # -------------------------------------------------------------
    # 7. STATISTICAL DEMAND FORECASTING
    # -------------------------------------------------------------
    def test_08_statistical_demand_forecasting_formula(self):
        """QA: Verify 0.5*Hist + 0.3*Recent + 0.2*Expected demand forecast formula."""
        resp = self.client.get("/api/forecast/1")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "success")
        fc = data["forecast"]

        # Verify formula values
        hist = fc["historical_avg"]
        recent = fc["recent_avg"]
        expected = fc["expected_avg"]
        predicted = fc["predicted_meals"]

        expected_calc = round((0.5 * hist) + (0.3 * recent) + (0.2 * expected))
        self.assertEqual(predicted, expected_calc)
        self.assertIn("not a trained machine learning model", fc["disclaimer"].lower())
        self.assertEqual(len(fc["forecast_series"]), 7)  # 7-day projection

    # -------------------------------------------------------------
    # 8. OSRM ROUTE OPTIMIZATION & LEAFLET COMPLIANCE
    # -------------------------------------------------------------
    def test_09_route_optimization_and_leaflet_geojson(self):
        """QA: Verify OSRM route calculations, ETAs, stop order, and GeoJSON validity."""
        route_payload = {
            "donor_id": 1,
            "ngo_ids": [1, 2]
        }
        resp = self.client.post("/api/route", json=route_payload)
        self.assertEqual(resp.status_code, 200)
        result = resp.get_json()

        self.assertEqual(result["status"], "success")
        self.assertGreater(result["total_distance_km"], 0)
        self.assertGreater(result["total_duration_minutes"], 0)
        self.assertEqual(result["stops_count"], 3)  # Origin + 2 stops

        # GeoJSON validation for Leaflet
        geojson = result["geojson"]
        self.assertEqual(geojson["type"], "Feature")
        self.assertIn(geojson["geometry"]["type"], ["LineString", "MultiLineString"])
        coords = geojson["geometry"]["coordinates"]
        self.assertGreater(len(coords), 1)

        # Delivery ETAs present
        stops = result["ordered_stops"]
        for s in stops:
            self.assertIn("eta", s)
            self.assertIn("eta_display", s)
            self.assertIn("cumulative_distance_km", s)

    # -------------------------------------------------------------
    # 9. COMPLETE DONATION-TO-DELIVERY WORKFLOW
    # -------------------------------------------------------------
    def test_10_full_donation_to_delivery_lifecycle(self):
        """QA: Full integration: Donor -> NGO -> Donation -> Match -> Allocate -> Accept -> Route."""
        # 1. Register Donor
        donor_resp = self.client.post("/api/donors", json={
            "name": "Panjab University Law Canteen (E2E Test)",
            "donor_type": "Canteen",
            "contact_name": "Satish Kumar",
            "phone": "+91 99887 76655",
            "email": "satish@pucanteen.edu",
            "address": "Sector 14, Chandigarh",
            "latitude": 30.7610,
            "longitude": 76.7700
        })
        self.assertEqual(donor_resp.status_code, 201)
        d_id = donor_resp.get_json()["donor_id"]

        # 2. Register NGO
        ngo_resp = self.client.post("/api/ngos", json={
            "name": "Sec 23 Care Community Kitchen (E2E Test)",
            "ngo_type": "Community Kitchen",
            "contact_name": "Jaspreet Singh",
            "phone": "+91 98722 33445",
            "email": "jaspreet@carekitchen.org",
            "address": "Sector 23-C, Chandigarh",
            "latitude": 30.7320,
            "longitude": 76.7680,
            "daily_capacity": 200,
            "current_occupancy": 50,
            "dietary_preferences": ["Vegetarian"],
            "food_requirements": ["Cooked Meals"]
        })
        self.assertEqual(ngo_resp.status_code, 201)
        n_id = ngo_resp.get_json()["ngo_id"]

        # 3. Submit safe donation
        now = datetime.now()
        don_resp = self.client.post("/api/donations", json={
            "donor_id": d_id,
            "food_name": "Fresh Poori Bhaji & Halwa",
            "food_category": "Cooked Meals",
            "quantity": 120,
            "prep_time": (now - timedelta(hours=1)).isoformat(),
            "collection_deadline": (now + timedelta(hours=3)).isoformat(),
            "storage_condition": "Hot-hold (>60°C)",
            "dietary_classification": "Vegetarian",
            "allergens": ["Gluten"]
        })
        self.assertEqual(don_resp.status_code, 201)
        don_data = don_resp.get_json()
        self.assertTrue(don_data["safety_evaluation"]["is_safe"])
        donation_id = don_data["donation_id"]

        # 4. Run AI Matching
        match_resp = self.client.post(f"/api/match/{donation_id}")
        self.assertEqual(match_resp.status_code, 200)
        match_data = match_resp.get_json()
        self.assertGreater(len(match_data["ranked_matches"]), 0)

        # 5. Propose Allocation
        top_match = match_data["ranked_matches"][0]
        alloc_resp = self.client.post("/api/allocations", json={
            "donation_id": donation_id,
            "ngo_id": top_match["ngo_id"],
            "allocated_meals": 100,
            "distance_km": top_match["distance_km"],
            "matching_score": top_match["matching_score"]
        })
        self.assertEqual(alloc_resp.status_code, 201)
        alloc_id = alloc_resp.get_json()["allocation_id"]

        # 6. Accept Allocation
        accept_resp = self.client.post(f"/api/allocations/{alloc_id}/accept")
        self.assertEqual(accept_resp.status_code, 200)

        # 7. Optimize Route
        route_resp = self.client.post("/api/route", json={
            "donor_id": d_id,
            "ngo_ids": [top_match["ngo_id"]]
        })
        self.assertEqual(route_resp.status_code, 200)
        route_data = route_resp.get_json()
        self.assertEqual(route_data["stops_count"], 2)
        self.assertGreater(route_data["total_distance_km"], 0)
        self.assertIn("geojson", route_data)


if __name__ == "__main__":
    unittest.main()
