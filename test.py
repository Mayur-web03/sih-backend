import requests
import json

ADDRESS = "bc1qy4ra9luzrm5695r8qvpwglum5lsukpx7nd3eju"

url = f"https://mempool.space/api/address/{ADDRESS}"

response = requests.get(url, timeout=30)

print("HTTP Status:", response.status_code)

if response.status_code != 200:
    print(response.text)
    exit()

data = response.json()

print(json.dumps(data, indent=2)) 