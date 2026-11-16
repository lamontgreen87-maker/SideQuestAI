import os
import json

class ProjectMemory:
    """
    Central repository for project context, previous shard results, and architectural state.
    Drones can check this to ensure their work integrates with the swarm's collective memory.
    """
    def __init__(self, storage_dir="memory"):
        self.storage_dir = storage_dir
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir)
        self.context_file = os.path.join(self.storage_dir, "context.json")
        self.shards_file = os.path.join(self.storage_dir, "shards.json")
        self._init_memory()

    def _init_memory(self):
        if not os.path.exists(self.context_file):
            with open(self.context_file, "w") as f:
                json.dump({"project_goal": "", "architecture": {}, "env_vars": {}}, f)
        if not os.path.exists(self.shards_file):
            with open(self.shards_file, "w") as f:
                json.dump([], f)

    def update_context(self, key, value):
        with open(self.context_file, "r") as f:
            data = json.load(f)
        data[key] = value
        with open(self.context_file, "w") as f:
            json.dump(data, f, indent=2)

    def record_shard(self, shard_id, task, outcome):
        with open(self.shards_file, "r") as f:
            shards = json.load(f)
        shards.append({
            "id": shard_id,
            "task": task,
            "outcome": outcome,
            "timestamp": os.path.getmtime(self.shards_file) # Simple timestamp
        })
        with open(self.shards_file, "w") as f:
            json.dump(shards, f, indent=2)

    def get_full_memory_prompt(self):
        """Returns a string representation of all project state for AI context."""
        with open(self.context_file, "r") as f:
            ctx = json.load(f)
        with open(self.shards_file, "r") as f:
            shards = json.load(f)
        
        prompt = "### PROJECT MEMORY ###\n"
        prompt += f"Primary Goal: {ctx.get('project_goal')}\n"
        prompt += f"Architecture: {json.dumps(ctx.get('architecture'))}\n"
        prompt += "Previous Shard Outcomes:\n"
        for s in shards[-10:]: # Last 10 shards for context
            prompt += f"- Shard {s['id']}: {s['outcome'][:200]}...\n"
        return prompt
