"""
Stop Brain - Terminate the persistent 72B pod
Run this at the end of your work session to stop billing.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("RUNPOD_API_KEY")
GRAPHQL_URL = f"https://api.runpod.io/graphql?api_key={API_KEY}"

POD_NAME = "hive-brain-persistent"

def find_persistent_pod():
    """Find the persistent brain pod."""
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
    resp = requests.post(GRAPHQL_URL, json={'query': query})
    data = resp.json()
    
    if 'errors' in data:
        print(f"Error checking pods: {data['errors']}")
        return None, None
    
    pods = data['data']['myself']['pods']
    for pod in pods:
        if pod['name'] == POD_NAME:
            return pod['id'], pod.get('costPerHr', 0)
    
    return None, None

def terminate_pod(pod_id):
    """Terminate the pod."""
    mutation = f"""
    mutation {{
      podTerminate(input: {{ podId: "{pod_id}" }})
    }}
    """
    
    resp = requests.post(GRAPHQL_URL, json={'query': mutation})
    data = resp.json()
    
    if 'errors' in data:
        print(f"Error terminating pod: {data['errors']}")
        return False
    
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("🧠 HIVE BRAIN - STOP SEQUENCE")
    print("=" * 60)
    
    # Find the pod
    pod_id, cost_per_hr = find_persistent_pod()
    
    if not pod_id:
        print(f"\n✅ No persistent pod found")
        print(f"   Account is already at $0/hr")
        exit(0)
    
    print(f"\nFound pod: {pod_id}")
    print(f"Current cost: ${cost_per_hr}/hr")
    
    # Terminate
    print(f"\n🛑 Terminating pod...")
    if terminate_pod(pod_id):
        print(f"✅ Pod terminated successfully")
        print(f"   Account burn rate: $0/hr")
        print(f"\n💡 Run `python start_brain.py` when you need it again")
    else:
        print(f"❌ Failed to terminate pod")
        print(f"   Try running `python cleanup_runpod.py` for emergency cleanup")
