"""
Dependency Resolver
Builds execution plans from shards with dependencies.
"""

from typing import List, Dict, Set, Tuple
from collections import defaultdict, deque

class DependencyResolver:
    """Resolves dependencies between shards and creates execution plans."""
    
    @staticmethod
    def build_plan(shards: List[Dict]) -> Dict:
        """
        Build an execution plan from shards with dependencies.
        
        Args:
            shards: List of shard dicts with 'id' and 'depends_on' fields
            
        Returns:
            Dict with execution waves and metadata
        """
        # Build dependency graph
        graph = defaultdict(list)
        in_degree = defaultdict(int)
        shard_map = {}
        
        for shard in shards:
            shard_id = shard['id']
            shard_map[shard_id] = shard
            dependencies = shard.get('depends_on', [])
            
            # Initialize in-degree
            if shard_id not in in_degree:
                in_degree[shard_id] = 0
            
            # Build edges
            for dep in dependencies:
                graph[dep].append(shard_id)
                in_degree[shard_id] += 1
        
        # Detect cycles
        if DependencyResolver._has_cycle(graph, list(shard_map.keys())):
            return {
                "valid": False,
                "error": "Circular dependency detected",
                "waves": []
            }
        
        # Topological sort into waves (levels)
        waves = []
        queue = deque([sid for sid in shard_map.keys() if in_degree[sid] == 0])
        
        while queue:
            # All shards in current wave can execute in parallel
            current_wave = []
            wave_size = len(queue)
            
            for _ in range(wave_size):
                shard_id = queue.popleft()
                current_wave.append(shard_id)
                
                # Reduce in-degree for dependent shards
                for dependent in graph[shard_id]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)
            
            waves.append(current_wave)
        
        # Calculate statistics
        total_shards = len(shard_map)
        max_parallelism = max(len(wave) for wave in waves) if waves else 0
        
        return {
            "valid": True,
            "waves": waves,
            "total_shards": total_shards,
            "total_waves": len(waves),
            "max_parallelism": max_parallelism,
            "shard_map": shard_map
        }
    
    @staticmethod
    def _has_cycle(graph: Dict, nodes: List[str]) -> bool:
        """Detect cycles using DFS."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {node: WHITE for node in nodes}
        
        def dfs(node):
            if color[node] == GRAY:
                return True  # Back edge = cycle
            if color[node] == BLACK:
                return False  # Already processed
            
            color[node] = GRAY
            for neighbor in graph.get(node, []):
                if dfs(neighbor):
                    return True
            color[node] = BLACK
            return False
        
        for node in nodes:
            if color[node] == WHITE:
                if dfs(node):
                    return True
        return False
    
    @staticmethod
    def visualize_plan(plan: Dict) -> str:
        """Create a human-readable visualization of the execution plan."""
        if not plan['valid']:
            return f"❌ Invalid Plan: {plan['error']}"
        
        output = []
        output.append("=" * 60)
        output.append("EXECUTION PLAN")
        output.append("=" * 60)
        output.append(f"Total Shards: {plan['total_shards']}")
        output.append(f"Total Waves: {plan['total_waves']}")
        output.append(f"Max Parallelism: {plan['max_parallelism']}")
        output.append("")
        
        for i, wave in enumerate(plan['waves'], 1):
            parallel_marker = "⚡ PARALLEL" if len(wave) > 1 else "→ SERIAL"
            output.append(f"Wave {i} {parallel_marker}: {wave}")
            
            # Show shard details
            for shard_id in wave:
                shard = plan['shard_map'][shard_id]
                task = shard.get('task', 'No description')[:50]
                deps = shard.get('depends_on', [])
                dep_str = f" (depends on: {deps})" if deps else ""
                output.append(f"  [{shard_id}] {task}...{dep_str}")
            output.append("")
        
        return "\n".join(output)


def test_dependency_resolver():
    """Test the dependency resolver with various scenarios."""
    
    print("=" * 60)
    print("DEPENDENCY RESOLVER TESTS")
    print("=" * 60)
    
    # Test 1: Simple linear dependency
    print("\n--- Test 1: Linear Dependency (A → B → C) ---")
    shards_linear = [
        {"id": "A", "task": "Define user model", "depends_on": []},
        {"id": "B", "task": "Implement password hashing", "depends_on": ["A"]},
        {"id": "C", "task": "Create login function", "depends_on": ["B"]}
    ]
    plan = DependencyResolver.build_plan(shards_linear)
    print(DependencyResolver.visualize_plan(plan))
    
    # Test 2: Parallel tasks
    print("\n--- Test 2: Parallel Tasks (A → B,C → D) ---")
    shards_parallel = [
        {"id": "A", "task": "Design database schema", "depends_on": []},
        {"id": "B", "task": "Implement auth endpoints", "depends_on": ["A"]},
        {"id": "C", "task": "Implement data endpoints", "depends_on": ["A"]},
        {"id": "D", "task": "Add API documentation", "depends_on": ["B", "C"]}
    ]
    plan = DependencyResolver.build_plan(shards_parallel)
    print(DependencyResolver.visualize_plan(plan))
    
    # Test 3: Circular dependency (should fail)
    print("\n--- Test 3: Circular Dependency (A → B → C → A) ---")
    shards_circular = [
        {"id": "A", "task": "Task A", "depends_on": ["C"]},
        {"id": "B", "task": "Task B", "depends_on": ["A"]},
        {"id": "C", "task": "Task C", "depends_on": ["B"]}
    ]
    plan = DependencyResolver.build_plan(shards_circular)
    print(DependencyResolver.visualize_plan(plan))
    
    # Test 4: Complex DAG
    print("\n--- Test 4: Complex DAG ---")
    shards_complex = [
        {"id": "A", "task": "Research requirements", "depends_on": []},
        {"id": "B", "task": "Design architecture", "depends_on": ["A"]},
        {"id": "C", "task": "Setup database", "depends_on": ["B"]},
        {"id": "D", "task": "Build API layer", "depends_on": ["B"]},
        {"id": "E", "task": "Implement auth", "depends_on": ["C", "D"]},
        {"id": "F", "task": "Add tests", "depends_on": ["E"]},
        {"id": "G", "task": "Write docs", "depends_on": ["D", "E"]}
    ]
    plan = DependencyResolver.build_plan(shards_complex)
    print(DependencyResolver.visualize_plan(plan))


if __name__ == "__main__":
    test_dependency_resolver()
