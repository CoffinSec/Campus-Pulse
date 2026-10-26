import os

import httpx
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'").strip()

print("Checking which models are available on your key...")
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
r = httpx.get(url, timeout=12)

if r.status_code == 200:
    all_models = [
        m["name"].replace("models/", "")
        for m in r.json().get("models", [])
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]
    print(f"Found {len(all_models)} available models: {all_models[:8]}...")
else:
    print(f"List models error: {r.status_code}")
    all_models = ["gemini-3.8-flash", "gemini-1.5-flash-8b", "gemini-1.5-pro", "gemini-2.0-flash-exp", "gemma-2-27b-it"]

# Test models until one responds with 200 OK
for m in all_models:
    print(f"\nPinging {m}...", end=" ")
    try:
        res = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}",
            json={"contents": [{"parts": [{"text": 'Respond with ONLY: {"status": "ok"}'}]}]},
            timeout=10,
        )
        if res.status_code == 200:
            print(f"✅ 200 OK! {m} is live and responding!")
            print(f"\n>>> BEST ACTIVE MODEL TO USE: {m} <<<")
            break
        else:
            print(f"HTTP {res.status_code} ({res.json().get('error', {}).get('message', '')[:60]})")
    except (httpx.HTTPError, ValueError) as e:
        print(f"Error: {e}")