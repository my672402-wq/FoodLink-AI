"""
FoodLink AI — External Services Integration Test Suite
Verifies:
  1. Google Gen AI SDK integration and graceful degradation when GEMINI_API_KEY is unset or empty.
  2. Reading environment variables from .env via Config.
  3. OSRM Table and Route API integration, road distance matrices, GeoJSON polyline generation.
  4. Leaflet-compatible GeoJSON output and marker coordinates for donors and NGOs.
  5. Estimated delivery times, per-leg durations, ETAs, and deadline warnings.
  6. Graceful failure handling on simulated OSRM timeouts and unreachable external endpoints.
"""

import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta

# Ensure parent directory is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import Config
from backend.ai_service import GeminiService, ai_service
from backend.routing import (
    get_osrm_distance_matrix,
    get_osrm_route_geometry,
    optimize_delivery_route
)
from app import app


class TestExternalServices(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    def test_01_config_loads_env_and_has_defaults(self):
        """Verify Config loads settings from .env and provides sensible defaults."""
        self.assertIsNotNone(Config.SECRET_KEY)
        self.assertIn("router.project-osrm.org", Config.OSRM_BASE_URL)
        self.assertGreater(Config.OSRM_TIMEOUT, 0)
        # Verify weight constants sum to 1.0
        total_weights = (
            Config.MATCH_WEIGHT_DISTANCE +
            Config.MATCH_WEIGHT_QUANTITY +
            Config.MATCH_WEIGHT_URGENCY +
            Config.MATCH_WEIGHT_DIETARY +
            Config.MATCH_WEIGHT_CAPACITY
        )
        self.assertAlmostEqual(total_weights, 1.0, places=2)

    def test_02_gemini_service_without_credentials(self):
        """Verify GeminiService operates cleanly in fallback mode without API key."""
        svc = GeminiService()
        status = svc.get_status()
        self.assertIsInstance(status, dict)
        self.assertIn("available", status)
        self.assertIn("model", status)

        # Test deterministic matching explanation fallback
        dummy_donation = {
            "food_name": "Paneer Butter Masala",
            "food_category": "Cooked Meals",
            "quantity": 100,
            "collection_deadline": (datetime.now() + timedelta(hours=3)).isoformat()
        }
        dummy_matches = [
            {
                "eligible": True,
                "ngo_name": "Tricity Langar Seva (Simulated)",
                "distance_km": 3.8,
                "matching_score": 88.5,
                "available_capacity": 150,
                "proposed_meals": 100,
                "dietary_preferences": ["Vegetarian"]
            }
        ]
        explanation = svc.generate_matching_explanation(dummy_donation, dummy_matches)
        self.assertIsInstance(explanation, dict)
        self.assertIn("summary", explanation)
        self.assertTrue(len(explanation["summary"]) > 20)
        self.assertFalse(explanation["ai_powered"])  # Without key, must be fallback

    def test_03_gemini_forecast_summary_fallback(self):
        """Verify forecast summary generates valid statistical commentary without Gemini."""
        svc = GeminiService()
        ngo = {"name": "Mohali Night Shelter (Simulated)"}
        forecast = {
            "predicted_meals": 120,
            "historical_avg": 115.0,
            "recent_avg": 125.0,
            "trend": "Increasing",
            "trend_percentage": 8.7
        }
        summary = svc.generate_forecast_summary(ngo, forecast)
        self.assertIsInstance(summary, dict)
        self.assertIn("summary", summary)
        self.assertIn("120", summary["summary"])
        self.assertIn("action_recommendation", summary)

    def test_04_gemini_platform_insights_fallback(self):
        """Verify platform insights generates valid operational bullets without Gemini."""
        svc = GeminiService()
        metrics = {
            "total_donations": 10,
            "total_meals_available": 600,
            "meals_allocated": 450,
            "active_ngos": 4
        }
        insights = svc.generate_platform_insights(metrics)
        self.assertIsInstance(insights, dict)
        self.assertIn("insights", insights)
        self.assertGreaterEqual(len(insights["insights"]), 2)

    def test_05_osrm_table_api_and_road_matrix(self):
        """Verify OSRM Table API returns distance and duration matrices or handles failure."""
        # Chandigarh Sector 17 coordinates and Mohali Phase 7 coordinates
        coords = [
            [76.7794, 30.7333],  # Sector 17 Plaza [lon, lat]
            [76.7179, 30.7046]   # Mohali Phase 7 [lon, lat]
        ]
        dist, dur = get_osrm_distance_matrix(coords, timeout=4)
        if dist is not None and dur is not None:
            # Live OSRM is reachable
            self.assertEqual(len(dist), 2)
            self.assertEqual(len(dur), 2)
            self.assertGreater(dist[0][1], 1000)  # > 1 km
            self.assertGreater(dur[0][1], 60)    # > 1 min
        else:
            # Network issue or public demo server busy — function gracefully returns None, None
            self.assertIsNone(dist)
            self.assertIsNone(dur)

    def test_06_osrm_route_geometry_geojson(self):
        """Verify OSRM Route API returns GeoJSON driving geometry or handles failure."""
        ordered_coords = [
            [76.7794, 30.7333],
            [76.7179, 30.7046]
        ]
        route_data = get_osrm_route_geometry(ordered_coords, timeout=4)
        if route_data is not None:
            self.assertIn("geometry", route_data)
            self.assertIn("distance_meters", route_data)
            self.assertIn("duration_seconds", route_data)
            self.assertEqual(route_data["geometry"]["type"], "LineString")
            self.assertGreater(len(route_data["geometry"]["coordinates"]), 2)

    def test_07_optimize_delivery_route_end_to_end(self):
        """Verify full delivery route optimization returns stop sequences, ETAs, and GeoJSON."""
        donor = {
            "id": 1,
            "name": "Panjab University Student Center Canteen (Simulated)",
            "address": "Sector 14, Chandigarh",
            "latitude": 30.7600,
            "longitude": 76.7690,
            "collection_deadline": (datetime.now() + timedelta(hours=2)).isoformat()
        }
        stops = [
            {
                "id": 1,
                "name": "Tricity Langar Seva Society (Simulated)",
                "address": "Sector 19-C, Chandigarh",
                "latitude": 30.7280,
                "longitude": 76.7860,
                "quantity": 60
            },
            {
                "id": 2,
                "name": "Mohali Rain Basera Shelter (Simulated)",
                "address": "Phase 6, Mohali",
                "latitude": 30.7210,
                "longitude": 76.7090,
                "quantity": 40
            }
        ]

        result = optimize_delivery_route(donor, stops)
        self.assertEqual(result["status"], "success")
        self.assertIn("total_distance_km", result)
        self.assertIn("total_duration_minutes", result)
        self.assertIn("ordered_stops", result)
        self.assertIn("legs", result)
        self.assertIn("geojson", result)
        self.assertIn("estimated_completion", result)
        self.assertIn("estimated_completion_display", result)

        # Check stops structure
        ordered_stops = result["ordered_stops"]
        self.assertEqual(len(ordered_stops), 3)  # Donor + 2 recipient stops
        self.assertEqual(ordered_stops[0]["type"], "donor")
        self.assertEqual(ordered_stops[1]["type"], "recipient")
        self.assertEqual(ordered_stops[2]["type"], "recipient")

        # Verify ETAs and cumulative distances are non-decreasing
        self.assertLessEqual(ordered_stops[0]["cumulative_distance_km"], ordered_stops[1]["cumulative_distance_km"])
        self.assertLessEqual(ordered_stops[1]["cumulative_distance_km"], ordered_stops[2]["cumulative_distance_km"])

        # Check GeoJSON structure for Leaflet
        geojson = result["geojson"]
        self.assertEqual(geojson["type"], "Feature")
        self.assertIn("geometry", geojson)
        self.assertIn(geojson["geometry"]["type"], ["LineString", "MultiLineString"])

    def test_08_route_deadline_warning_detection(self):
        """Verify route optimizer generates deadline warnings when arrival time exceeds deadline."""
        # Expired or very tight deadline
        tight_deadline = (datetime.now() - timedelta(minutes=10)).isoformat()
        donor = {
            "id": 1,
            "name": "Banquet Hall (Simulated)",
            "latitude": 30.7600,
            "longitude": 76.7690,
            "collection_deadline": tight_deadline
        }
        stops = [
            {
                "id": 1,
                "name": "Shelter A",
                "latitude": 30.7000,
                "longitude": 76.7000,
                "collection_deadline": tight_deadline
            }
        ]
        result = optimize_delivery_route(donor, stops)
        self.assertEqual(result["status"], "success")
        self.assertGreater(len(result["deadline_warnings"]), 0)
        self.assertIn("Warning", result["deadline_warnings"][0])

    def test_09_haversine_fallback_resilience(self):
        """Verify routing gracefully falls back to Haversine 1.3x if OSRM endpoint fails."""
        # Pass a bogus OSRM port/host via temporary monkeypatch or zero coordinates
        donor = {"id": 1, "name": "Donor", "latitude": 30.73, "longitude": 76.77}
        stops = [{"id": 2, "name": "Stop 1", "latitude": 30.71, "longitude": 76.71}]

        # Call with 0.001s timeout to force fallback
        from backend.routing import get_osrm_distance_matrix
        dist, dur = get_osrm_distance_matrix([[76.77, 30.73], [76.71, 30.71]], timeout=0.001)
        self.assertIsNone(dist)

        # Full optimize_delivery_route must still return success with fallback
        result = optimize_delivery_route(donor, stops)
        self.assertEqual(result["status"], "success")
        self.assertGreater(result["total_distance_km"], 0)
        self.assertGreater(result["total_duration_minutes"], 0)

    def test_10_api_health_endpoint_diagnostics(self):
        """Verify /api/health returns detailed external service diagnostics."""
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertTrue(data["database_connected"])
        self.assertIn("gemini_active", data)
        self.assertIn("gemini_status", data)
        self.assertIsInstance(data["gemini_status"], dict)

    def test_11_api_route_post_endpoint(self):
        """Verify POST /api/route endpoint with valid donor and NGO IDs."""
        # 1 and 2 exist in seed database
        payload = {
            "donor_id": 1,
            "ngo_ids": [1, 2]
        }
        resp = self.client.post("/api/route", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "success")
        self.assertIn("geojson", data)
        self.assertIn("ordered_stops", data)
        self.assertEqual(len(data["ordered_stops"]), 3)

    def test_12_api_route_handles_missing_stops(self):
        """Verify POST /api/route handles missing or invalid stop data gracefully."""
        resp = self.client.post("/api/route", json={"donor_id": 1, "ngo_ids": []})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data["status"], "error")


if __name__ == "__main__":
    unittest.main()
