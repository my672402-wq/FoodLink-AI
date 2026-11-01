import unittest
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app
from database import get_db_connection, init_db, save_allocation_transaction, accept_allocation_transaction
from backend.food_safety import validate_food_safety
from backend.matching import evaluate_ngo_match, rank_ngos_for_donation, haversine_distance
from backend.forecasting import calculate_statistical_demand_forecast
from backend.routing import optimize_delivery_route
from data.seed_data import seed_database

class TestFoodLinkAI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reset and seed database before running tests
        seed_database()
        cls.client = app.test_client()

    def test_01_food_safety_validation(self):
        """Verify that food safety correctly accepts safe donations and rejects unsafe ones."""
        now = datetime.now()
        
        # Valid Hot-hold Cooked meal within safe window
        safe_prep = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        safe_deadline = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        res_safe = validate_food_safety(
            food_name="Fresh Khichdi",
            food_category="Cooked Meals",
            prep_time_raw=safe_prep,
            collection_deadline_raw=safe_deadline,
            storage_condition="Hot-hold (>60°C)",
            allergens=["Dairy"]
        )
        self.assertTrue(res_safe["is_safe"])
        self.assertEqual(res_safe["status"], "Valid")
        self.assertEqual(len(res_safe["reasons"]), 0)

        # Unsafe: Cooked meal stored at room temp exceeding 4 hour window
        unsafe_prep = (now - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M")
        unsafe_deadline = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        res_unsafe = validate_food_safety(
            food_name="Old Biryani",
            food_category="Cooked Meals",
            prep_time_raw=unsafe_prep,
            collection_deadline_raw=unsafe_deadline,
            storage_condition="Room Temp (20-25°C)",
            allergens=[]
        )
        self.assertFalse(res_unsafe["is_safe"])
        self.assertEqual(res_unsafe["status"], "Rejected")
        self.assertTrue(any("safe window" in r.lower() or "danger" in r.lower() for r in res_unsafe["reasons"]))

        # Unsafe: Expired collection deadline
        expired_deadline = (now - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M")
        res_expired = validate_food_safety(
            food_name="Expired Bread",
            food_category="Bakery",
            prep_time_raw=safe_prep,
            collection_deadline_raw=expired_deadline,
            storage_condition="Room Temp (20-25°C)",
            allergens=[]
        )
        self.assertFalse(res_expired["is_safe"])
        self.assertTrue(any("elapsed" in r.lower() for r in res_expired["reasons"]))

    def test_02_haversine_distance(self):
        """Verify distance calculation between Chandigarh Sectors."""
        # Sector 17 (30.7398, 76.7827) to Sector 35 (30.7230, 76.7640) ~ 2.6 km
        dist = haversine_distance(30.7398, 76.7827, 30.7230, 76.7640)
        self.assertGreater(dist, 1.5)
        self.assertLess(dist, 4.0)

    def test_03_matching_engine_and_hard_constraints(self):
        """Verify matching score calculations and rejection of incompatible recipients."""
        now = datetime.now()
        donation = {
            "id": 1,
            "donor_latitude": 30.7600,
            "donor_longitude": 76.7684,
            "food_name": "Dal & Rice",
            "food_category": "Cooked Meals",
            "quantity": 100,
            "allocated_quantity": 0,
            "dietary_classification": "Non-Veg",
            "safety_status": "Valid",
            "collection_deadline": (now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
        }

        # Strict Vegetarian NGO must reject Non-Veg donation
        veg_ngo = {
            "id": 10,
            "name": "Strict Veg Ashram",
            "latitude": 30.7500,
            "longitude": 76.7700,
            "daily_capacity": 200,
            "current_occupancy": 50,
            "dietary_preferences": json.dumps(["Vegetarian"]),
            "food_requirements": json.dumps(["Cooked Meals"])
        }
        res_incompatible = evaluate_ngo_match(donation, veg_ngo, now=now)
        self.assertFalse(res_incompatible["eligible"])
        self.assertTrue(any("dietary" in r.lower() for r in res_incompatible["rejection_reasons"]))

        # Compatible NGO accepts
        any_ngo = {
            "id": 11,
            "name": "Universal Food Kitchen",
            "latitude": 30.7550,
            "longitude": 76.7690,
            "daily_capacity": 200,
            "current_occupancy": 50,
            "dietary_preferences": json.dumps(["Any"]),
            "food_requirements": json.dumps(["Cooked Meals"])
        }
        res_compatible = evaluate_ngo_match(donation, any_ngo, now=now)
        self.assertTrue(res_compatible["eligible"])
        self.assertGreater(res_compatible["matching_score"], 60.0)
        self.assertIn("factors", res_compatible)
        self.assertEqual(res_compatible["proposed_meals"], 100)

    def test_04_demand_forecasting_formula(self):
        """Verify statistical demand forecast calculation using 0.5*Hist + 0.3*Recent + 0.2*Expected."""
        # Test synthetic records: 10 days of 100 meals, 7 days of 150 meals
        sample_records = [{"date": f"2026-10-{i:02d}", "meals_demanded": 100} for i in range(1, 11)]
        sample_records += [{"date": f"2026-10-{i:02d}", "meals_demanded": 150} for i in range(11, 18)]
        
        hist_avg = (100 * 10 + 150 * 7) / 17.0 # ~ 120.588
        recent_avg = 150.0
        expected = 140.0
        
        expected_pred = (0.5 * hist_avg) + (0.3 * recent_avg) + (0.2 * expected) # ~ 60.29 + 45.0 + 28.0 = 133.29 -> 133
        
        res = calculate_statistical_demand_forecast(sample_records, expected_override=expected)
        self.assertEqual(res["predicted_meals"], round(expected_pred))
        self.assertEqual(res["trend"], "Increasing Demand")
        self.assertIn("disclaimer", res)

    def test_05_allocation_transaction_constraints(self):
        """Verify that transactions prevent over-allocating meals beyond surplus."""
        conn = get_db_connection()
        # Find donation 1
        row = conn.execute("SELECT id, quantity, allocated_quantity FROM donations WHERE id = 1").fetchone()
        conn.close()
        
        surplus = row["quantity"] - row["allocated_quantity"]
        self.assertGreater(surplus, 0)

        # Trying to allocate more than surplus MUST fail with ValueError
        with self.assertRaises(ValueError):
            save_allocation_transaction(donation_id=1, ngo_id=1, meals_to_allocate=surplus + 50)

        # Allocating exact or smaller quantity succeeds
        alloc_id = save_allocation_transaction(donation_id=1, ngo_id=1, meals_to_allocate=10, distance_km=2.5, matching_score=88.0)
        self.assertIsInstance(alloc_id, int)

        # Accept the allocation
        accepted = accept_allocation_transaction(alloc_id)
        self.assertTrue(accepted)

    def test_06_route_optimization(self):
        """Verify route optimization orders stops and outputs GeoJSON geometry."""
        donor = {
            "id": 1,
            "name": "Donor Central",
            "latitude": 30.7600,
            "longitude": 76.7684,
            "collection_deadline": (datetime.now() + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
        }
        stops = [
            {"id": 1, "name": "Stop A", "latitude": 30.7280, "longitude": 76.7780, "meals_allocated": 30},
            {"id": 2, "name": "Stop B", "latitude": 30.7046, "longitude": 76.7179, "meals_allocated": 40}
        ]

        route_res = optimize_delivery_route(donor, stops)
        self.assertEqual(route_res["status"], "success")
        self.assertEqual(len(route_res["ordered_stops"]), 3) # Donor + 2 stops
        self.assertIn("geojson", route_res)
        self.assertIn("total_distance_km", route_res)
        self.assertIn("total_duration_minutes", route_res)

    def test_07_api_health_and_dashboard(self):
        """Verify Flask API endpoints."""
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertTrue(data["database_connected"])

        res_dash = self.client.get("/api/dashboard")
        self.assertEqual(res_dash.status_code, 200)
        dash_data = res_dash.get_json()
        self.assertEqual(dash_data["status"], "success")
        self.assertIn("metrics", dash_data)
        self.assertGreater(dash_data["metrics"]["total_donations"], 0)

    def test_08_api_matching_and_forecast(self):
        """Verify /api/match/<id> and /api/forecast/<id> endpoints."""
        res_match = self.client.post("/api/match/1")
        self.assertEqual(res_match.status_code, 200)
        match_data = res_match.get_json()
        self.assertIn("ranked_matches", match_data)
        self.assertGreater(len(match_data["ranked_matches"]), 0)
        self.assertIn("ai_explanation", match_data)

        res_fc = self.client.get("/api/forecast/1")
        self.assertEqual(res_fc.status_code, 200)
        fc_data = res_fc.get_json()
        self.assertIn("forecast", fc_data)
        self.assertIn("predicted_meals", fc_data["forecast"])

if __name__ == "__main__":
    unittest.main()
