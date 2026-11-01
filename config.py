import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)

# Load environment variables from .env if present
load_dotenv(BASE_DIR / ".env")

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "foodlink-ai-hackathon-insecure-key-2026")
    DATABASE_PATH = os.getenv("DATABASE_PATH", str(INSTANCE_DIR / "foodlink.db"))
    
    # Gemini AI configuration
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    
    # OSRM routing configuration
    OSRM_BASE_URL = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org")
    OSRM_TIMEOUT = int(os.getenv("OSRM_TIMEOUT", "4")) # 4 seconds timeout for API fallback
    
    # Matching Engine Weights (Sum = 1.0)
    MATCH_WEIGHT_DISTANCE = 0.30
    MATCH_WEIGHT_QUANTITY = 0.25
    MATCH_WEIGHT_URGENCY = 0.20
    MATCH_WEIGHT_DIETARY = 0.15
    MATCH_WEIGHT_CAPACITY = 0.10
    
    # Food Safety Rules configuration
    # Maximum safe consumption/collection window from prep_time (in hours) by category
    SHELF_LIFE_HOURS = {
        "Cooked Meals": 4,          # Hot or ambient cooked food max 4 hrs
        "Cooked Meals (Chilled)": 24,# Cooked food rapidly cooled & chilled (0-4°C)
        "Perishable Dairy": 12,     # Fresh paneer, milk desserts, curd
        "Bakery": 36,               # Bread, rolls, buns
        "Raw Produce": 48,          # Vegetables, fruits
        "Packaged": 72              # Sealed packaged goods with intact seals
    }
    
    # Valid storage conditions
    STORAGE_CONDITIONS = [
        "Hot-hold (>60°C)",
        "Chilled (0-4°C)",
        "Room Temp (20-25°C)",
        "Frozen (<-18°C)"
    ]
