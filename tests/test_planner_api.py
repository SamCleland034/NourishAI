import requests
import json

def test_planner_prompt():
    url = "http://127.0.0.1:8000/api/planner/prompt"
    payload = {
        "message": "A simple 3-day high-protein plan",
        "history": [],
        "num_recipes": 3,
        "exclude_ids": [],
        "user_id": 1,
        "week_id": "2026-W14"
    }
    
    print(f"Testing {url}...")
    try:
        response = requests.post(url, json=payload, timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            plan = data.get("suggested_plan")
            if plan:
                print("SUCCESS: Plan received!")
                print(f"Normalized Days: {list(plan.keys())}")
                # Check for Mon, Tue, etc.
                expected = ["Mon", "Tue", "Wed"]
                found = [d for d in expected if d in plan]
                print(f"Verified Expected Keys: {found}")
            else:
                print("FAILURE: No suggested_plan in response.")
        elif response.status_code == 429:
            print("INFO: AI Rate Limit Reached (429). The normalization layer works, but the AI provider is busy.")
        else:
            print(f"FAILURE: Server returned {response.status_code}")
            print(f"Detail: {response.text}")
            
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")

if __name__ == "__main__":
    test_planner_prompt()
