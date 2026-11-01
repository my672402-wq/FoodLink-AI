"""
QA Tool: Verify all DOM IDs referenced in JS files exist in templates/index.html
"""
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

with open(BASE_DIR / 'templates' / 'index.html', 'r', encoding='utf-8') as f:
    html_content = f.read()

html_ids = set(re.findall(r'id=["\']([^"\']+)["\']', html_content))

js_files = ['static/js/app.js', 'static/js/dashboard.js', 'static/js/map.js']

print(f"Total HTML IDs found: {len(html_ids)}")

for js_path in js_files:
    full_path = BASE_DIR / js_path
    if not full_path.exists():
        continue
    with open(full_path, 'r', encoding='utf-8') as f:
        js_content = f.read()
    
    js_ids = set(re.findall(r'getElementById\(["\']([^"\']+)["\']\)', js_content))
    missing = js_ids - html_ids
    print(f"\n[{js_path}]")
    print(f"  Referenced IDs: {len(js_ids)}")
    if missing:
        print(f"  MISSING in HTML: {missing}")
    else:
        print(f"  All IDs verified in HTML! (0 missing)")
