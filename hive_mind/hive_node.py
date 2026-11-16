import asyncio
import json
from drone import DroneAgent

class HiveNode:
    """
    The Hive Master / Host Node.
    Responsible for shattering complex goals into atomic tasks.
    """
    def __init__(self):
        self.drones = []

    async def shatter_goal(self, goal):
        """
        Logic to decompose a goal. 
        In a real system, this would use an LLM or a rule engine.
        """
        print(f"[HiveNode] Shattering goal: {goal}")
        
        # Simulating a strategic breakdown for the prototype
        if "login" in goal.lower():
            return [
                {"id": 1, "task": "Search for best practices in modern secure login implementations. Report findings.", "type": "research"},
                {"id": 2, "task": "Design a basic Python skeleton for a secure login function based on findings.", "type": "action"},
                {"id": 3, "task": "Create a unit test to verify the skeleton handles invalid credentials correctly.", "type": "test"}
            ]
        return [{"id": 1, "task": f"Analyze and solve: {goal}", "type": "general"}]

    async def execute_swarm(self, goal):
        tasks = await self.shatter_goal(goal)
        results = []
        
        print(f"[HiveNode] Dispatching {len(tasks)} tasks to clones...")
        
        # Parallel execution of drones
        drone_coros = [DroneAgent(t['id'], t['task'], t['type']).run() for t in tasks]
        results = await asyncio.gather(*drone_coros)
        
        print("\n" + "="*50)
        print("[HiveNode] Swarm results synthesized:")
        for res in results:
            print(f"- Task {res['id']} ({res['status']}): {res['output'][:100]}...")
        print("="*50)

if __name__ == "__main__":
    node = HiveNode()
    asyncio.run(node.execute_swarm("Create a secure login script"))
