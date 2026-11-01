import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
import random

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import get_db_connection, init_db

def seed_database():
    """Populates the SQLite database with realistic demonstration data for Chandigarh-Mohali."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    # Clear existing demo records and reset auto-increment sequences
    cursor.execute("DELETE FROM notifications;")
    cursor.execute("DELETE FROM demand_history;")
    cursor.execute("DELETE FROM allocations;")
    cursor.execute("DELETE FROM donations;")
    cursor.execute("DELETE FROM ngos;")
    cursor.execute("DELETE FROM donors;")
    try:
        cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('donors', 'ngos', 'donations', 'allocations', 'demand_history', 'notifications');")
    except Exception:
        pass
    conn.commit()

    # 1. Donors (Chandigarh - Mohali Region)
    donors_data = [
        (
            "PU Central Student Canteen (Simulated)",
            "College Canteen",
            "Prof. Ramesh Sharma",
            "+91 98765 11001",
            "canteen@pu-simulated.edu.in",
            "Student Centre, Panjab University, Sector 14, Chandigarh",
            30.7600,
            76.7684
        ),
        (
            "The Grand Haveli Caterers (Simulated)",
            "Event Catering",
            "Kuldeep Singh Sandhu",
            "+91 98765 11002",
            "events@grandhaveli-simulated.com",
            "SCO 142-143, Sector 35-B, Chandigarh",
            30.7230,
            76.7640
        ),
        (
            "Tricity Bites Gourmet Diner (Simulated)",
            "Restaurant",
            "Priya Verma",
            "+91 98765 11003",
            "manager@tricitybites-sim.in",
            "Showroom 28, Phase 3B2, Mohali, Punjab",
            30.7180,
            76.7275
        ),
        (
            "PEC Hostel Mess No. 3 (Simulated)",
            "Hostel Mess",
            "S. Harpreet Singh",
            "+91 98765 11004",
            "mess3@pec-simulated.ac.in",
            "Punjab Engineering College, Sector 12, Chandigarh",
            30.7650,
            76.7860
        )
    ]

    donor_ids = []
    for d in donors_data:
        cursor.execute("""
            INSERT INTO donors (name, donor_type, contact_name, phone, email, address, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, d)
        donor_ids.append(cursor.lastrowid)

    # 2. NGOs (Chandigarh - Mohali Region)
    ngos_data = [
        (
            "Annapurna Seva Community Kitchen (Simulated)",
            "Community Kitchen",
            "Surinder Kaur",
            "+91 98111 22001",
            "annapurna@sevacommunity-sim.org",
            "Community Hall, Sector 20-C, Chandigarh",
            30.7280,
            76.7780,
            250, # daily capacity
            65,  # current occupancy
            json.dumps(["Vegetarian", "Any"]),
            json.dumps(["Cooked Meals", "Perishable Dairy", "Bakery"])
        ),
        (
            "Sahyog Shelter for Hope (Simulated)",
            "Food Shelter",
            "Capt. R.K. Bakshi",
            "+91 98111 22002",
            "contact@sahyogshelter-sim.org",
            "Plot 54, Industrial Area Phase 7, Mohali, Punjab",
            30.7046,
            76.7179,
            180,
            75,
            json.dumps(["Any"]),
            json.dumps(["Cooked Meals", "Packaged", "Raw Produce"])
        ),
        (
            "Mother Teresa Ashray NGO (Simulated)",
            "NGO / Family Aid",
            "Sister Philomena",
            "+91 98111 22003",
            "ashray@mt-familyaid-sim.org",
            "Sector 23-B Near Children Home, Chandigarh",
            30.7320,
            76.7650,
            150,
            40,
            json.dumps(["Vegetarian", "Vegan"]),
            json.dumps(["Cooked Meals", "Bakery", "Raw Produce"])
        ),
        (
            "Guru Nanak Langar Mission (Simulated)",
            "Community Kitchen",
            "Bhai Jaspal Singh",
            "+91 98111 22004",
            "langarseva@gn-mission-sim.org",
            "Near Phase 1 Gurdwara Sahib, Mohali, Punjab",
            30.7110,
            76.7020,
            400,
            140,
            json.dumps(["Vegetarian", "Any"]),
            json.dumps(["Cooked Meals", "Raw Produce", "Packaged"])
        )
    ]

    ngo_ids = []
    for n in ngos_data:
        cursor.execute("""
            INSERT INTO ngos (name, ngo_type, contact_name, phone, email, address, latitude, longitude, daily_capacity, current_occupancy, dietary_preferences, food_requirements)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, n)
        ngo_ids.append(cursor.lastrowid)

    # 3. Donations with varied categories, quantities and deadlines
    now = datetime.now()

    donations_data = [
        (
            donor_ids[0], # PU Canteen
            "Rajma Masala, Jeera Rice & Mix Veg",
            "Cooked Meals",
            120,
            0,
            (now - timedelta(hours=1, minutes=30)).strftime("%Y-%m-%dT%H:%M"),
            (now + timedelta(hours=2, minutes=30)).strftime("%Y-%m-%dT%H:%M"),
            "Hot-hold (>60°C)",
            "Vegetarian",
            json.dumps(["Dairy"]),
            "Valid",
            None,
            "Available",
            "Prepared for campus lunch rush. Kept in steam buffet tables."
        ),
        (
            donor_ids[1], # Grand Haveli Caterers
            "Paneer Butter Masala & Dal Makhani Banquet Trays",
            "Cooked Meals",
            85,
            0,
            (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            (now + timedelta(hours=3, minutes=15)).strftime("%Y-%m-%dT%H:%M"),
            "Hot-hold (>60°C)",
            "Vegetarian",
            json.dumps(["Dairy", "Nuts"]),
            "Valid",
            None,
            "Available",
            "Unserved banquet batch from corporate seminar. High-calorie wholesome meals."
        ),
        (
            donor_ids[3], # PEC Hostel Mess
            "Moong Dal, Rice, Mixed Dry Sabzi & Rotis",
            "Cooked Meals",
            180,
            0,
            (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
            (now + timedelta(hours=2, minutes=0)).strftime("%Y-%m-%dT%H:%M"),
            "Hot-hold (>60°C)",
            "Vegetarian",
            json.dumps(["Gluten"]),
            "Valid",
            None,
            "Available",
            "Hostel mess batch surplus. Packaged in sanitized thermal vessels."
        ),
        (
            donor_ids[2], # Tricity Bites Diner
            "Artisan Multigrain Loaves & Banana Walnut Bread",
            "Bakery",
            50,
            0,
            (now - timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M"),
            (now + timedelta(hours=28)).strftime("%Y-%m-%dT%H:%M"),
            "Room Temp (20-25°C)",
            "Vegetarian",
            json.dumps(["Gluten", "Nuts"]),
            "Valid",
            None,
            "Available",
            "Surplus morning bake. Individually wrapped in food-grade kraft bags."
        ),
        (
            donor_ids[2], # Tricity Bites Diner
            "Fresh Farm Tomatoes, Cucumbers & Spinach Crates",
            "Raw Produce",
            60,
            0,
            (now - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M"),
            (now + timedelta(hours=40)).strftime("%Y-%m-%dT%H:%M"),
            "Room Temp (20-25°C)",
            "Vegan",
            json.dumps([]),
            "Valid",
            None,
            "Available",
            "Crisp unpeeled whole vegetables suitable for community kitchen cooking."
        ),
        (
            donor_ids[1], # Grand Haveli (Food safety failed test case)
            "Buffet Mixed Chicken Gravy (Ambient Storage Test Case)",
            "Cooked Meals",
            40,
            0,
            (now - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M"),
            (now - timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M"),
            "Room Temp (20-25°C)",
            "Non-Veg",
            json.dumps(["Dairy"]),
            "Rejected",
            "Expired collection deadline and unsafe ambient storage exceeding 4-hour temperature danger limit.",
            "Rejected",
            "Simulated sample donation to test and verify food safety validation engine."
        )
    ]

    cursor.executemany("""
        INSERT INTO donations (
            donor_id, food_name, food_category, quantity, allocated_quantity,
            prep_time, collection_deadline, storage_condition, dietary_classification,
            allergens, safety_status, safety_reason, status, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, donations_data)

    # 4. Realistic 30-day Historical Demand records for each NGO
    demand_records = []
    base_demands = {
        1: 180, # Annapurna
        2: 120, # Sahyog
        3: 110, # Mother Teresa
        4: 280  # Guru Nanak
    }

    start_date = (now - timedelta(days=30)).date()
    for day_i in range(30):
        rec_date = start_date + timedelta(days=day_i)
        dow_str = rec_date.strftime("%A")
        is_weekend = rec_date.weekday() in (5, 6)

        for ngo_id in ngo_ids:
            base = base_demands[ngo_id]
            # Add weekend bump of +15-20%, plus realistic random variation
            variation = random.randint(-15, 18)
            weekend_boost = int(base * 0.18) if is_weekend else 0
            meals_demanded = max(30, base + weekend_boost + variation)
            # Meals served is typically 85-98% of demanded
            meals_served = int(meals_demanded * random.uniform(0.88, 0.98))

            demand_records.append((
                ngo_id,
                rec_date.strftime("%Y-%m-%d"),
                dow_str,
                meals_demanded,
                meals_served,
                f"Regular meal service ({dow_str})"
            ))

    cursor.executemany("""
        INSERT INTO demand_history (ngo_id, date, day_of_week, meals_demanded, meals_served, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, demand_records)

    # 5. Realistic Notification Dispatch Logs for Demonstration
    sample_notifications = [
        (
            "Donor",
            "PU Central Student Canteen (Simulated)",
            "SMS",
            "+91 98765 11001",
            "Donor Verification Complete",
            "🌿 Welcome to FoodLink AI! PU Central Student Canteen is registered & verified for surplus food redistribution in Sector 14, Chandigarh.",
            "Delivered",
            None
        ),
        (
            "Donor",
            "The Grand Haveli Caterers (Simulated)",
            "SMS",
            "+91 98765 11002",
            "Food Safety Clearance Passed",
            "✓ Donation 'Paneer Butter Masala & Dal Makhani' (85 meals) passed safety screening. Valid collection window: 3.2 hours remaining.",
            "Delivered",
            None
        ),
        (
            "NGO",
            "Annapurna Seva Community Kitchen (Simulated)",
            "WhatsApp",
            "+91 98111 22001",
            "Surplus Match Alert: 120 Meals Available",
            "🟢 Urgent Food Match! 120 meals of 'Rajma Masala & Jeera Rice' available from PU Canteen (3.2 km away). Collect before 02:30 PM. Click to accept batch.",
            "Delivered",
            None
        ),
        (
            "Delivery Volunteer",
            "Mohali Quick-Response Volunteer Unit",
            "Dispatch Packet",
            "+91 98700 55441",
            "Delivery Route Generated (OSRM)",
            "🚗 Delivery Route Assigned: PU Central Canteen -> Annapurna Seva Kitchen. Driving distance: 4.67 km (~7 min drive). Turn-by-turn road navigation ready.",
            "Delivered",
            None
        )
    ]

    cursor.executemany("""
        INSERT INTO notifications (recipient_type, recipient_name, channel, contact_info, title, message, status, action_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, sample_notifications)

    conn.commit()
    conn.close()
    print("Database successfully initialized and seeded with Chandigarh-Mohali demonstration data.")

if __name__ == "__main__":
    seed_database()
