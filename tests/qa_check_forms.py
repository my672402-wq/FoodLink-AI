"""
QA Tool: Check all form IDs and verify submit listeners
"""
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

with open(BASE_DIR / 'templates' / 'index.html', 'r', encoding='utf-8') as f:
    html = f.read()

forms = re.findall(r'<form\b[^>]*>', html)
all_js = ""
for js_path in ['static/js/app.js', 'static/js/dashboard.js', 'static/js/map.js']:
    with open(BASE_DIR / js_path, 'r', encoding='utf-8') as f:
        all_js += f.read() + "\n"

print(f"Total forms in HTML: {len(forms)}")
for f_tag in forms:
    id_match = re.search(r'id=["\']([^"\']+)["\']', f_tag)
    f_id = id_match.group(1) if id_match else "NO_ID"
    in_js = f_id in all_js
    print(f"  Form: {f_id} -> bound in JS: {in_js}")
