from datetime import datetime, timezone
import dateutil.parser
from config import Config

SAFETY_DISCLAIMER = (
    "FoodLink AI applies rule-based pre-collection risk screening to assist food redistribution logistics. "
    "This does not constitute formal certification or regulatory warranty of food safety. "
    "Receiving organizations must perform sensory inspection and temperature checks prior to serving."
)

CATEGORY_MAX_WINDOW_HOURS = {
    "Cooked Meals": {
        "Hot-hold (>60°C)": 6.0,
        "Chilled (0-4°C)": 24.0,
        "Room Temp (20-25°C)": 4.0,
        "Frozen (<-18°C)": 72.0,
        "_default": 4.0
    },
    "Perishable Dairy": {
        "Chilled (0-4°C)": 12.0,
        "Frozen (<-18°C)": 48.0,
        "_default": 2.0  # dairy at room temp degrades quickly
    },
    "Bakery": {
        "Room Temp (20-25°C)": 36.0,
        "Chilled (0-4°C)": 48.0,
        "_default": 36.0
    },
    "Raw Produce": {
        "Room Temp (20-25°C)": 48.0,
        "Chilled (0-4°C)": 96.0,
        "_default": 48.0
    },
    "Packaged": {
        "Room Temp (20-25°C)": 72.0,
        "Chilled (0-4°C)": 72.0,
        "_default": 72.0
    }
}

def parse_iso_or_local(dt_str):
    if not dt_str:
        return None
    try:
        dt = dateutil.parser.parse(str(dt_str))
        # Remove tzinfo to do naive comparison if user enters naive local time
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt
    except Exception:
        # Fallback manual formats
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(dt_str), fmt)
            except ValueError:
                continue
    return None

def validate_food_safety(
    food_name: str,
    food_category: str,
    prep_time_raw: str,
    collection_deadline_raw: str,
    storage_condition: str,
    allergens: list or str = None,
    evaluation_time: datetime = None
) -> dict:
    """
    Validates donation against food safety screening rules.
    Returns:
        dict: {
            'is_safe': bool,
            'status': 'Valid' | 'Rejected',
            'reasons': list of rejection reasons,
            'warnings': list of cautionary notices,
            'window_limit_hours': float,
            'elapsed_since_prep_hours': float,
            'remaining_until_deadline_hours': float,
            'disclaimer': str
        }
    """
    reasons = []
    warnings = []
    now = evaluation_time or datetime.now()

    # 1. Check required fields
    if not food_name or not str(food_name).strip():
        reasons.append("Food name cannot be empty.")
    
    prep_dt = parse_iso_or_local(prep_time_raw)
    deadline_dt = parse_iso_or_local(collection_deadline_raw)

    if not prep_dt:
        reasons.append("Invalid or missing preparation timestamp.")
    if not deadline_dt:
        reasons.append("Invalid or missing collection deadline timestamp.")

    if prep_dt and deadline_dt:
        if deadline_dt <= prep_dt:
            reasons.append("Collection deadline must be chronologically after the preparation time.")
        
        # Check if already expired relative to now
        if deadline_dt < now:
            reasons.append(f"Collection deadline has already elapsed (expired at {deadline_dt.strftime('%Y-%m-%d %H:%M')}).")
        
        # Check if prep time is in future
        if prep_dt > now:
            warnings.append("Preparation timestamp is logged in the future (scheduled batch prep).")

    # 2. Category and Storage Condition Rules
    category_rules = CATEGORY_MAX_WINDOW_HOURS.get(food_category, None)
    if not category_rules:
        warnings.append(f"Unrecognized food category '{food_category}'. Evaluated against generic safe window of 4 hours.")
        max_allowed_hours = 4.0
    else:
        max_allowed_hours = category_rules.get(storage_condition, category_rules.get("_default", 4.0))

    elapsed_hours = 0.0
    remaining_hours = 0.0

    if prep_dt:
        elapsed_delta = (now - prep_dt).total_seconds()
        elapsed_hours = round(max(0.0, elapsed_delta / 3600.0), 2)
    
    if deadline_dt:
        remaining_delta = (deadline_dt - now).total_seconds()
        remaining_hours = round(max(0.0, remaining_delta / 3600.0), 2)

    if prep_dt and deadline_dt:
        total_lifespan_hours = (deadline_dt - prep_dt).total_seconds() / 3600.0
        if total_lifespan_hours > max_allowed_hours:
            reasons.append(
                f"Collection deadline exceeds the safe window for {food_category} under '{storage_condition}'. "
                f"Maximum allowed window is {max_allowed_hours} hours, but requested window is {round(total_lifespan_hours, 1)} hours."
            )

    # 3. Specific Critical Temperature & Storage Incompatibilities
    if food_category == "Cooked Meals" and storage_condition == "Room Temp (20-25°C)":
        if elapsed_hours > 4.0:
            reasons.append("Cooked meals stored at room temperature (temperature danger zone) must be collected within 4 hours of preparation.")
        else:
            warnings.append("Cooked meals stored at room temperature are in the danger zone. Urgent collection required.")

    if food_category == "Perishable Dairy" and storage_condition in ("Room Temp (20-25°C)", "Hot-hold (>60°C)"):
        reasons.append("Perishable dairy items (paneer, milk, curd, desserts) require active refrigeration (0-4°C) or freezing.")

    # 4. Allergen screening
    if allergens is None or (isinstance(allergens, list) and len(allergens) == 0) or allergens == "":
        warnings.append("No allergen declarations logged. Food items must be screened for major allergens (dairy, nuts, gluten, soy).")

    is_safe = (len(reasons) == 0)
    status = "Valid" if is_safe else "Rejected"

    return {
        "is_safe": is_safe,
        "status": status,
        "reasons": reasons,
        "warnings": warnings,
        "window_limit_hours": max_allowed_hours,
        "elapsed_since_prep_hours": elapsed_hours,
        "remaining_until_deadline_hours": remaining_hours,
        "disclaimer": SAFETY_DISCLAIMER
    }
