import httpx # Use async library
from typing import Dict, Any

ERGAST_API_URL = "https://ergast.com/api/f1/current/driverStandings.json" # More specific URL

async def get_f1_standings() -> Dict[str, Any]:
    """Fetches the current F1 driver standings from the Ergast API asynchronously."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(ERGAST_API_URL, timeout=10.0)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            return response.json()
        except httpx.RequestError as exc:
            print(f"An error occurred while requesting {exc.request.url!r}: {exc}")
            raise # Re-raise the exception to be handled upstream
        except httpx.HTTPStatusError as exc:
            print(f"Error response {exc.response.status_code} while requesting {exc.request.url!r}: {exc.response.text}")
            raise # Re-raise the exception

# Example usage (optional, for testing this file directly)
# import asyncio
# if __name__ == "__main__":
#     async def run_test():
#         try:
#             standings = await get_f1_standings()
#             print(standings)
#         except Exception as e:
#             print(f"Test failed: {e}")
#     asyncio.run(run_test())
