import os
import requests
import json
from dotenv import load_dotenv

# Load secrets
load_dotenv()

class RunPodOrchestrator:
    """
    Phase 2: The Brain Management (Direct GraphQL version).
    Handles automated spin-up and spin-down of 72B GPU nodes without SDK dependencies.
    """
    def __init__(self):
        # Detect mode: serverless or persistent
        self.mode = os.getenv("RUNPOD_MODE", "persistent")  # Default to persistent
        
        # Persistent pod config
        self.template_id = os.getenv("RUNPOD_TEMPLATE_ID")
        self.volume_id = os.getenv("RUNPOD_VOLUME_ID")
        self.datacenter_id = os.getenv("RUNPOD_DATACENTER_ID")
        self.current_pod_id = None
        
        # Serverless config
        self.serverless_endpoint_id = os.getenv("RUNPOD_SERVERLESS_ENDPOINT_ID")
        self.serverless_url = os.getenv("RUNPOD_SERVERLESS_URL")
        
        # Health check
        api_key = os.getenv("RUNPOD_API_KEY")
        if not api_key:
            print("[RunPod] CRITICAL ERROR: RUNPOD_API_KEY not found in .env")
        else:
            if self.mode == "serverless":
                print(f"[RunPod] Serverless Mode. Endpoint: {self.serverless_endpoint_id}")
            else:
                print(f"[RunPod] Persistent Mode. Template: {self.template_id} Region: {self.datacenter_id}")

    def _get_graphql_config(self):
        # Force reload from .env to catch any runtime changes
        load_dotenv(override=True)
        api_key = os.getenv("RUNPOD_API_KEY")
        if not api_key:
            print("[RunPod] ERROR: No API Key found in environment!")
            return None
        
        # Masked key for logs
        masked_key = f"{api_key[:4]}...{api_key[-4:]}"
        print(f"[RunPod] Handshaking with key: {masked_key}")
        
        return f"https://api.runpod.io/graphql?api_key={api_key}"

    def get_persistent_brain_ip(self):
        """
        Check if the persistent brain pod is running and return its IP.
        Does NOT launch a new pod - user must run start_brain.py manually.
        """
        graphql_url = self._get_graphql_config()
        
        # Query for pods with the persistent name
        query = """
        {
          myself {
            pods {
              id
              name
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
        
        try:
            response = requests.post(graphql_url, json={'query': query})
            data = response.json()
            
            if 'errors' in data:
                print(f"[RunPod] Error checking persistent pod: {data['errors']}")
                return None
            
            pods = data['data']['myself']['pods']
            for pod in pods:
                if pod['name'] == 'hive-brain-persistent':
                    # Found the persistent pod
                    ports = pod.get('runtime', {}).get('ports', [])
                    for port in ports:
                        if port.get('privatePort') == 8000:
                            ip = port.get('ip')
                            public_port = port.get('publicPort')
                            if ip and public_port:
                                endpoint = f"http://{ip}:{public_port}"
                                print(f"[RunPod] Persistent brain found: {endpoint}")
                                return endpoint
                    
                    print(f"[RunPod] Persistent pod found but no IP yet (still initializing)")
                    return None
            
            print(f"[RunPod] No persistent brain pod found")
            return None
            
        except Exception as e:
            print(f"[RunPod] Exception checking persistent pod: {str(e)}")
            return None

    def ignite_72b(self, primary_gpu="NVIDIA RTX 6000 Ada Generation"):
        """
        Wakes the 'Big Brain' on RunPod with resilient GPU fallback.
        """
        graphql_url = self._get_graphql_config()
        print(f"[RunPod] IGNITION SEQUENCE START...")

        # Fallback list of powerful GPUs common in European datacenters
        gpu_fallback_list = [
            primary_gpu,
            "NVIDIA A100-SXM4-80GB", # Verified IN STOCK (EUR-IS-1)
            "NVIDIA A100 80GB PCIe",
            "NVIDIA RTX A6000",
            "NVIDIA RTX A5000",
            "NVIDIA RTX 5000 Ada Generation"
        ]

        for gpu_type in gpu_fallback_list:
            print(f"[RunPod] Attempting ignition with: {gpu_type}...")
            
            # Refactor query to use proper dataCenterId binding
            query = """
            mutation {
              podFindAndDeployOnDemand(
                input: {
                  dataCenterId: "%s"
                  gpuCount: 1
                  gpuTypeId: "%s"
                  name: "Hive-Mind-72B-Brain"
                  imageName: "vllm/vllm-openai:latest"
                  templateId: "%s"
                  networkVolumeId: "%s"
                  dockerArgs: "--model /model/qwen2.5-72b-instruct --tensor-parallel-size 1 --gpu-memory-utilization 0.95 --port 8000"
                  env: [
                    { key: "HUGGING_FACE_HUB_TOKEN", value: "YOUR_HF_TOKEN_IF_NEEDED" }
                  ]
                }
              ) {
                id
                imageName
                machineId
              }
            }
            """ % (self.datacenter_id, gpu_type, self.template_id, self.volume_id)

            try:
                response = requests.post(graphql_url, json={'query': query})
                data = response.json()
                
                if 'errors' in data:
                    err_msg = data['errors'][0].get('message', 'Unknown Error')
                    print(f"[RunPod] {gpu_type} rejected: {err_msg}")
                    continue

                if not data.get('data') or not data['data'].get('podFindAndDeployOnDemand'):
                    print(f"[RunPod] {gpu_type} failed (No data).")
                    continue

                pod_data = data['data']['podFindAndDeployOnDemand']
                self.current_pod_id = pod_data['id']
                print(f"[RunPod] SUCCESS: Brain Ignited on {gpu_type}. Pod ID: {self.current_pod_id}")
                return self.current_pod_id
                
            except Exception as e:
                print(f"[RunPod] {gpu_type} Exception: {str(e)}")
                continue

        print("[RunPod] CRITICAL: All GPU ignition attempts failed in region.")
        return None

    def hibernate(self):
        """
        Shuts down the Brain to save money.
        """
        if not self.current_pod_id:
            print("[RunPod] Brain is already sleeping.")
            return

        query = """
        mutation {
          podTerminate(input: {podId: "%s"})
        }
        """ % self.current_pod_id

        print(f"[RunPod] HIBERNATION SIGNAL SENT (Terminating Pod {self.current_pod_id})...")
        try:
            graphql_url = self._get_graphql_config()
            response = requests.post(graphql_url, json={'query': query})
            data = response.json()
            if 'errors' in data:
                print(f"[RunPod] HIBERNATION ERROR: {data['errors'][0]['message']}")
            else:
                print("[RunPod] SUCCESS: Brain is now sleeping. Cost = $0.")
                self.current_pod_id = None
        except Exception as e:
            print(f"[RunPod] HIBERNATION FAILED: {str(e)}")

    def get_status(self):
        if not self.current_pod_id:
            return "SLEEPING"
        
        query = """
        query {
          pod(input: {podId: "%s"}) {
            runtime {
              status
            }
          }
        }
        """ % self.current_pod_id

        try:
            graphql_url = self._get_graphql_config()
            response = requests.post(graphql_url, json={'query': query})
            data = response.json()
            return data['data']['pod']['runtime']['status']
        except:
            return "ERROR"

    def get_pod_ip(self):
        """
        Retrieves the public IP of the ignited pod.
        """
        if not self.current_pod_id:
            return None
        
        query = """
        query {
          pod(input: {podId: "%s"}) {
            runtime {
              ports {
                ip
                publicPort
              }
            }
          }
        }
        """ % self.current_pod_id

        try:
            graphql_url = self._get_graphql_config()
            response = requests.post(graphql_url, json={'query': query})
            data = response.json()
            # Find the ip for port 8000
            ports = data['data']['pod']['runtime']['ports']
            for p in ports:
                if p['publicPort'] == 8000:
                    return p['ip']
            return None
        except:
            return None
    
    def call_serverless(self, prompt, max_tokens=500, temperature=0.7):
        """
        Call the serverless endpoint for inference.
        
        Args:
            prompt: Text prompt to send
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            
        Returns:
            Response text or None if failed
        """
        if self.mode != "serverless":
            print("[RunPod] ERROR: Not in serverless mode")
            return None
        
        if not self.serverless_url:
            print("[RunPod] ERROR: RUNPOD_SERVERLESS_URL not configured")
            return None
        
        api_key = os.getenv("RUNPOD_API_KEY")
        
        try:
            print(f"[RunPod] Calling serverless endpoint...")
            response = requests.post(
                f"{self.serverless_url}/run",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "input": {
                        "prompt": prompt,
                        "max_tokens": max_tokens,
                        "temperature": temperature
                    }
                },
                timeout=300
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Handle async response
                if data.get("status") == "IN_QUEUE":
                    # Poll for result
                    request_id = data.get("id")
                    return self._poll_serverless_result(request_id)
                elif data.get("status") == "COMPLETED":
                    return data.get("output", {}).get("text")
                else:
                    print(f"[RunPod] Unexpected status: {data.get('status')}")
                    return None
            else:
                print(f"[RunPod] Serverless error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"[RunPod] Serverless exception: {str(e)}")
            return None
    
    def _poll_serverless_result(self, request_id, max_wait=300):
        """Poll for serverless result."""
        import time
        api_key = os.getenv("RUNPOD_API_KEY")
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                response = requests.get(
                    f"{self.serverless_url}/status/{request_id}",
                    headers={"Authorization": f"Bearer {api_key}"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status")
                    
                    if status == "COMPLETED":
                        return data.get("output", {}).get("text")
                    elif status == "FAILED":
                        print(f"[RunPod] Request failed: {data.get('error')}")
                        return None
                    
                    # Still processing, wait and retry
                    time.sleep(1)
                else:
                    print(f"[RunPod] Status check failed: {response.status_code}")
                    return None
                    
            except Exception as e:
                print(f"[RunPod] Polling exception: {str(e)}")
                return None
        
        print(f"[RunPod] Timeout waiting for result")
        return None

if __name__ == "__main__":
    manager = RunPodOrchestrator()
    # manager.ignite_72b()
