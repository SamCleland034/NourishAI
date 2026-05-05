import httpx
import json

def test_search():
    url = "http://127.0.0.1:8000/api/recipes/search"
    payload = {"query": "chicken", "limit": 5}
    try:
        response = httpx.post(url, json=payload, timeout=10.0)
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_search()
