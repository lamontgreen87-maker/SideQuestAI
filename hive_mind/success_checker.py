"""
Success Criteria Checker
Validates that completed shards meet their success criteria.
"""

from typing import List, Dict
import asyncio
from drone import DroneAgent

class SuccessChecker:
    """Checks if shard outputs meet defined success criteria."""
    
    @staticmethod
    async def check(shards: List[Dict], results: Dict[str, Dict]) -> Dict:
        """
        Check if shards meet their success criteria.
        
        Args:
            shards: List of shard definitions with success_criteria
            results: Dict mapping shard_id to execution results
            
        Returns:
            Success report with scores and failed criteria
        """
        total_criteria = 0
        passed_criteria = 0
        shard_scores = {}
        failed_criteria = []
        
        for shard in shards:
            shard_id = shard['id']
            criteria = shard.get('success_criteria', [])
            
            if not criteria:
                # No criteria defined - assume success if shard completed
                if shard_id in results and results[shard_id].get('status') == 'success':
                    shard_scores[shard_id] = {"score": 1.0, "passed": [], "failed": []}
                else:
                    shard_scores[shard_id] = {"score": 0.0, "passed": [], "failed": ["No output"]}
                continue
            
            # Check each criterion
            shard_result = results.get(shard_id, {})
            output = shard_result.get('output', '')
            
            passed = []
            failed = []
            
            for criterion in criteria:
                # Use a Judge drone to evaluate the criterion
                is_met = await SuccessChecker._evaluate_criterion(
                    criterion, 
                    output, 
                    shard['task']
                )
                
                total_criteria += 1
                if is_met:
                    passed_criteria += 1
                    passed.append(criterion)
                else:
                    failed.append(criterion)
                    failed_criteria.append({
                        "shard_id": shard_id,
                        "criterion": criterion
                    })
            
            # Calculate shard score
            shard_score = len(passed) / len(criteria) if criteria else 0
            shard_scores[shard_id] = {
                "score": round(shard_score, 2),
                "passed": passed,
                "failed": failed
            }
        
        # Calculate overall score
        overall_score = passed_criteria / total_criteria if total_criteria > 0 else 0
        
        return {
            "score": round(overall_score, 2),
            "total_criteria": total_criteria,
            "passed_criteria": passed_criteria,
            "failed_criteria": failed_criteria,
            "shard_scores": shard_scores,
            "passed": overall_score >= 0.8  # 80% threshold
        }
    
    @staticmethod
    async def _evaluate_criterion(criterion: str, output: str, task: str) -> bool:
        """
        Use a Judge drone to evaluate if a criterion is met.
        
        Args:
            criterion: Success criterion to check
            output: Shard output to evaluate
            task: Original task description
            
        Returns:
            True if criterion is met, False otherwise
        """
        # Create a Judge drone to evaluate
        judge = DroneAgent(
            drone_id="judge-criterion",
            task=f"""Evaluate if the following output meets this success criterion:

CRITERION: {criterion}

ORIGINAL TASK: {task}

OUTPUT:
{output[:500]}  # Limit to first 500 chars

Respond with ONLY "YES" if the criterion is clearly met, or "NO" if it is not met or unclear.""",
            task_type="audit",
            role="critic"
        )
        
        try:
            result = await judge.run()
            response = result.get('output', '').strip().upper()
            
            # Simple YES/NO parsing
            return "YES" in response and "NO" not in response
        except Exception as e:
            print(f"[SuccessChecker] Error evaluating criterion: {e}")
            return False
    
    @staticmethod
    def visualize_report(report: Dict) -> str:
        """Create human-readable success report."""
        output = []
        output.append("=" * 60)
        output.append("SUCCESS CRITERIA REPORT")
        output.append("=" * 60)
        
        status = "✅ PASSED" if report['passed'] else "❌ FAILED"
        output.append(f"Status: {status}")
        output.append(f"Overall Score: {report['score'] * 100:.0f}%")
        output.append(f"Criteria: {report['passed_criteria']}/{report['total_criteria']} passed")
        output.append("")
        
        # Shard-by-shard breakdown
        output.append("SHARD BREAKDOWN:")
        for shard_id, scores in report['shard_scores'].items():
            score_pct = scores['score'] * 100
            status_icon = "✅" if scores['score'] >= 0.8 else "⚠️" if scores['score'] >= 0.5 else "❌"
            output.append(f"\n{status_icon} Shard {shard_id}: {score_pct:.0f}%")
            
            if scores['passed']:
                output.append(f"  ✓ Passed:")
                for criterion in scores['passed']:
                    output.append(f"    - {criterion}")
            
            if scores['failed']:
                output.append(f"  ✗ Failed:")
                for criterion in scores['failed']:
                    output.append(f"    - {criterion}")
        
        return "\n".join(output)


async def test_success_checker():
    """Test the success checker (simplified without actual AI evaluation)."""
    
    print("=" * 60)
    print("SUCCESS CHECKER TESTS")
    print("=" * 60)
    
    # Test 1: Mock evaluation (without actual AI calls)
    print("\n--- Test 1: Mock Success Check ---")
    shards = [
        {
            "id": "A",
            "task": "Build authentication system",
            "success_criteria": [
                "User can register",
                "User can login",
                "Passwords are hashed"
            ]
        },
        {
            "id": "B",
            "task": "Add API documentation",
            "success_criteria": [
                "All endpoints documented",
                "Examples provided"
            ]
        }
    ]
    
    results = {
        "A": {
            "status": "success",
            "output": "Built auth system with registration, login, and bcrypt password hashing"
        },
        "B": {
            "status": "success",
            "output": "Added API docs with endpoint descriptions"
        }
    }
    
    # Mock the evaluation (in real use, this would call AI)
    print("Note: This is a mock test. Real evaluation requires AI calls.")
    print("In production, each criterion would be evaluated by a Judge drone.")
    
    # Create a simplified mock report
    mock_report = {
        "score": 0.80,
        "total_criteria": 5,
        "passed_criteria": 4,
        "failed_criteria": [{"shard_id": "B", "criterion": "Examples provided"}],
        "shard_scores": {
            "A": {
                "score": 1.0,
                "passed": ["User can register", "User can login", "Passwords are hashed"],
                "failed": []
            },
            "B": {
                "score": 0.5,
                "passed": ["All endpoints documented"],
                "failed": ["Examples provided"]
            }
        },
        "passed": True
    }
    
    print(SuccessChecker.visualize_report(mock_report))


if __name__ == "__main__":
    asyncio.run(test_success_checker())
