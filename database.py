import sqlite3
import os
from pathlib import Path
from config import Config

def get_db_connection():
    """Returns a SQLite connection with foreign keys enabled and row factory."""
    db_path = Config.DATABASE_PATH
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    """Initializes the database schema if tables do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS donors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        donor_type TEXT NOT NULL DEFAULT 'Restaurant',
        contact_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        email TEXT,
        address TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS ngos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        ngo_type TEXT NOT NULL DEFAULT 'Community Kitchen',
        contact_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        email TEXT,
        address TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        daily_capacity INTEGER NOT NULL DEFAULT 100,
        current_occupancy INTEGER NOT NULL DEFAULT 0,
        dietary_preferences TEXT NOT NULL DEFAULT '["Any"]',
        food_requirements TEXT NOT NULL DEFAULT '["Cooked Meals"]',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS donations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        donor_id INTEGER NOT NULL,
        food_name TEXT NOT NULL,
        food_category TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        allocated_quantity INTEGER NOT NULL DEFAULT 0,
        prep_time TEXT NOT NULL,
        collection_deadline TEXT NOT NULL,
        storage_condition TEXT NOT NULL,
        dietary_classification TEXT NOT NULL DEFAULT 'Vegetarian',
        allergens TEXT DEFAULT '[]',
        safety_status TEXT NOT NULL DEFAULT 'Valid',
        safety_reason TEXT,
        status TEXT NOT NULL DEFAULT 'Available',
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (donor_id) REFERENCES donors (id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS allocations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        donation_id INTEGER NOT NULL,
        ngo_id INTEGER NOT NULL,
        allocated_meals INTEGER NOT NULL,
        distance_km REAL NOT NULL DEFAULT 0.0,
        matching_score REAL NOT NULL DEFAULT 0.0,
        status TEXT NOT NULL DEFAULT 'Proposed',
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        accepted_at TIMESTAMP,
        FOREIGN KEY (donation_id) REFERENCES donations (id) ON DELETE CASCADE,
        FOREIGN KEY (ngo_id) REFERENCES ngos (id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS demand_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ngo_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        day_of_week TEXT NOT NULL,
        meals_demanded INTEGER NOT NULL,
        meals_served INTEGER NOT NULL,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ngo_id) REFERENCES ngos (id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient_type TEXT NOT NULL, -- 'Donor', 'NGO', 'Delivery Volunteer', 'System'
        recipient_name TEXT NOT NULL,
        channel TEXT NOT NULL,        -- 'SMS', 'WhatsApp', 'Dispatch Packet', 'Push'
        contact_info TEXT NOT NULL,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Delivered',
        action_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()

def save_allocation_transaction(donation_id: int, ngo_id: int, meals_to_allocate: int, distance_km: float = 0.0, matching_score: float = 0.0, notes: str = ""):
    """
    Safely allocates meals to an NGO inside an ACID transaction.
    Guarantees:
      1. Total allocated meals does NOT exceed available donation quantity.
      2. No duplicate unfulfilled allocations exceed surplus.
      3. NGO capacity headroom is respected.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE;")

        # Fetch donation row with lock
        cursor.execute("SELECT id, quantity, allocated_quantity, status FROM donations WHERE id = ?", (donation_id,))
        don_row = cursor.fetchone()
        if not don_row:
            raise ValueError(f"Donation with ID {donation_id} not found.")

        total_qty = don_row["quantity"]
        current_allocated = don_row["allocated_quantity"]
        remaining_qty = total_qty - current_allocated

        if meals_to_allocate <= 0:
            raise ValueError("Allocated meal count must be greater than zero.")

        if meals_to_allocate > remaining_qty:
            raise ValueError(
                f"Requested allocation ({meals_to_allocate} meals) exceeds remaining unallocated surplus ({remaining_qty} meals). "
                f"Total donation: {total_qty}, already allocated: {current_allocated}."
            )

        # Check NGO capacity
        cursor.execute("SELECT id, name, daily_capacity, current_occupancy FROM ngos WHERE id = ?", (ngo_id,))
        ngo_row = cursor.fetchone()
        if not ngo_row:
            raise ValueError(f"NGO with ID {ngo_id} not found.")

        ngo_cap = ngo_row["daily_capacity"]
        ngo_occ = ngo_row["current_occupancy"]
        available_cap = ngo_cap - ngo_occ
        if meals_to_allocate > available_cap:
            raise ValueError(
                f"NGO '{ngo_row['name']}' cannot receive {meals_to_allocate} meals. "
                f"Remaining capacity is only {available_cap} (Capacity: {ngo_cap}, Occupancy: {ngo_occ})."
            )

        # Insert allocation as Proposed
        cursor.execute("""
            INSERT INTO allocations (donation_id, ngo_id, allocated_meals, distance_km, matching_score, status, notes)
            VALUES (?, ?, ?, ?, ?, 'Proposed', ?)
        """, (donation_id, ngo_id, meals_to_allocate, distance_km, matching_score, notes))
        allocation_id = cursor.lastrowid

        # Update donation allocated_quantity
        new_allocated = current_allocated + meals_to_allocate
        new_status = "Proposed" if new_allocated >= total_qty else "Available"

        cursor.execute("""
            UPDATE donations 
            SET allocated_quantity = ?, status = ?
            WHERE id = ?
        """, (new_allocated, new_status, donation_id))

        conn.commit()
        return allocation_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def accept_allocation_transaction(allocation_id: int):
    """
    Marks proposed allocation as Accepted and updates NGO current occupancy.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE;")

        cursor.execute("""
            SELECT a.id, a.donation_id, a.ngo_id, a.allocated_meals, a.status,
                   d.quantity as don_quantity, d.allocated_quantity as don_allocated
            FROM allocations a
            JOIN donations d ON a.donation_id = d.id
            WHERE a.id = ?
        """, (allocation_id,))
        row = cursor.fetchone()

        if not row:
            raise ValueError(f"Allocation #{allocation_id} not found.")

        if row["status"] == "Accepted":
            # Already accepted
            conn.commit()
            return True

        allocated_meals = row["allocated_meals"]
        ngo_id = row["ngo_id"]
        donation_id = row["donation_id"]

        # Update allocation status
        cursor.execute("""
            UPDATE allocations
            SET status = 'Accepted', accepted_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (allocation_id,))

        # Update NGO occupancy
        cursor.execute("""
            UPDATE ngos
            SET current_occupancy = current_occupancy + ?
            WHERE id = ?
        """, (allocated_meals, ngo_id))

        # Check if all allocations for this donation are accepted
        cursor.execute("""
            SELECT COUNT(*) as pending_count
            FROM allocations
            WHERE donation_id = ? AND status = 'Proposed'
        """, (donation_id,))
        pending = cursor.fetchone()["pending_count"]

        if pending == 0 and row["don_allocated"] >= row["don_quantity"]:
            cursor.execute("UPDATE donations SET status = 'Accepted' WHERE id = ?", (donation_id,))

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def log_notification(recipient_type, recipient_name, channel, contact_info, title, message, action_url=None):
    """Logs an automated notification/message dispatched to a Donor, NGO or Delivery Volunteer."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO notifications (recipient_type, recipient_name, channel, contact_info, title, message, action_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (recipient_type, recipient_name, channel, contact_info, title, message, action_url))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        conn.rollback()
        print(f"Failed to log notification: {e}")
        return None
    finally:
        conn.close()

def get_recent_notifications(limit=50):
    """Fetches the latest automated notification dispatches."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, recipient_type, recipient_name, channel, contact_info, title, message, status, action_url, created_at
            FROM notifications
            ORDER BY created_at DESC, id DESC
            LIMIT ?
        """, (limit,))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

