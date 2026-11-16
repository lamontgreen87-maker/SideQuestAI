"""
Model Benchmark Suite
Compare 3B vs 8B models on actual Hive Mind tasks.
"""

import requests
import time
import json

OLLAMA_BASE = "http://localhost:11434"

# Test cases representing real Hive Mind workloads
TEST_CASES = [
    {
        "name": "Simple Shatter",
        "prompt": """SHATTER THE FOLLOWING GOAL into 2-3 atomic mission shards. 
Format your response ONLY as a valid JSON list of objects.
Each object must have: "id" (char), "task" (string), and "type" (research/action/audit).

GOAL: Build a user authentication system with email verification""",
        "expected_type": "json"
    },
    {
        "name": "Code Review (Critic Role)",
        "prompt": """Review this plan for gaps or overly broad tasks:
[{"id": "A", "task": "Set up database", "type": "action"},
 {"id": "B", "task": "Build frontend", "type": "action"}]

Identify if any tasks are OVERLY_BROAD or VAGUE.""",
        "expected_type": "critique"
    },
    {
        "name": "Quick Research",
        "prompt": "List 3 key considerations when implementing JWT authentication.",
        "expected_type": "list"
    }
]

def test_model(model_name, prompt, max_tokens=500):
    """Test a single prompt on a model and return timing + output."""
    start = time.time()
    
    response = requests.post(
        f"{OLLAMA_BASE}/api/generate",
        json={
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.7
            }
        }
    )
    
    elapsed = time.time() - start
    
    if response.status_code == 200:
        data = response.json()
        output = data.get('response', '')
        
        # Debug: Check if output is actually empty
        if not output or len(output.strip()) == 0:
            print(f"      ⚠️ WARNING: Empty response from {model_name}")
            print(f"      Raw data keys: {list(data.keys())}")
            print(f"      Response field: '{output}'")
        
        return {
            "success": True,
            "output": output,
            "time_seconds": round(elapsed, 2),
            "tokens": len(output.split()) if output else 0,
            "raw_response_size": len(output) if output else 0
        }
    else:
        return {
            "success": False,
            "error": response.text,
            "time_seconds": round(elapsed, 2)
        }

def run_benchmark():
    """Run all test cases on both models."""
    models = ["qwen2.5:3b", "qwen3:8b"]
    
    print("=" * 80)
    print("HIVE MIND MODEL BENCHMARK")
    print("=" * 80)
    
    results = {}
    
    for test_case in TEST_CASES:
        print(f"\n{'='*80}")
        print(f"TEST: {test_case['name']}")
        print(f"{'='*80}")
        
        results[test_case['name']] = {}
        
        for model in models:
            print(f"\n🧠 Testing {model}...")
            result = test_model(model, test_case['prompt'])
            
            if result['success']:
                print(f"   ⏱️  Time: {result['time_seconds']}s")
                print(f"   📝 Tokens: ~{result['tokens']} ({result.get('raw_response_size', 0)} chars)")
                print(f"   📄 Output preview:")
                preview = result['output'][:200].replace('\n', ' ') if result['output'] else "[EMPTY]"
                print(f"      {preview}...")
                
                results[test_case['name']][model] = result
            else:
                print(f"   ❌ Error: {result['error']}")
                results[test_case['name']][model] = result
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}\n")
    
    for test_name, model_results in results.items():
        print(f"{test_name}:")
        for model, result in model_results.items():
            if result['success']:
                speed = "tokens/sec" if result['time_seconds'] > 0 else "N/A"
                tps = round(result['tokens'] / result['time_seconds'], 1) if result['time_seconds'] > 0 else 0
                print(f"  {model:20s} {result['time_seconds']:6.2f}s  ~{tps} tokens/sec")
        print()
    
    # Save detailed results
    with open('benchmark_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print("📊 Detailed results saved to benchmark_results.json")

if __name__ == "__main__":
    run_benchmark()
