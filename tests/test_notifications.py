"""
Test Suite for Real-Time Notification & Alert Dispatch Engine
"""
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import app
from database import log_notification, get_recent_notifications

class TestNotificationEngine(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_01_get_notifications(self):
        resp = self.client.get("/api/notifications")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "success")
        self.assertGreaterEqual(data["count"], 4)

    def test_02_post_simulated_notification(self):
        payload = {
            "recipient_type": "NGO",
            "recipient_name": "Govinda Seva Sadan",
            "channel": "WhatsApp",
            "contact_info": "+91 62016 23632",
            "title": "Surplus Match Alert",
            "message": "60 meals of Cooked Rice available from CGCU Jhanjeri."
        }
        resp = self.client.post("/api/notifications", json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertEqual(data["status"], "success")
        self.assertTrue(data["notification_id"] > 0)

    def test_03_log_and_fetch_order(self):
        nid = log_notification(
            recipient_type="Delivery Volunteer",
            recipient_name="Volunteer Unit 1",
            channel="Dispatch Packet",
            contact_info="+91 99999 88888",
            title="Road Route Ready",
            message="Driving route calculated: 6.87 km"
        )
        self.assertIsNotNone(nid)
        recent = get_recent_notifications(limit=5)
        self.assertTrue(any(n["id"] == nid for n in recent))

if __name__ == "__main__":
    unittest.main()
