import httpx

if __name__ == "__main__":
    response = httpx.get("http://127.0.0.1:8000/health", timeout=5)
    response.raise_for_status()
    print(response.json())
