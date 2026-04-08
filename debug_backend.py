import httpx
import asyncio

async def test_backend():
    url = "http://localhost:8000/mcp/execute"
    payload = {
        "action": "generate_learning_path",
        "input": {"topic": "Python"}
    }
    print(f"Testing connectivity to {url}...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload)
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Connectivity Error: {e}")

if __name__ == "__main__":
    try:
        import httpx
        print("httpx is installed.")
    except ImportError:
        print("httpx is NOT installed.")
    
    asyncio.run(test_backend())
