"""
Test Serverless Endpoint
Quick test to verify serverless endpoint is working.
"""

import os
from dotenv import load_dotenv
from runpod_orchestrator import RunPodOrchestrator

load_dotenv()

def test_serverless():
    """Test the serverless endpoint."""
    
    print("=" * 60)
    print("SERVERLESS ENDPOINT TEST")
    print("=" * 60)
    
    # Check configuration
    mode = os.getenv("RUNPOD_MODE")
    endpoint_id = os.getenv("RUNPOD_SERVERLESS_ENDPOINT_ID")
    endpoint_url = os.getenv("RUNPOD_SERVERLESS_URL")
    
    print(f"\nMode: {mode}")
    print(f"Endpoint ID: {endpoint_id}")
    print(f"Endpoint URL: {endpoint_url}")
    
    if mode != "serverless":
        print("\n❌ ERROR: RUNPOD_MODE must be set to 'serverless'")
        print("Set in .env: RUNPOD_MODE=serverless")
        return
    
    if not endpoint_id or not endpoint_url:
        print("\n❌ ERROR: Serverless endpoint not configured")
        print("Required in .env:")
        print("  RUNPOD_SERVERLESS_ENDPOINT_ID=your-endpoint-id")
        print("  RUNPOD_SERVERLESS_URL=https://api.runpod.ai/v2/your-endpoint-id")
        return
    
    # Initialize orchestrator
    print("\n" + "=" * 60)
    print("Testing Connection...")
    print("=" * 60)
    
    orchestrator = RunPodOrchestrator()
    
    # Simple test prompt
    test_prompt = "Say 'Hello from the Hive Mind!' and nothing else."
    
    print(f"\nSending test prompt: {test_prompt}")
    print("Waiting for response...")
    
    import time
    start = time.time()
    
    response = orchestrator.call_serverless(test_prompt, max_tokens=50)
    
    elapsed = time.time() - start
    
    if response:
        print(f"\n✅ SUCCESS!")
        print(f"Response time: {elapsed:.1f} seconds")
        print(f"Response: {response}")
    else:
        print(f"\n❌ FAILED")
        print("Check the error messages above")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    test_serverless()
