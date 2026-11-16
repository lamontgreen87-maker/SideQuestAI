"""
Coding Task Benchmark: 3B vs 7B
Test on actual coding tasks to see if 7B is worth the extra time.
"""

import requests
import time
import json

OLLAMA_BASE = "http://localhost:11434"

# Coding-focused test cases
CODING_TESTS = [
    {
        "name": "Simple Function",
        "prompt": "Write a Python function that takes a list of numbers and returns only the even numbers. Include docstring and type hints.",
        "expected": "code"
    },
    {
        "name": "Class Design",
        "prompt": "Design a Python class for a Task Queue with methods: add_task, get_next_task, and mark_complete. Include proper error handling.",
        "expected": "code"
    },
    {
        "name": "Code Review",
        "prompt": """Review this code for bugs and improvements:
```python
def process_data(data):
    result = []
    for i in range(len(data)):
        if data[i] > 0:
            result.append(data[i] * 2)
    return result
```""",
        "expected": "critique"
    }
]

def test_model(model_name, prompt, max_tokens=800):
    """Test a single prompt on a model."""
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
        
        return {
            "success": True,
            "output": output,
            "time_seconds": round(elapsed, 2),
            "chars": len(output) if output else 0
        }
    else:
        return {
            "success": False,
            "error": response.text,
            "time_seconds": round(elapsed, 2)
        }

def run_coding_benchmark():
    """Run coding tests on both models."""
    models = ["qwen2.5:3b", "qwen2.5:7b"]
    
    print("=" * 80)
    print("CODING BENCHMARK: 3B vs 7B")
    print("=" * 80)
    
    results = {}
    
    for test_case in CODING_TESTS:
        print(f"\n{'='*80}")
        print(f"TEST: {test_case['name']}")
        print(f"{'='*80}")
        
        results[test_case['name']] = {}
        
        for model in models:
            print(f"\n🧠 Testing {model}...")
            result = test_model(model, test_case['prompt'])
            
            if result['success']:
                print(f"   ⏱️  Time: {result['time_seconds']}s")
                print(f"   📝 Output: {result['chars']} chars")
                print(f"   📄 Preview:")
                preview = result['output'][:150].replace('\n', ' ') if result['output'] else "[EMPTY]"
                print(f"      {preview}...")
                
                results[test_case['name']][model] = result
            else:
                print(f"   ❌ Error: {result['error']}")
                results[test_case['name']][model] = result
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY: Speed Comparison")
    print(f"{'='*80}\n")
    
    for test_name, model_results in results.items():
        print(f"{test_name}:")
        for model, result in model_results.items():
            if result['success']:
                print(f"  {model:20s} {result['time_seconds']:6.2f}s  ({result['chars']} chars)")
        print()
    
    # Save results
    with open('coding_benchmark_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print("📊 Full results saved to coding_benchmark_results.json")
    print("\n💡 Now manually review the outputs to compare QUALITY")

if __name__ == "__main__":
    run_coding_benchmark()
