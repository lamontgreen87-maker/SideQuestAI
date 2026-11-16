import asyncio
import sys

from overmind import Overmind


async def run(goal: str):
    hub = Overmind(redundancy_factor=1, phase=1, nexus=None)
    result = await hub.run_swarm(goal, max_depth=3)
    print("FINAL_REPORT:")
    if isinstance(result, dict):
        print(result.get("final_report", ""))
    else:
        print(result)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python swarm_runner.py \"<goal>\"")
    asyncio.run(run(sys.argv[1]))
