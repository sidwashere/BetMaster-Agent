import requests
import json
import time

url = "http://localhost:11434/api/generate"
payload = {
    "model": "llama3",
    "prompt": "Say hello in JSON format like {'message': 'hello'}",
    "stream": False,
    "format": "json"
}

start = time.time()
try:
    print(f"Testing Ollama at {url}...")
    res = requests.post(url, json=payload, timeout=5)
    print(f"Status: {res.status_code}")
    print(f"Response: {res.text}")
    print(f"Time: {time.time() - start:.2f}s")
except Exception as e:
    print(f"Failed: {e}")
