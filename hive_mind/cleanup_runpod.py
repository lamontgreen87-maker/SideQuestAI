"""
RunPod Emergency Cleanup Script
Terminates ALL active pods to prevent account drain.
Run this whenever you're done testing or before going to sleep.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("RUNPOD_API_KEY")
GRAPHQL_URL = f"https://api.runpod.io/graphql?api_key={API_KEY}"

def terminate_all_pods():
    """Terminate all active pods on the account."""
    
    # Query for all pods
    query = """
    {
      myself {
        pods {
          id
          name
          desiredStatus
        }
      }
    }
    """
    
    resp = requests.post(GRAPHQL_URL, json={'query': query})
    data = resp.json()
    
    if 'errors' in data:
        print(f"Error querying pods: {data['errors']}")
        return
    
    pods = data['data']['myself']['pods']
    
    if not pods:
        print("✅ No active pods found. Account is clean.")
        return
    
    print(f"Found {len(pods)} active pod(s). Terminating...")
    
    for pod in pods:
        pod_id = pod['id']
        pod_name = pod['name']
        
        # Terminate the pod
        terminate_mutation = f"""
        mutation {{
          podTerminate(input: {{ podId: "{pod_id}" }})
        }}
        """
        
        term_resp = requests.post(GRAPHQL_URL, json={'query': terminate_mutation})
        term_data = term_resp.json()
        
        if 'errors' in term_data:
            print(f"❌ Failed to terminate {pod_name} ({pod_id}): {term_data['errors']}")
        else:
            print(f"✅ Terminated: {pod_name} ({pod_id})")
    
    print("\n🛡️ Cleanup complete. Run rate: $0/hr")

if __name__ == "__main__":
    print("🚨 RunPod Emergency Cleanup")
    print("=" * 50)
    terminate_all_pods()
