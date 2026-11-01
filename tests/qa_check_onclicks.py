"""
QA Tool: Verify all inline onclick and event handlers in index.html exist in JS files
"""
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

with open(BASE_DIR / 'templates' / 'index.html', 'r', encoding='utf-8') as f:
    html_content = f.read()

# Find onclick calls
onclicks = re.findall(r'onclick=["\']([a-zA-Z0-9_]+)\(', html_content)
print(f"Total onclick functions called: {len(onclicks)} (Unique: {len(set(onclicks))})")

# Read all JS files
all_js = ""
for js_path in ['static/js/app.js', 'static/js/dashboard.js', 'static/js/map.js']:
    with open(BASE_DIR / js_path, 'r', encoding='utf-8') as f:
        all_js += f.read() + "\n"

# Check each function
missing_funcs = set()
for func in set(onclicks):
    # Check if defined as function func( or func =
    pattern = rf'(function\s+{func}\b|window\.{func}\b|const\s+{func}\s*=|let\s+{func}\s*=|var\s+{func}\s*=)'
    if not re.search(pattern, all_js):
        missing_funcs.add(func)

if missing_funcs:
    print(f"MISSING functions called in HTML onclick: {missing_funcs}")
else:
    print("All onclick functions verified in JS files!")
