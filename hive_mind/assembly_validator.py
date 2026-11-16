"""
Assembly Validator
Checks if completed shards fit together logically.
"""

from typing import List, Dict
import json

class AssemblyValidator:
    """Validates that completed shards form a coherent solution."""
    
    @staticmethod
    def validate(shards: List[Dict], results: Dict[str, Dict]) -> Dict:
        """
        Validate assembly of completed shards.
        
        Args:
            shards: List of shard definitions
            results: Dict mapping shard_id to execution results
            
        Returns:
            Validation report with issues and confidence score
        """
        issues = []
        warnings = []
        
        # Check 1: Completeness
        completeness = AssemblyValidator._check_completeness(shards, results)
        issues.extend(completeness['issues'])
        
        # Check 2: Interface Compatibility
        compatibility = AssemblyValidator._check_compatibility(shards, results)
        issues.extend(compatibility['issues'])
        warnings.extend(compatibility['warnings'])
        
        # Check 3: Output Coverage
        coverage = AssemblyValidator._check_coverage(shards, results)
        warnings.extend(coverage['warnings'])
        
        # Calculate confidence score
        total_checks = 3
        passed_checks = sum([
            len(completeness['issues']) == 0,
            len(compatibility['issues']) == 0,
            len(coverage['warnings']) == 0
        ])
        
        confidence = passed_checks / total_checks
        
        return {
            "valid": len(issues) == 0,
            "confidence": round(confidence, 2),
            "issues": issues,
            "warnings": warnings,
            "checks": {
                "completeness": completeness,
                "compatibility": compatibility,
                "coverage": coverage
            }
        }
    
    @staticmethod
    def _check_completeness(shards: List[Dict], results: Dict) -> Dict:
        """Check if all shards completed successfully."""
        issues = []
        
        for shard in shards:
            shard_id = shard['id']
            
            if shard_id not in results:
                issues.append({
                    "type": "MISSING_RESULT",
                    "shard_id": shard_id,
                    "message": f"Shard {shard_id} has no result"
                })
            elif results[shard_id].get('status') == 'failed':
                issues.append({
                    "type": "FAILED_SHARD",
                    "shard_id": shard_id,
                    "message": f"Shard {shard_id} failed execution"
                })
        
        return {
            "passed": len(issues) == 0,
            "issues": issues
        }
    
    @staticmethod
    def _check_compatibility(shards: List[Dict], results: Dict) -> Dict:
        """Check if shard outputs are compatible with dependent shards."""
        issues = []
        warnings = []
        
        # Build output map
        outputs_map = {}
        for shard in shards:
            shard_id = shard['id']
            outputs = shard.get('outputs', [])
            outputs_map[shard_id] = outputs
        
        # Check dependencies
        for shard in shards:
            shard_id = shard['id']
            dependencies = shard.get('depends_on', [])
            
            for dep_id in dependencies:
                # Check if dependency produced expected outputs
                expected_outputs = outputs_map.get(dep_id, [])
                
                if dep_id not in results:
                    issues.append({
                        "type": "MISSING_DEPENDENCY",
                        "shard_id": shard_id,
                        "dependency": dep_id,
                        "message": f"Shard {shard_id} depends on {dep_id} which has no result"
                    })
                elif not expected_outputs:
                    warnings.append({
                        "type": "NO_OUTPUTS_DEFINED",
                        "shard_id": dep_id,
                        "message": f"Dependency {dep_id} has no outputs defined"
                    })
        
        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "warnings": warnings
        }
    
    @staticmethod
    def _check_coverage(shards: List[Dict], results: Dict) -> Dict:
        """Check for orphaned outputs (produced but never used)."""
        warnings = []
        
        # Collect all outputs
        all_outputs = set()
        for shard in shards:
            outputs = shard.get('outputs', [])
            all_outputs.update(outputs)
        
        # Collect all referenced outputs (via dependencies)
        referenced_outputs = set()
        for shard in shards:
            dependencies = shard.get('depends_on', [])
            for dep_id in dependencies:
                # Find the dependency shard
                dep_shard = next((s for s in shards if s['id'] == dep_id), None)
                if dep_shard:
                    referenced_outputs.update(dep_shard.get('outputs', []))
        
        # Find orphaned outputs
        orphaned = all_outputs - referenced_outputs
        if orphaned:
            warnings.append({
                "type": "ORPHANED_OUTPUTS",
                "outputs": list(orphaned),
                "message": f"These outputs are produced but never used: {orphaned}"
            })
        
        return {
            "passed": len(warnings) == 0,
            "warnings": warnings
        }
    
    @staticmethod
    def visualize_report(report: Dict) -> str:
        """Create human-readable validation report."""
        output = []
        output.append("=" * 60)
        output.append("ASSEMBLY VALIDATION REPORT")
        output.append("=" * 60)
        
        status = "✅ VALID" if report['valid'] else "❌ INVALID"
        output.append(f"Status: {status}")
        output.append(f"Confidence: {report['confidence'] * 100:.0f}%")
        output.append("")
        
        # Issues
        if report['issues']:
            output.append("🚨 ISSUES:")
            for issue in report['issues']:
                output.append(f"  - [{issue['type']}] {issue['message']}")
            output.append("")
        
        # Warnings
        if report['warnings']:
            output.append("⚠️  WARNINGS:")
            for warning in report['warnings']:
                output.append(f"  - [{warning['type']}] {warning['message']}")
            output.append("")
        
        if not report['issues'] and not report['warnings']:
            output.append("✨ No issues found! Assembly looks good.")
        
        return "\n".join(output)


def test_assembly_validator():
    """Test the assembly validator."""
    
    print("=" * 60)
    print("ASSEMBLY VALIDATOR TESTS")
    print("=" * 60)
    
    # Test 1: Valid assembly
    print("\n--- Test 1: Valid Assembly ---")
    shards_valid = [
        {"id": "A", "task": "Design schema", "depends_on": [], "outputs": ["schema.sql"]},
        {"id": "B", "task": "Build API", "depends_on": ["A"], "outputs": ["api.py"]},
        {"id": "C", "task": "Add tests", "depends_on": ["B"], "outputs": ["tests.py"]}
    ]
    results_valid = {
        "A": {"status": "success", "output": "Schema created"},
        "B": {"status": "success", "output": "API built"},
        "C": {"status": "success", "output": "Tests added"}
    }
    report = AssemblyValidator.validate(shards_valid, results_valid)
    print(AssemblyValidator.visualize_report(report))
    
    # Test 2: Missing result
    print("\n--- Test 2: Missing Result ---")
    results_missing = {
        "A": {"status": "success", "output": "Schema created"},
        "B": {"status": "success", "output": "API built"}
        # C is missing!
    }
    report = AssemblyValidator.validate(shards_valid, results_missing)
    print(AssemblyValidator.visualize_report(report))
    
    # Test 3: Failed shard
    print("\n--- Test 3: Failed Shard ---")
    results_failed = {
        "A": {"status": "success", "output": "Schema created"},
        "B": {"status": "failed", "output": "API build failed"},
        "C": {"status": "success", "output": "Tests added"}
    }
    report = AssemblyValidator.validate(shards_valid, results_failed)
    print(AssemblyValidator.visualize_report(report))
    
    # Test 4: Orphaned outputs
    print("\n--- Test 4: Orphaned Outputs ---")
    shards_orphaned = [
        {"id": "A", "task": "Design schema", "depends_on": [], "outputs": ["schema.sql", "unused.txt"]},
        {"id": "B", "task": "Build API", "depends_on": ["A"], "outputs": ["api.py"]}
    ]
    results_orphaned = {
        "A": {"status": "success", "output": "Schema created"},
        "B": {"status": "success", "output": "API built"}
    }
    report = AssemblyValidator.validate(shards_orphaned, results_orphaned)
    print(AssemblyValidator.visualize_report(report))


if __name__ == "__main__":
    test_assembly_validator()
