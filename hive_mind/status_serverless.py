"""
Check Serverless Endpoint Status
Shows endpoint health and configuration.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

def check_serverless_status():
    """Check serverless endpoint status."""
    
    print("=" * 60)
    print("SERVERLESS ENDPOINT STATUS")
    print("=" * 60)
    
    endpoint_id = os.getenv("RUNPOD_SERVERLESS_ENDPOINT_ID")
    api_key = os.getenv("RUNPOD_API_KEY")
    
    if not endpoint_id or not api_key:
        print("\n❌ Missing configuration")
        print("Required in .env:")
        print("  RUNPOD_SERVERLESS_ENDPOINT_ID")
        print("  RUNPOD_API_KEY")
        return
    
    print(f"\nEndpoint ID: {endpoint_id}")
    
    # Check endpoint health
    try:
        url = f"https://api.runpod.ai/v2/{endpoint_id}/health"
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"}
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ Endpoint is healthy")
            print(f"Workers: {data.get('workers', 'Unknown')}")
            print(f"Jobs in queue: {data.get('jobs', {}).get('inQueue', 0)}")
            print(f"Jobs in progress: {data.get('jobs', {}).get('inProgress', 0)}")
        else:
            print(f"\n⚠️ Health check returned: {response.status_code}")
            print(f"Response: {response.text}")
    
    except Exception as e:
        print(f"\n❌ Error checking status: {str(e)}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    check_serverless_status()
