import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("RUNPOD_API_KEY")
GRAPHQL_URL = f"https://api.runpod.io/graphql?api_key={API_KEY}"

def test_api():
    url = f"https://api.runpod.io/graphql?api_key={API_KEY}"
    
    print("\n--- FORENSIC POD CHECK ---")
    query = """
    {
      myself {
        pods {
          id
          name
          desiredStatus
          costPerHr
        }
      }
    }
    """
    resp = requests.post(url, json={'query': query})
    try:
        data = resp.json()
        if 'errors' in data:
            print(f"API Error: {data['errors']}")
            return

        pods = data['data']['myself']['pods']
        if not pods:
            print("No active pods found (Clean Scale).")
        
        total_cost = 0
        for p in pods:
            status = p.get('runtime', {}).get('status', 'UNKNOWN')
            cost = p.get('costPerHr', 0)
            total_cost += cost
            print(f"POD: {p['id']} | Name: {p['name']} | Status: {status} | Cost: ${cost}/hr")
            
        print(f"\nTOTAL ACTIVE RUN RATE: ${total_cost}/hr")

    except Exception as e:
        print(f"Error: {e}")
        print(resp.json())

if __name__ == "__main__":
    test_api()
