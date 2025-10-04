# app/diag_polygon.py
import os, json, sys, asyncio
import httpx

API = "https://api.polygon.io"

def show_key():
    k = os.getenv("POLYGON_API_KEY", "")
    print("Key length:", len(k))
    print("First 4 / Last 4:", k[:4], "...", k[-4:] if len(k) >= 4 else "")
    print("Has spaces:", any(c.isspace() for c in k))
    # Show codepoints of first few chars to detect hidden characters
    print("First 6 codepoints:", [ord(c) for c in k[:6]])

async def test_aggs():
    key = os.getenv("POLYGON_API_KEY", "")
    url = f"{API}/v2/aggs/ticker/AAPL/range/1/day/2025-10-01/2025-10-03"
    params = {"adjusted":"true", "sort":"asc", "limit": 5, "apiKey": key}
    async with httpx.AsyncClient(timeout=15) as x:
        r = await x.get(url, params=params)
    print("AGGS status:", r.status_code)
    try:
        print("AGGS body (first 200):", r.text[:200])
    except Exception:
        pass

async def main():
    print("== Polygon Key Check ==")
    show_key()
    print("\n== Aggs Endpoint Check ==")
    await test_aggs()

if __name__ == "__main__":
    asyncio.run(main())
