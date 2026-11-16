import asyncio
import sys
from overmind import Overmind

async def run(goal):
    hub = Overmind(redundancy_factor=1, phase=1)
    result = await hub.decompose_goal(goal)
    print("GOAL:", goal)
    print("TASKS:")
    for t in result.get("tasks", []):
        print(f"[{t.get('id')}] {t.get('task')}")

if __name__ == "__main__":
    asyncio.run(run(sys.argv[1]))
