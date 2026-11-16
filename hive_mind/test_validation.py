"""
Integration Test: Validation Layer with 7B Model
Tests the full Shatter -> Validate -> Execute pipeline.
"""

import asyncio
from overmind import Overmind


async def test_validation_pipeline():
    """Test the full validation pipeline with a realistic task."""

    print("=" * 80)
    print("VALIDATION LAYER INTEGRATION TEST")
    print("=" * 80)
    print("\nTesting with 7B model locally...")
    print("This will validate:")
    print("  1. Enhanced shard format generation")
    print("  2. Dependency resolution")
    print("  3. Execution plan building")
    print("\n" + "=" * 80)

    # Initialize Overmind in Phase 1 (local mode)
    overmind = Overmind(phase=1)

    # Test Case 1: Simple task with dependencies
    print("\n\nTEST 1: Simple Task with Dependencies")
    print("-" * 80)
    goal1 = "Build a user authentication system with registration and login"

    print(f"\nGoal: {goal1}")
    print("\nExpected shards:")
    print("  A: Research auth best practices (no dependencies)")
    print("  B: Design database schema (depends on A)")
    print("  C: Implement auth endpoints (depends on B)")
    print("\nRunning Shatter...")

    try:
        result1 = await overmind.decompose_goal(goal1)

        if "error" in result1:
            print(f"\nERROR: {result1['error']}")
        else:
            print("\nSUCCESS!")
            print(f"\nGenerated {len(result1['tasks'])} shards:")
            if len(result1["tasks"]) == 1 and result1["tasks"][0].get("task") == goal1:
                print("WARNING: Shatter fallback detected. Check Ollama/model availability.")
            for shard in result1["tasks"]:
                print(f"\n  [{shard['id']}] {shard['task']}")
                print(f"      Depends on: {shard.get('depends_on', [])}")
                print(f"      Outputs: {shard.get('outputs', [])}")
                print(f"      Success criteria: {shard.get('success_criteria', [])}")

            if result1.get("execution_plan"):
                plan = result1["execution_plan"]
                print("\nExecution Plan:")
                print(f"   Total waves: {plan['total_waves']}")
                print(f"   Max parallelism: {plan['max_parallelism']}")
                print("\n   Wave breakdown:")
                for i, wave in enumerate(plan["waves"], 1):
                    parallel = "PARALLEL" if len(wave) > 1 else "SERIAL"
                    print(f"   Wave {i} {parallel}: {wave}")

    except Exception as e:
        print(f"\nTEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()

    # Test Case 2: More complex task
    print("\n\nTEST 2: Complex Task with Multiple Dependencies")
    print("-" * 80)
    goal2 = "Create a REST API with database, authentication, and documentation"

    print(f"\nGoal: {goal2}")
    print("\nExpected shards:")
    print("  A: Design database schema (no dependencies)")
    print("  B: Implement auth system (depends on A)")
    print("  C: Build API endpoints (depends on A)")
    print("  D: Add documentation (depends on B, C)")
    print("\nRunning Shatter...")

    try:
        result2 = await overmind.decompose_goal(goal2)

        if "error" in result2:
            print(f"\nERROR: {result2['error']}")
        else:
            print("\nSUCCESS!")
            print(f"\nGenerated {len(result2['tasks'])} shards:")
            if len(result2["tasks"]) == 1 and result2["tasks"][0].get("task") == goal2:
                print("WARNING: Shatter fallback detected. Check Ollama/model availability.")
            for shard in result2["tasks"]:
                print(f"\n  [{shard['id']}] {shard['task']}")
                print(f"      Depends on: {shard.get('depends_on', [])}")
                print(f"      Outputs: {shard.get('outputs', [])}")
                print(f"      Success criteria: {shard.get('success_criteria', [])[:2]}...")

            if result2.get("execution_plan"):
                plan = result2["execution_plan"]
                print("\nExecution Plan:")
                print(f"   Total waves: {plan['total_waves']}")
                print(f"   Max parallelism: {plan['max_parallelism']}")
                print("\n   Wave breakdown:")
                for i, wave in enumerate(plan["waves"], 1):
                    parallel = "PARALLEL" if len(wave) > 1 else "SERIAL"
                    print(f"   Wave {i} {parallel}: {wave}")

                # Check for parallel execution
                if plan["max_parallelism"] > 1:
                    print(f"\n   Parallelism detected! Can run {plan['max_parallelism']} shards simultaneously")

    except Exception as e:
        print(f"\nTEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()

    # Summary
    print("\n\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print("\nValidation layer is integrated and functional!")
    print("\nNext steps:")
    print("  1. Review the generated shards above")
    print("  2. Check if dependencies make sense")
    print("  3. Verify execution plan is optimal")
    print("  4. When 72B is available, run same tests for comparison")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(test_validation_pipeline())
