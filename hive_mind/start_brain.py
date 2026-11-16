"""
Start Brain - Launch the persistent 72B pod
Run this once at the start of your work session.
"""

import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("RUNPOD_API_KEY")
TEMPLATE_ID = os.getenv("RUNPOD_TEMPLATE_ID")
VOLUME_ID = os.getenv("RUNPOD_VOLUME_ID")
DATACENTER_ID = os.getenv("RUNPOD_DATACENTER_ID")
GRAPHQL_URL = f"https://api.runpod.io/graphql?api_key={API_KEY}"

POD_NAME = "hive-brain-persistent"

def check_existing_pod():
    """Check if a persistent pod is already running."""
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
        print(f"Error checking pods: {data['errors']}")
        return None
    
    pods = data['data']['myself']['pods']
    for pod in pods:
        if pod['name'] == POD_NAME:
            return pod['id']
    
    return None

def launch_pod():
    """Launch the persistent brain pod."""
    print(f"🚀 Launching {POD_NAME}...")
    print(f"   Region: {DATACENTER_ID}")
    print(f"   Volume: {VOLUME_ID}")
    
    # Try GPU types in order of preference
    gpu_types = [
        "NVIDIA A100-SXM4-80GB",
        "NVIDIA A100 80GB PCIe",
        "NVIDIA RTX A6000",
        "NVIDIA RTX 6000 Ada Generation"
    ]
    
    for gpu_type in gpu_types:
        print(f"\n   Trying: {gpu_type}...")
        
        mutation = """
        mutation {
          podFindAndDeployOnDemand(
            input: {
              dataCenterId: "%s"
              gpuCount: 1
              gpuTypeId: "%s"
              name: "%s"
              imageName: "vllm/vllm-openai:latest"
              templateId: "%s"
              networkVolumeId: "%s"
              dockerArgs: "--model /model/qwen2.5-72b-instruct --tensor-parallel-size 1 --gpu-memory-utilization 0.95 --port 8000"
            }
          ) {
            id
            imageName
            costPerHr
          }
        }
        """ % (DATACENTER_ID, gpu_type, POD_NAME, TEMPLATE_ID, VOLUME_ID)
        
        resp = requests.post(GRAPHQL_URL, json={'query': mutation})
        data = resp.json()
        
        if 'errors' in data:
            err_msg = data['errors'][0].get('message', '')
            if "no longer any instances available" in err_msg:
                print(f"   ❌ Out of stock")
                continue
            else:
                print(f"   ⚠️ Error: {err_msg}")
                continue
        
        if data.get('data') and data['data'].get('podFindAndDeployOnDemand'):
            pod_data = data['data']['podFindAndDeployOnDemand']
            pod_id = pod_data['id']
            cost = pod_data.get('costPerHr', 0)
            print(f"\n✅ Pod launched successfully!")
            print(f"   Pod ID: {pod_id}")
            print(f"   GPU: {gpu_type}")
            print(f"   Cost: ${cost}/hr")
            return pod_id
    
    print("\n❌ Failed to launch pod - all GPU types unavailable in region")
    return None

def wait_for_health(pod_id):
    """Wait for vLLM to be ready."""
    print(f"\n⏳ Waiting for vLLM to initialize...")
    print(f"   This takes ~5-6 minutes on first start (downloading image + loading model)")
    
    for i in range(120):  # 10 minutes max
        # Get pod IP
        query = f"""
        {{
          pod(input: {{ podId: "{pod_id}" }}) {{
            runtime {{
              ports {{
                ip
                isIpPublic
                privatePort
                publicPort
              }}
            }}
          }}
        }}
        """
        
        resp = requests.post(GRAPHQL_URL, json={'query': query})
        data = resp.json()
        
        if data.get('data') and data['data'].get('pod'):
            ports = data['data']['pod'].get('runtime', {}).get('ports', [])
            for port in ports:
                if port.get('privatePort') == 8000:
                    ip = port.get('ip')
                    public_port = port.get('publicPort')
                    
                    if ip and public_port:
                        # Try health check
                        try:
                            health_url = f"http://{ip}:{public_port}/health"
                            health_resp = requests.get(health_url, timeout=2)
                            if health_resp.status_code == 200:
                                print(f"\n✅ Brain is online and ready!")
                                print(f"   Endpoint: http://{ip}:{public_port}")
                                return f"http://{ip}:{public_port}"
                        except:
                            pass
        
        # Progress indicator
        if i % 10 == 0:
            print(f"   {i * 5}s elapsed...")
        time.sleep(5)
    
    print("\n⚠️ Health check timeout - pod may still be initializing")
    print("   Run `python status_brain.py` to check status")
    return None

if __name__ == "__main__":
    print("=" * 60)
    print("🧠 HIVE BRAIN - START SEQUENCE")
    print("=" * 60)
    
    # Check if already running
    existing_pod = check_existing_pod()
    if existing_pod:
        print(f"\n⚠️ Pod already running: {existing_pod}")
        print(f"   Run `python status_brain.py` to check status")
        print(f"   Run `python stop_brain.py` to terminate it first")
        exit(0)
    
    # Launch new pod
    pod_id = launch_pod()
    if not pod_id:
        exit(1)
    
    # Wait for health
    endpoint = wait_for_health(pod_id)
    
    if endpoint:
        print(f"\n🎯 Ready for requests!")
        print(f"   The dashboard will now use the remote 72B brain")
        print(f"   Run `python stop_brain.py` when done to stop billing")
    else:
        print(f"\n⚠️ Pod launched but health check incomplete")
        print(f"   Check status in a few minutes with `python status_brain.py`")
