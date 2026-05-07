import asyncio
import aiohttp
import traceback

async def test():
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
        async with aiohttp.ClientSession(headers=headers) as session:
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            async with session.get(url, timeout=10) as response:
                print(response.status)
                print(await response.text())
    except Exception as e:
        print(f"Exception: {repr(e)}")

asyncio.run(test())
