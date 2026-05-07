import requests
import traceback

def test():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        response = requests.get(url, headers=headers, timeout=10)
        print(response.status_code)
        print(len(response.text))
    except Exception as e:
        print(f"Exception: {repr(e)}")

test()
