import asyncio
import uuid
import random
from drone import DroneAgent

class LocalEarOrchestrator:
    """
    Phase 1: The Ears.
    Runs on the local SER5. 
    Manages the 'Funded Queue' and Nano-Drones (3B).
    """
    def __init__(self):
        self.queue = []
        self.escrow_balance = 0.0
        self.is_brain_awake = False

    async def add_task_to_queue(self, goal, payment):
        task_id = str(uuid.uuid4())[:8]
        print(f"\n[Ear] New Task {task_id} received with ${payment} Gas.")
        self.queue.append({"id": task_id, "goal": goal, "payment": payment, "status": "PENDING"})
        self.escrow_balance += payment
        
        # Dispatch a Nano-Drone (3B) as the 'Mouth' to acknowledge the user
        mouth = DroneAgent(f"{task_id}-Mouth", goal, "comm", role="mouth", model_size="3B")
        await mouth.run()
        
        await self.process_queue()

    async def process_queue(self):
        for task in self.queue:
            if task["status"] == "PENDING":
                print(f"[Ear] Triage Phase: Assigning Nano-Drone (3B) to audit Goal {task['id']}...")
                scout = DroneAgent(f"{task['id']}-Scout", task['goal'], "audit", role="scout", model_size="3B")
                audit_result = await scout.run()
                
                if "NANO_AUDIT_PASS" in audit_result["output"]:
                    task["status"] = "FUNDED"
                    print(f"[Ear] Task {task['id']} is now FUNDED and VALIDATED.")
                    
                    # Logic to check if we should 'Wake the Brain' (Ignition)
                    if not self.is_brain_awake:
                        await self.ignite_big_brain()

    async def ignite_big_brain(self):
        print("\n" + "="*60)
        print("[Ear] IGNITION SIGNAL SENT: Waking the 72B Overmind...")
        print("[Ear] Mounting Network Volume (Persistent Brain)...")
        self.is_brain_awake = True
        await asyncio.sleep(2.0) # Simulate spin-up
        print("[Ear] Big Brain is AWAKE and processing the Funded Queue.")
        print("="*60 + "\n")

async def test_phase_1_flow():
    ear = LocalEarOrchestrator()
    
    # Simulate a user submitting an 'Impossible' project
    await ear.add_task_to_queue("Build a decentralized OS for smart refrigerators.", payment=50.0)
    
    # Simulate another small task
    await ear.add_task_to_queue("Translate the Hive Manifesto into Binary Poetry.", payment=5.0)

if __name__ == "__main__":
    asyncio.run(test_phase_1_flow())
