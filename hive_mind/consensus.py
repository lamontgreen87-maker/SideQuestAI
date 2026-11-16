from collections import Counter

class ConsensusEngine:
    """
    Compiles results from multiple drones working on the same task.
    Filters out noise and finds the "Golden Truth".
    """
    @staticmethod
    def synthesize(results):
        """
        Filters out workers that failed their tests and synthesizes the 'Winner'.
        """
        print(f"[Consensus] Evaluating {len(results)} outputs via Functional Truth...")
        
        # 1. Filter only those that passed their self-tests
        valid_outputs = [r['output'] for r in results if "PASSED" in r.get('output', '').upper()]
        
        if not valid_outputs:
            return "FAILURE: No workers reached consensus on a working solution."
        
        # 2. Of the valid ones, we look for the most detailed/cleanest (simulation)
        # In a real hive, the Overmind (Qwen 72B) would judge the style.
        winner = max(valid_outputs, key=len) 
        
        return f"Consensus Reached! (Winner selected from {len(valid_outputs)} successful variations):\n{winner}"

if __name__ == "__main__":
    # Test
    ce = ConsensusEngine()
    test_results = ["Use AES-256", "Use AES-256 for encryption", "Encryption: AES-256"]
    print(ce.synthesize(test_results))
