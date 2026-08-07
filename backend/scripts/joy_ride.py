"""Take arctic_express for a joy ride via the REST API."""

import asyncio

import aiohttp

BASE = "http://localhost:8080"
TRAIN = "arctic_express"


async def set_speed(session: aiohttp.ClientSession, speed: int) -> None:
    resp = await session.post(f"{BASE}/trains/{TRAIN}/speed", json={"speed": speed})
    data = await resp.json()
    print(f"  speed={speed:>4d}  success={data.get('success')}")


async def main() -> None:
    lap = 0
    async with aiohttp.ClientSession() as session:
        while True:
            lap += 1
            print(f"\n--- Lap {lap} ---")

            print("Cruising at 50...")
            await set_speed(session, 50)
            await asyncio.sleep(20)

            print("Full throttle!")
            await set_speed(session, 100)
            await asyncio.sleep(20)

            print("Braking...")
            await set_speed(session, 0)
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
