"""
QA Tool: Check all button IDs in index.html and verify if they have event listeners or onclicks
"""
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

with open(BASE_DIR / 'templates' / 'index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Find all buttons
button_tags = re.findall(r'<button\b[^>]*>', html)

all_js = ""
for js_path in ['static/js/app.js', 'static/js/dashboard.js', 'static/js/map.js']:
    with open(BASE_DIR / js_path, 'r', encoding='utf-8') as f:
        all_js += f.read() + "\n"

print(f"Total buttons in HTML: {len(button_tags)}")
unbound = []
for btn in button_tags:
    id_match = re.search(r'id=["\']([^"\']+)["\']', btn)
    onclick_match = re.search(r'onclick=["\']([^"\']+)["\']', btn)
    btn_id = id_match.group(1) if id_match else None
    
    if btn_id:
        # Check if id appears in JS
        in_js = btn_id in all_js
        has_onclick = bool(onclick_match)
        if not in_js and not has_onclick:
            unbound.append((btn_id, btn))

print(f"\nUnbound buttons (has ID, but neither referenced in JS nor has onclick): {len(unbound)}")
for b_id, tag in unbound:
    print(f"  - ID: {b_id} | Tag: {tag}")
