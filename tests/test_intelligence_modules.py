import unittest
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Ensure root directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import Config
from backend.matching import evaluate_ngo_match, rank_ngos_for_donation, compute_multi_ngo_split, haversine_distance
from backend.forecasting import calculate_statistical_demand_forecast
from backend.food_safety import validate_food_safety
from database import get_db_connection, save_allocation_transaction, accept_allocation_transaction
from data.seed_data import seed_database

class TestFoodLinkIntelligenceModules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_database()

    # =========================================================================
    # 1. WEIGHTED DONOR-RECIPIENT MATCHING & HARD CONSTRAINTS
    # =========================================================================
    def test_01_matching_weights_sum_to_one(self):
        """Ensure mathematical integrity: matching weights must sum to exactly 1.0."""
        total_weight = (
            Config.MATCH_WEIGHT_DISTANCE +
            Config.MATCH_WEIGHT_QUANTITY +
            Config.MATCH_WEIGHT_URGENCY +
            Config.MATCH_WEIGHT_DIETARY +
            Config.MATCH_WEIGHT_CAPACITY
        )
        self.assertAlmostEqual(total_weight, 1.0, places=4)

    def test_02_matching_score_normalization(self):
        """Verify that individual factor scores and final scores are normalized within [0, 100]."""
        now = datetime.now()
        donation = {
            "id": 1,
            "donor_latitude": 30.7398,
            "donor_longitude": 76.7827,
            "food_name": "Vegetable Pulao",
            "food_category": "Cooked Meals",
            "quantity": 80,
            "allocated_quantity": 0,
            "dietary_classification": "Vegetarian",
            "safety_status": "Valid",
            "collection_deadline": (now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
        }
        ngo = {
            "id": 1,
            "name": "Nearby Seva Kitchen",
            "latitude": 30.7300,
            "longitude": 76.7800,
            "daily_capacity": 200,
            "current_occupancy": 50,
            "dietary_preferences": json.dumps(["Vegetarian", "Any"]),
            "food_requirements": json.dumps(["Cooked Meals"])
        }
        res = evaluate_ngo_match(donation, ngo, now=now)
        self.assertTrue(res["eligible"])
        self.assertGreaterEqual(res["matching_score"], 0.0)
        self.assertLessEqual(res["matching_score"], 100.0)
        for factor_name, score_val in res["factors"].items():
            self.assertGreaterEqual(score_val, 0.0, f"{factor_name} was < 0")
            self.assertLessEqual(score_val, 100.0, f"{factor_name} was > 100")

    def test_03_hard_constraint_dietary_mismatch_rejection(self):
        """Non-Veg donation must be disqualified when candidate NGO only accepts Vegetarian or Vegan."""
        now = datetime.now()
        non_veg_donation = {
            "id": 2,
            "donor_latitude": 30.7398,
            "donor_longitude": 76.7827,
            "food_name": "Chicken Curry",
            "food_category": "Cooked Meals",
            "quantity": 50,
            "allocated_quantity": 0,
            "dietary_classification": "Non-Veg",
            "safety_status": "Valid",
            "collection_deadline": (now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
        }
        strict_veg_ngo = {
            "id": 2,
            "name": "Strict Veg Ashram",
            "latitude": 30.7350,
            "longitude": 76.7810,
            "daily_capacity": 150,
            "current_occupancy": 30,
            "dietary_preferences": json.dumps(["Vegetarian"]),
            "food_requirements": json.dumps(["Cooked Meals"])
        }
        res = evaluate_ngo_match(non_veg_donation, strict_veg_ngo, now=now)
        self.assertFalse(res["eligible"])
        self.assertEqual(res["matching_score"], 0.0)
        self.assertTrue(any("dietary" in r.lower() for r in res["rejection_reasons"]))

    def test_04_hard_constraint_full_capacity_rejection(self):
        """Candidate NGO with zero remaining capacity headroom must be rejected before scoring."""
        now = datetime.now()
        donation = {
            "id": 3,
            "donor_latitude": 30.7398,
            "donor_longitude": 76.7827,
            "food_name": "Dal & Rice",
            "food_category": "Cooked Meals",
            "quantity": 40,
            "allocated_quantity": 0,
            "dietary_classification": "Vegetarian",
            "safety_status": "Valid",
            "collection_deadline": (now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
        }
        full_ngo = {
            "id": 3,
            "name": "Full Shelter",
            "latitude": 30.7350,
            "longitude": 76.7810,
            "daily_capacity": 100,
            "current_occupancy": 100, # 0 headroom
            "dietary_preferences": json.dumps(["Any"]),
            "food_requirements": json.dumps(["Cooked Meals"])
        }
        res = evaluate_ngo_match(donation, full_ngo, now=now)
        self.assertFalse(res["eligible"])
        self.assertTrue(any("full capacity" in r.lower() for r in res["rejection_reasons"]))

    # =========================================================================
    # 2. STATISTICAL DEMAND FORECASTING (EXPLICITLY DISTINGUISHED FROM ML)
    # =========================================================================
    def test_05_statistical_demand_forecasting_formula(self):
        """Verify baseline formula: Prediction = (0.5 * Hist) + (0.3 * Recent) + (0.2 * Expected)."""
        history = [
            {"date": "2026-10-01", "meals_demanded": 100},
            {"date": "2026-10-02", "meals_demanded": 100},
            {"date": "2026-10-03", "meals_demanded": 100},
            {"date": "2026-10-04", "meals_demanded": 200},
            {"date": "2026-10-05", "meals_demanded": 200},
            {"date": "2026-10-06", "meals_demanded": 200},
            {"date": "2026-10-07", "meals_demanded": 200}
        ]
        # Total days: 7. Sum = 3*100 + 4*200 = 1100. Hist avg = 1100 / 7 = 157.1428
        # Recent 7 days slice = all 7 days = 157.1428
        # Expected override = 180.0
        # Expected prediction = (0.5 * 157.1428) + (0.3 * 157.1428) + (0.2 * 180.0) = 125.714 + 36.0 = 161.714 -> 162
        res = calculate_statistical_demand_forecast(history, expected_override=180.0)
        self.assertEqual(res["predicted_meals"], 162)
        self.assertIn("disclaimer", res)
        # Ensure clearly distinguished from ML
        self.assertIn("statistical", res["disclaimer"].lower())
        self.assertIn("not a trained machine learning model", res["disclaimer"].lower())

    def test_06_forecasting_trend_classification(self):
        """Verify trend indicator identifies increasing, decreasing, or stable patterns."""
        # Increasing trend
        increasing_records = [{"date": f"2026-10-{i:02d}", "meals_demanded": 50 if i < 10 else 120} for i in range(1, 18)]
        res_inc = calculate_statistical_demand_forecast(increasing_records)
        self.assertEqual(res_inc["trend"], "Increasing Demand")
        self.assertGreater(res_inc["trend_percentage"], 5.0)

        # Decreasing trend
        decreasing_records = [{"date": f"2026-10-{i:02d}", "meals_demanded": 150 if i < 10 else 60} for i in range(1, 18)]
        res_dec = calculate_statistical_demand_forecast(decreasing_records)
        self.assertEqual(res_dec["trend"], "Decreasing Demand")
        self.assertLess(res_dec["trend_percentage"], -5.0)

    # =========================================================================
    # 3. FOOD SAFETY VALIDATION RULES & TEMPERATURE SCREENING
    # =========================================================================
    def test_07_food_safety_cooked_meals_temperature_danger_zone(self):
        """Cooked meals at room temperature exceeding 4 hours must fail validation."""
        now = datetime.now()
        prep_time = (now - timedelta(hours=4, minutes=30)).strftime("%Y-%m-%dT%H:%M")
        deadline = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")

        res = validate_food_safety(
            food_name="Buffet Rice & Dal",
            food_category="Cooked Meals",
            prep_time_raw=prep_time,
            collection_deadline_raw=deadline,
            storage_condition="Room Temp (20-25°C)",
            allergens=[]
        )
        self.assertFalse(res["is_safe"])
        self.assertEqual(res["status"], "Rejected")
        self.assertTrue(any("temperature danger zone" in r.lower() or "4 hours" in r.lower() for r in res["reasons"]))

    def test_08_food_safety_perishable_dairy_refrigeration_requirement(self):
        """Perishable dairy stored at room temperature or hot-holding must be rejected."""
        now = datetime.now()
        prep_time = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        deadline = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")

        res_dairy_hot = validate_food_safety(
            food_name="Fresh Paneer Cubes",
            food_category="Perishable Dairy",
            prep_time_raw=prep_time,
            collection_deadline_raw=deadline,
            storage_condition="Room Temp (20-25°C)",
            allergens=["Dairy"]
        )
        self.assertFalse(res_dairy_hot["is_safe"])
        self.assertTrue(any("refrigeration" in r.lower() or "dairy" in r.lower() for r in res_dairy_hot["reasons"]))

        # Dairy chilled at 0-4°C passes
        res_dairy_chilled = validate_food_safety(
            food_name="Fresh Paneer Cubes",
            food_category="Perishable Dairy",
            prep_time_raw=prep_time,
            collection_deadline_raw=deadline,
            storage_condition="Chilled (0-4°C)",
            allergens=["Dairy"]
        )
        self.assertTrue(res_dairy_chilled["is_safe"])
        self.assertEqual(res_dairy_chilled["status"], "Valid")

    def test_09_food_safety_chronological_deadline_inversion(self):
        """Deadline prior to preparation time must be rejected."""
        now = datetime.now()
        prep_time = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        deadline = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")

        res = validate_food_safety(
            food_name="Baked Goods",
            food_category="Bakery",
            prep_time_raw=prep_time,
            collection_deadline_raw=deadline,
            storage_condition="Room Temp (20-25°C)",
            allergens=[]
        )
        self.assertFalse(res["is_safe"])
        self.assertTrue(any("chronologically" in r.lower() for r in res["reasons"]))

    # =========================================================================
    # 4. MULTI-NGO ALLOCATION & ZERO-OVER-ALLOCATION GUARANTEE
    # =========================================================================
    def test_10_multi_ngo_allocation_split_within_surplus(self):
        """Verify that multi-NGO allocation distributes large surplus without exceeding total available quantity."""
        donation = {
            "id": 100,
            "food_name": "Large Campus Canteen Batch",
            "quantity": 250,
            "allocated_quantity": 0
        }
        # Candidate NGOs with limited individual capacities
        ranked_candidates = [
            {"ngo_id": 1, "ngo_name": "Kitchen Alpha", "eligible": True, "available_capacity": 100, "matching_score": 95.0, "distance_km": 2.1},
            {"ngo_id": 2, "ngo_name": "Shelter Beta", "eligible": True, "available_capacity": 90, "matching_score": 88.0, "distance_km": 4.5},
            {"ngo_id": 3, "ngo_name": "Ashram Gamma", "eligible": True, "available_capacity": 120, "matching_score": 78.0, "distance_km": 6.8},
            {"ngo_id": 4, "ngo_name": "Ineligible Delta", "eligible": False, "available_capacity": 80, "matching_score": 0.0, "distance_km": 12.0}
        ]

        plan = compute_multi_ngo_split(donation, ranked_candidates)
        self.assertEqual(plan["status"], "success")
        self.assertEqual(plan["total_available"], 250)
        self.assertEqual(plan["total_allocated"], 250)
        self.assertEqual(plan["remaining_unallocated"], 0)

        # NGO 1 gets 100, NGO 2 gets 90, NGO 3 gets 60 (remaining: 250 - 190 = 60). Ineligible NGO 4 gets 0.
        dist = plan["distribution_plan"]
        self.assertEqual(len(dist), 3)
        self.assertEqual(dist[0]["allocated_meals"], 100)
        self.assertEqual(dist[1]["allocated_meals"], 90)
        self.assertEqual(dist[2]["allocated_meals"], 60)

        # Invariant: Sum of allocated meals must strictly equal total_allocated and not exceed available
        total_sum = sum(d["allocated_meals"] for d in dist)
        self.assertEqual(total_sum, 250)
        self.assertLessEqual(total_sum, donation["quantity"])

    def test_11_database_transaction_prevents_over_allocation(self):
        """Verify SQLite ACID transaction blocks race condition or over-allocation attempts."""
        conn = get_db_connection()
        don_row = conn.execute("SELECT id, quantity, allocated_quantity FROM donations WHERE safety_status = 'Valid' LIMIT 1").fetchone()
        conn.close()

        don_id = don_row["id"]
        unallocated = don_row["quantity"] - don_row["allocated_quantity"]

        # Attempting to allocate surplus + 10 MUST raise ValueError and abort transaction
        with self.assertRaises(ValueError) as ctx:
            save_allocation_transaction(
                donation_id=don_id,
                ngo_id=1,
                meals_to_allocate=unallocated + 10,
                distance_km=2.0,
                matching_score=85.0
            )
        self.assertIn("exceeds remaining", str(ctx.exception).lower())

if __name__ == "__main__":
    unittest.main()
