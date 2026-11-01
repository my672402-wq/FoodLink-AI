import os
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template

# Ensure local imports resolve correctly
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config import Config
from database import (
    get_db_connection,
    init_db,
    save_allocation_transaction,
    accept_allocation_transaction,
    log_notification,
    get_recent_notifications
)
from backend.food_safety import validate_food_safety
from backend.matching import rank_ngos_for_donation, haversine_distance
from backend.forecasting import calculate_statistical_demand_forecast
from backend.routing import optimize_delivery_route
from backend.ai_service import ai_service
from data.seed_data import seed_database

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.from_object(Config)

# Initialize database on startup
init_db()

# -------------------------------------------------------------
# FRONTEND ROUTE
# -------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

# -------------------------------------------------------------
# REST API ENDPOINTS
# -------------------------------------------------------------

@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint providing status of database and AI service."""
    db_ok = False
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False

    return jsonify({
        "status": "healthy" if db_ok else "degraded",
        "service": "FoodLink AI API",
        "version": "1.0.0",
        "database_connected": db_ok,
        "gemini_active": ai_service.is_available(),
        "gemini_model": ai_service.model_name,
        "gemini_status": ai_service.get_status(),
        "timestamp": datetime.now().isoformat()
    }), 200

@app.route("/api/seed", methods=["POST"])
def reset_and_seed():
    """Utility endpoint to re-seed database with realistic Chandigarh-Mohali demo data."""
    try:
        seed_database()
        return jsonify({"status": "success", "message": "Database reset and seeded with demonstration data."}), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/api/dashboard", methods=["GET"])
def get_dashboard_data():
    """Main dashboard metrics, urgent warnings, and recent activity."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Total counts
    cursor.execute("SELECT COUNT(*) as cnt FROM donors")
    total_donors = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM ngos")
    total_ngos = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(quantity), 0) as total_meals, COALESCE(SUM(allocated_quantity), 0) as allocated_meals FROM donations")
    don_stats = cursor.fetchone()
    total_donations = don_stats["cnt"]
    total_meals_available = don_stats["total_meals"]
    meals_allocated = don_stats["allocated_meals"]

    # Category distribution
    cursor.execute("""
        SELECT food_category, COUNT(*) as count, SUM(quantity) as meals
        FROM donations
        GROUP BY food_category
    """)
    category_breakdown = [dict(row) for row in cursor.fetchall()]

    # Status distribution
    cursor.execute("""
        SELECT status, COUNT(*) as count
        FROM donations
        GROUP BY status
    """)
    status_breakdown = {row["status"]: row["count"] for row in cursor.fetchall()}

    # Urgent donations (Available or Proposed, collection deadline within next 3.5 hours)
    cursor.execute("""
        SELECT d.*, dn.name as donor_name, dn.phone as donor_phone, dn.address as donor_address
        FROM donations d
        JOIN donors dn ON d.donor_id = dn.id
        WHERE d.status IN ('Available', 'Proposed') AND d.safety_status = 'Valid'
        ORDER BY d.collection_deadline ASC
        LIMIT 5
    """)
    urgent_donations = [dict(row) for row in cursor.fetchall()]

    # Recent activities (latest allocations and donations)
    cursor.execute("""
        SELECT a.id, a.allocated_meals, a.distance_km, a.matching_score, a.status, a.created_at,
               d.food_name, d.food_category, dn.name as donor_name, n.name as ngo_name
        FROM allocations a
        JOIN donations d ON a.donation_id = d.id
        JOIN donors dn ON d.donor_id = dn.id
        JOIN ngos n ON a.ngo_id = n.id
        ORDER BY a.created_at DESC
        LIMIT 5
    """)
    recent_allocations = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT d.*, dn.name as donor_name
        FROM donations d
        JOIN donors dn ON d.donor_id = dn.id
        ORDER BY d.created_at DESC
        LIMIT 6
    """)
    recent_donations = [dict(row) for row in cursor.fetchall()]

    conn.close()

    metrics = {
        "total_donors": total_donors,
        "active_ngos": total_ngos,
        "total_donations": total_donations,
        "total_meals_available": total_meals_available,
        "meals_allocated": meals_allocated,
        "meals_pending": max(0, total_meals_available - meals_allocated)
    }

    return jsonify({
        "status": "success",
        "metrics": metrics,
        "category_breakdown": category_breakdown,
        "status_breakdown": status_breakdown,
        "urgent_donations": urgent_donations,
        "recent_allocations": recent_allocations,
        "recent_donations": recent_donations
    }), 200

# -------------------------------------------------------------
# DONORS API
# -------------------------------------------------------------
@app.route("/api/donors", methods=["GET", "POST"])
def handle_donors():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        name = data.get("name", "").strip()
        donor_type = data.get("donor_type", "Restaurant").strip()
        contact_name = data.get("contact_name", "").strip()
        phone = data.get("phone", "").strip()
        email = data.get("email", "").strip()
        address = data.get("address", "").strip()
        lat = data.get("latitude")
        lon = data.get("longitude")

        if not name or not contact_name or not phone or not address or lat is None or lon is None:
            conn.close()
            return jsonify({"status": "error", "error": "Missing required fields: name, contact_name, phone, address, latitude, longitude."}), 400

        try:
            cursor.execute("""
                INSERT INTO donors (name, donor_type, contact_name, phone, email, address, latitude, longitude)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, donor_type, contact_name, phone, email, address, float(lat), float(lon)))
            donor_id = cursor.lastrowid
            conn.commit()
            conn.close()

            log_notification(
                recipient_type="Donor",
                recipient_name=name,
                channel="SMS",
                contact_info=phone,
                title="Donor Account Activated",
                message=f"🌿 Welcome to FoodLink AI! '{name}' is verified for surplus food redistribution in {address}."
            )

            return jsonify({"status": "success", "donor_id": donor_id, "message": "Donor registered successfully."}), 201
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({"status": "error", "error": str(e)}), 500

    # GET
    cursor.execute("SELECT * FROM donors ORDER BY created_at DESC")
    donors = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"status": "success", "donors": donors}), 200

# -------------------------------------------------------------
# NGOS API
# -------------------------------------------------------------
@app.route("/api/ngos", methods=["GET", "POST"])
def handle_ngos():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        name = data.get("name", "").strip()
        ngo_type = data.get("ngo_type", "Community Kitchen").strip()
        contact_name = data.get("contact_name", "").strip()
        phone = data.get("phone", "").strip()
        email = data.get("email", "").strip()
        address = data.get("address", "").strip()
        lat = data.get("latitude")
        lon = data.get("longitude")
        daily_capacity = data.get("daily_capacity", 100)
        current_occupancy = data.get("current_occupancy", 0)
        dietary_prefs = data.get("dietary_preferences", ["Any"])
        food_reqs = data.get("food_requirements", ["Cooked Meals"])

        if not name or not contact_name or not phone or not address or lat is None or lon is None:
            conn.close()
            return jsonify({"status": "error", "error": "Missing required fields: name, contact_name, phone, address, latitude, longitude."}), 400

        diet_json = json.dumps(dietary_prefs) if isinstance(dietary_prefs, (list, dict)) else str(dietary_prefs)
        reqs_json = json.dumps(food_reqs) if isinstance(food_reqs, (list, dict)) else str(food_reqs)

        try:
            cursor.execute("""
                INSERT INTO ngos (name, ngo_type, contact_name, phone, email, address, latitude, longitude, daily_capacity, current_occupancy, dietary_preferences, food_requirements)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, ngo_type, contact_name, phone, email, address, float(lat), float(lon), int(daily_capacity), int(current_occupancy), diet_json, reqs_json))
            ngo_id = cursor.lastrowid

            # Seed a default initial week of demand history for the new NGO so forecasting works immediately
            now = datetime.now()
            history_rows = []
            for i in range(14):
                d = (now - timedelta(days=14 - i)).strftime("%Y-%m-%d")
                history_rows.append((ngo_id, d, "Weekday", int(daily_capacity * 0.75), int(daily_capacity * 0.70), "Baseline initialization"))
            cursor.executemany("INSERT INTO demand_history (ngo_id, date, day_of_week, meals_demanded, meals_served, notes) VALUES (?, ?, ?, ?, ?, ?)", history_rows)

            conn.commit()
            conn.close()

            log_notification(
                recipient_type="NGO",
                recipient_name=name,
                channel="WhatsApp",
                contact_info=phone,
                title="NGO Active on Redistribution Network",
                message=f"🤝 Welcome to FoodLink AI! '{name}' ({daily_capacity} meals/day capacity) is now live to receive immediate nearby surplus food match alerts."
            )

            return jsonify({"status": "success", "ngo_id": ngo_id, "message": "NGO registered successfully."}), 201
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({"status": "error", "error": str(e)}), 500

    # GET
    cursor.execute("SELECT * FROM ngos ORDER BY name ASC")
    rows = cursor.fetchall()
    ngos = []
    for r in rows:
        d = dict(r)
        d["available_capacity"] = max(0, d["daily_capacity"] - d["current_occupancy"])
        try:
            d["dietary_preferences"] = json.loads(d["dietary_preferences"])
        except Exception:
            pass
        try:
            d["food_requirements"] = json.loads(d["food_requirements"])
        except Exception:
            pass
        ngos.append(d)
    conn.close()
    return jsonify({"status": "success", "ngos": ngos}), 200

# -------------------------------------------------------------
# DONATIONS API
# -------------------------------------------------------------
@app.route("/api/donations", methods=["GET", "POST"])
def handle_donations():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        donor_id = data.get("donor_id")
        food_name = data.get("food_name", "").strip()
        food_category = data.get("food_category", "Cooked Meals").strip()
        quantity = data.get("quantity")
        prep_time = data.get("prep_time", "").strip()
        collection_deadline = data.get("collection_deadline", "").strip()
        storage_condition = data.get("storage_condition", "Room Temp (20-25°C)").strip()
        dietary_classification = data.get("dietary_classification", "Vegetarian").strip()
        allergens = data.get("allergens", [])
        notes = data.get("notes", "").strip()

        if not donor_id or not food_name or not quantity or not prep_time or not collection_deadline or not storage_condition:
            conn.close()
            return jsonify({"status": "error", "error": "Missing required donation fields."}), 400

        try:
            quantity = int(quantity)
            if quantity <= 0:
                conn.close()
                return jsonify({"status": "error", "error": "Quantity must be a positive integer."}), 400
        except ValueError:
            conn.close()
            return jsonify({"status": "error", "error": "Quantity must be a valid number."}), 400

        # Run Food Safety Engine Validation
        safety_result = validate_food_safety(
            food_name=food_name,
            food_category=food_category,
            prep_time_raw=prep_time,
            collection_deadline_raw=collection_deadline,
            storage_condition=storage_condition,
            allergens=allergens
        )

        safety_status = safety_result["status"] # 'Valid' or 'Rejected'
        safety_reason = "; ".join(safety_result["reasons"]) if not safety_result["is_safe"] else None
        donation_status = "Available" if safety_result["is_safe"] else "Rejected"

        allergens_json = json.dumps(allergens) if isinstance(allergens, (list, dict)) else str(allergens)

        try:
            cursor.execute("""
                INSERT INTO donations (
                    donor_id, food_name, food_category, quantity, allocated_quantity,
                    prep_time, collection_deadline, storage_condition, dietary_classification,
                    allergens, safety_status, safety_reason, status, notes
                ) VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (donor_id, food_name, food_category, quantity, prep_time, collection_deadline, storage_condition, dietary_classification, allergens_json, safety_status, safety_reason, donation_status, notes))
            donation_id = cursor.lastrowid

            # Fetch donor info for alert dispatch
            cursor.execute("SELECT name, phone FROM donors WHERE id = ?", (donor_id,))
            donor_row = cursor.fetchone()
            donor_name = donor_row["name"] if donor_row else "Registered Donor"
            donor_phone = donor_row["phone"] if donor_row else "N/A"

            conn.commit()
            conn.close()

            if safety_result["is_safe"]:
                log_notification(
                    recipient_type="Donor",
                    recipient_name=donor_name,
                    channel="SMS",
                    contact_info=donor_phone,
                    title="Donation Passed Food Safety Screening",
                    message=f"✓ Donation '{food_name}' ({quantity} meals) passed safety screening. Available for immediate recipient matching."
                )
            else:
                log_notification(
                    recipient_type="Donor",
                    recipient_name=donor_name,
                    channel="SMS",
                    contact_info=donor_phone,
                    title="Safety Screening Flagged Unsafe",
                    message=f"⚠️ Donation '{food_name}' could not be published: {safety_reason}."
                )

            return jsonify({
                "status": "success",
                "donation_id": donation_id,
                "safety_evaluation": safety_result,
                "message": "Donation created successfully." if safety_result["is_safe"] else "Donation recorded but marked REJECTED due to food safety screening."
            }), 201
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({"status": "error", "error": str(e)}), 500

    # GET
    status_filter = request.args.get("status")
    query = """
        SELECT d.*, dn.name as donor_name, dn.phone as donor_phone, dn.address as donor_address,
               dn.latitude as donor_latitude, dn.longitude as donor_longitude
        FROM donations d
        JOIN donors dn ON d.donor_id = dn.id
    """
    params = []
    if status_filter:
        query += " WHERE d.status = ?"
        params.append(status_filter)
    query += " ORDER BY d.created_at DESC"

    cursor.execute(query, params)
    donations = []
    for r in cursor.fetchall():
        d = dict(r)
        d["unallocated_quantity"] = max(0, d["quantity"] - d["allocated_quantity"])
        try:
            d["allergens"] = json.loads(d["allergens"])
        except Exception:
            pass
        donations.append(d)
    conn.close()
    return jsonify({"status": "success", "donations": donations}), 200

@app.route("/api/donations/<int:donation_id>", methods=["GET"])
def get_donation_by_id(donation_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT d.*, dn.name as donor_name, dn.phone as donor_phone, dn.email as donor_email,
               dn.address as donor_address, dn.latitude as donor_latitude, dn.longitude as donor_longitude
        FROM donations d
        JOIN donors dn ON d.donor_id = dn.id
        WHERE d.id = ?
    """, (donation_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({"status": "error", "error": f"Donation #{donation_id} not found."}), 404

    donation = dict(row)
    donation["unallocated_quantity"] = max(0, donation["quantity"] - donation["allocated_quantity"])
    try:
        donation["allergens"] = json.loads(donation["allergens"])
    except Exception:
        pass

    # Fetch any allocations for this donation
    cursor.execute("""
        SELECT a.*, n.name as ngo_name, n.phone as ngo_phone, n.address as ngo_address,
               n.latitude as ngo_latitude, n.longitude as ngo_longitude
        FROM allocations a
        JOIN ngos n ON a.ngo_id = n.id
        WHERE a.donation_id = ?
        ORDER BY a.created_at DESC
    """, (donation_id,))
    allocations = [dict(r) for r in cursor.fetchall()]

    conn.close()
    return jsonify({
        "status": "success",
        "donation": donation,
        "allocations": allocations
    }), 200

# -------------------------------------------------------------
# AI SMART MATCHING API
# -------------------------------------------------------------
@app.route("/api/match/<int:donation_id>", methods=["POST"])
def run_matching(donation_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch donation and donor details
    cursor.execute("""
        SELECT d.*, dn.name as donor_name, dn.address as donor_address,
               dn.latitude as donor_latitude, dn.longitude as donor_longitude
        FROM donations d
        JOIN donors dn ON d.donor_id = dn.id
        WHERE d.id = ?
    """, (donation_id,))
    don_row = cursor.fetchone()

    if not don_row:
        conn.close()
        return jsonify({"status": "error", "error": f"Donation #{donation_id} not found."}), 404

    donation = dict(don_row)

    # Fetch all registered NGOs
    cursor.execute("SELECT * FROM ngos ORDER BY id ASC")
    ngos = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # Rank NGOs using multi-factor scoring and hard constraints
    ranked_results = rank_ngos_for_donation(donation, ngos)

    # Generate Gemini explanation (or deterministic fallback)
    ai_explanation = ai_service.generate_matching_explanation(donation, ranked_results)

    return jsonify({
        "status": "success",
        "donation_id": donation_id,
        "food_name": donation["food_name"],
        "surplus_meals": max(0, donation["quantity"] - donation["allocated_quantity"]),
        "ranked_matches": ranked_results,
        "ai_explanation": ai_explanation
    }), 200

# -------------------------------------------------------------
# ALLOCATIONS API (TRANSACTION SAFE)
# -------------------------------------------------------------
@app.route("/api/allocations", methods=["POST"])
def create_allocation():
    data = request.get_json(silent=True) or {}
    donation_id = data.get("donation_id")
    ngo_id = data.get("ngo_id")
    meals_to_allocate = data.get("allocated_meals")
    distance_km = float(data.get("distance_km", 0.0))
    matching_score = float(data.get("matching_score", 0.0))
    notes = data.get("notes", "").strip()

    if not donation_id or not ngo_id or not meals_to_allocate:
        return jsonify({"status": "error", "error": "Missing required fields: donation_id, ngo_id, allocated_meals."}), 400

    try:
        meals_to_allocate = int(meals_to_allocate)
    except ValueError:
        return jsonify({"status": "error", "error": "allocated_meals must be an integer."}), 400

    try:
        allocation_id = save_allocation_transaction(
            donation_id=int(donation_id),
            ngo_id=int(ngo_id),
            meals_to_allocate=meals_to_allocate,
            distance_km=distance_km,
            matching_score=matching_score,
            notes=notes
        )

        # Trigger automated notification to recipient NGO
        try:
            conn = get_db_connection()
            info_row = conn.execute("""
                SELECT n.name as ngo_name, n.phone as ngo_phone, d.food_name, dn.name as donor_name
                FROM ngos n, donations d, donors dn
                WHERE n.id = ? AND d.id = ? AND d.donor_id = dn.id
            """, (ngo_id, donation_id)).fetchone()
            conn.close()
            if info_row:
                log_notification(
                    recipient_type="NGO",
                    recipient_name=info_row["ngo_name"],
                    channel="WhatsApp",
                    contact_info=info_row["ngo_phone"],
                    title=f"Surplus Batch Match: {meals_to_allocate} Meals Available",
                    message=f"🟢 Match Alert! {meals_to_allocate} meals of '{info_row['food_name']}' allocated from {info_row['donor_name']} ({distance_km} km away). Action Required: Accept Batch in FoodLink AI."
                )
        except Exception as log_err:
            print(f"Notification dispatch warning: {log_err}")

        return jsonify({
            "status": "success",
            "allocation_id": allocation_id,
            "message": f"Successfully allocated {meals_to_allocate} meals (Status: Proposed)."
        }), 201
    except ValueError as val_err:
        return jsonify({"status": "error", "error": str(val_err)}), 400
    except Exception as e:
        return jsonify({"status": "error", "error": f"Internal error during allocation: {str(e)}"}), 500

@app.route("/api/allocations/<int:allocation_id>/accept", methods=["POST"])
def accept_allocation(allocation_id):
    try:
        # Fetch details before or after accept for alert dispatch
        conn = get_db_connection()
        info_row = conn.execute("""
            SELECT a.allocated_meals, n.name as ngo_name, n.phone as ngo_phone,
                   d.food_name, dn.name as donor_name, dn.phone as donor_phone
            FROM allocations a
            JOIN ngos n ON a.ngo_id = n.id
            JOIN donations d ON a.donation_id = d.id
            JOIN donors dn ON d.donor_id = dn.id
            WHERE a.id = ?
        """, (allocation_id,)).fetchone()
        conn.close()

        accept_allocation_transaction(allocation_id)

        if info_row:
            # 1. Alert to Donor
            log_notification(
                recipient_type="Donor",
                recipient_name=info_row["donor_name"],
                channel="SMS",
                contact_info=info_row["donor_phone"],
                title="Donation Batch Accepted",
                message=f"🤝 Great news! {info_row['ngo_name']} accepted your donation of {info_row['allocated_meals']} meals of '{info_row['food_name']}'. Delivery volunteer dispatched for pickup."
            )
            # 2. Alert to Delivery Volunteer
            log_notification(
                recipient_type="Delivery Volunteer",
                recipient_name="Volunteer Logistics Dispatch",
                channel="Dispatch Packet",
                contact_info=info_row["ngo_phone"],
                title="Delivery Dispatch Task Activated",
                message=f"🚗 Delivery Task Created! Pickup {info_row['allocated_meals']} meals from {info_row['donor_name']} -> Deliver to {info_row['ngo_name']}. Road route & ETA ready."
            )

        return jsonify({
            "status": "success",
            "message": f"Allocation #{allocation_id} accepted by recipient organization."
        }), 200
    except ValueError as val_err:
        return jsonify({"status": "error", "error": str(val_err)}), 400
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

# -------------------------------------------------------------
# DEMAND FORECASTING API
# -------------------------------------------------------------
@app.route("/api/forecast/<int:ngo_id>", methods=["GET"])
def get_ngo_forecast(ngo_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM ngos WHERE id = ?", (ngo_id,))
    ngo_row = cursor.fetchone()
    if not ngo_row:
        conn.close()
        return jsonify({"status": "error", "error": f"NGO #{ngo_id} not found."}), 404
    ngo = dict(ngo_row)

    cursor.execute("""
        SELECT date, day_of_week, meals_demanded, meals_served, notes
        FROM demand_history
        WHERE ngo_id = ?
        ORDER BY date ASC
    """, (ngo_id,))
    history_records = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # Calculate statistical forecast using weighted formula
    forecast_data = calculate_statistical_demand_forecast(history_records)

    # Generate AI explanation (Gemini or deterministic)
    ai_summary = ai_service.generate_forecast_summary(ngo, forecast_data)

    return jsonify({
        "status": "success",
        "ngo": ngo,
        "forecast": forecast_data,
        "ai_summary": ai_summary
    }), 200

# -------------------------------------------------------------
# ROUTE OPTIMIZATION API (OSRM + LEAFLET GEOJSON)
# -------------------------------------------------------------
@app.route("/api/route", methods=["POST"])
def calculate_route():
    data = request.get_json(silent=True) or {}
    donor_id = data.get("donor_id")
    ngo_ids = data.get("ngo_ids", [])
    donation_id = data.get("donation_id")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Donor coordinates
    if donor_id:
        cursor.execute("SELECT id, name, address, latitude, longitude FROM donors WHERE id = ?", (donor_id,))
        d_row = cursor.fetchone()
        if not d_row:
            conn.close()
            return jsonify({"status": "error", "error": f"Donor #{donor_id} not found."}), 404
        donor_info = dict(d_row)
    else:
        donor_info = data.get("donor")
        if not donor_info or "latitude" not in donor_info or "longitude" not in donor_info:
            conn.close()
            return jsonify({"status": "error", "error": "Donor details or donor_id required."}), 400

    # Fetch collection deadline if donation_id given
    if donation_id:
        cursor.execute("SELECT collection_deadline FROM donations WHERE id = ?", (donation_id,))
        don_row = cursor.fetchone()
        if don_row:
            donor_info["collection_deadline"] = don_row["collection_deadline"]

    # Recipient stops
    recipient_stops = []
    if ngo_ids:
        placeholders = ",".join("?" for _ in ngo_ids)
        cursor.execute(f"SELECT id, name, address, latitude, longitude FROM ngos WHERE id IN ({placeholders})", ngo_ids)
        for row in cursor.fetchall():
            recipient_stops.append(dict(row))
    elif "stops" in data:
        recipient_stops = data["stops"]

    conn.close()

    if not recipient_stops:
        return jsonify({"status": "error", "error": "At least one recipient NGO stop is required for route calculation."}), 400

    # Optimize route
    result = optimize_delivery_route(donor_info, recipient_stops)

    if result.get("status") == "success":
        try:
            log_notification(
                recipient_type="Delivery Volunteer",
                recipient_name="Volunteer Navigation Unit",
                channel="Dispatch Packet",
                contact_info="Mobile GPS Unit",
                title=f"Turn-by-Turn Delivery Route Generated ({result['total_distance_km']} km)",
                message=f"🗺️ OSRM Route: {result['stops_count']} stops, {result['total_duration_minutes']} min drive. Estimated Delivery Completion: {result.get('estimated_completion_display', 'N/A')}."
            )
        except Exception as log_err:
            print(f"Route alert log warning: {log_err}")

    return jsonify(result), 200

# -------------------------------------------------------------
# NOTIFICATIONS DISPATCH TELEMETRY API
# -------------------------------------------------------------
@app.route("/api/notifications", methods=["GET", "POST"])
def handle_notifications():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        r_type = data.get("recipient_type", "System")
        r_name = data.get("recipient_name", "Broadcast")
        channel = data.get("channel", "In-App")
        contact = data.get("contact_info", "N/A")
        title = data.get("title", "FoodLink Alert")
        message = data.get("message", "")
        nid = log_notification(r_type, r_name, channel, contact, title, message)
        return jsonify({"status": "success", "notification_id": nid}), 201

    limit = int(request.args.get("limit", 50))
    notifs = get_recent_notifications(limit=limit)
    return jsonify({"status": "success", "notifications": notifs, "count": len(notifs)}), 200

# -------------------------------------------------------------
# AI SYSTEM INSIGHTS API
# -------------------------------------------------------------
@app.route("/api/ai-insights", methods=["POST"])
def get_ai_insights():
    """Generates overall intelligence briefing for platform administrators."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total_donations, COALESCE(SUM(quantity), 0) as total_meals_available, COALESCE(SUM(allocated_quantity), 0) as meals_allocated FROM donations")
    row = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) as active_ngos FROM ngos")
    active_ngos = cursor.fetchone()["active_ngos"]
    conn.close()

    metrics = {
        "total_donations": row["total_donations"],
        "total_meals_available": row["total_meals_available"],
        "meals_allocated": row["meals_allocated"],
        "active_ngos": active_ngos
    }

    insights_result = ai_service.generate_platform_insights(metrics)
    return jsonify({
        "status": "success",
        "metrics": metrics,
        "insights_data": insights_result
    }), 200

# -------------------------------------------------------------
# MAIN SERVER ENTRYPOINT
# -------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    print(f"Starting FoodLink AI on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=debug)
