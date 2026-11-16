import asyncio
import os
from overmind import Overmind

async def test_shatter():
    print("--- DIRECT SHATTER TEST ---")
    print(f"OLLAMA_URL: {os.getenv('OLLAMA_URL', 'http://localhost:11434/api/generate')}")
    
    hub = Overmind(redundancy_factor=1, phase=1)
    goal = "Create a task manager app with a dark mode UI and user authentication."
    
    print(f"Goal: {goal}")
    print("Shattering...")
    
    try:
        # We call decompose_goal directly
        result = await hub.decompose_goal(goal)
        print("\n--- SHATTER RESULT ---")
        if "tasks" in result:
            for t in result["tasks"]:
                print(f"[{t.get('id')}] (Tier {t.get('required_tier')}): {t.get('task')}")
        else:
            print(f"Shatter failed or returned empty: {result}")
            
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_shatter())
