import requests
import json

def test_vix():
    print("Testing /api/vix...")
    try:
        r = requests.get("http://localhost:8000/api/vix?timeframe=5m&limit=10")
        print(f"Status: {r.status_code}")
        if r.ok:
            data = r.json()
            print(f"Data length: {len(data)}")
            if data:
                print(f"First item: {data[0]}")
                print(f"Last item: {data[-1]}")
    except Exception as e:
        print(f"Error: {e}")

    print("\nTesting /api/vix/live...")
    try:
        r = requests.get("http://localhost:8000/api/vix/live")
        print(f"Status: {r.status_code}")
        if r.ok:
            print(f"Data: {r.json()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_vix()
