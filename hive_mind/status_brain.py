"""
Status Brain - Check the persistent 72B pod status
Quick status check to see if the brain is online and how much it's costing.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("RUNPOD_API_KEY")
GRAPHQL_URL = f"https://api.runpod.io/graphql?api_key={API_KEY}"

POD_NAME = "hive-brain-persistent"

def check_status():
    """Check pod status and health."""
    query = """
    {
      myself {
        pods {
          id
          name
          desiredStatus
          costPerHr
          runtime {
            ports {
              ip
              isIpPublic
              privatePort
              publicPort
            }
          }
        }
      }
    }
    """
    resp = requests.post(GRAPHQL_URL, json={'query': query})
    data = resp.json()
    
    if 'errors' in data:
        print(f"Error checking status: {data['errors']}")
        return
    
    pods = data['data']['myself']['pods']
    persistent_pod = None
    
    for pod in pods:
        if pod['name'] == POD_NAME:
            persistent_pod = pod
            break
    
    if not persistent_pod:
        print(f"❌ Brain is OFFLINE")
        print(f"   Run `python start_brain.py` to launch it")
        return
    
    # Pod exists
    pod_id = persistent_pod['id']
    cost = persistent_pod.get('costPerHr', 0)
    status = persistent_pod.get('desiredStatus', 'UNKNOWN')
    
    print(f"✅ Brain is ONLINE")
    print(f"   Pod ID: {pod_id}")
    print(f"   Status: {status}")
    print(f"   Cost: ${cost}/hr")
    
    # Check for endpoint
    ports = persistent_pod.get('runtime', {}).get('ports', [])
    for port in ports:
        if port.get('privatePort') == 8000:
            ip = port.get('ip')
            public_port = port.get('publicPort')
            if ip and public_port:
                endpoint = f"http://{ip}:{public_port}"
                print(f"   Endpoint: {endpoint}")
                
                # Try health check
                try:
                    health_resp = requests.get(f"{endpoint}/health", timeout=2)
                    if health_resp.status_code == 200:
                        print(f"   Health: ✅ Ready")
                    else:
                        print(f"   Health: ⚠️ Not ready yet")
                except:
                    print(f"   Health: ⚠️ Initializing...")
                
                return
    
    print(f"   Endpoint: ⏳ Waiting for IP assignment...")

if __name__ == "__main__":
    print("=" * 60)
    print("🧠 HIVE BRAIN - STATUS CHECK")
    print("=" * 60)
    print()
    check_status()
