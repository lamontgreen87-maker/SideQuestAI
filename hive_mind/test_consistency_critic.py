import asyncio

import overmind


class FakeDrone:
    def __init__(self, outputs):
        self._outputs = outputs

    async def run(self):
        return {"output": self._outputs.pop(0)}


async def run_tests():
    hub = overmind.Overmind(redundancy_factor=1, phase=1, nexus=None)
    hub.consistency_critic_count = 3

    outputs = ["REVISE:\n- LANGUAGE: PYTHON\n- EVIDENCE: main.py:L1\n- MISSING: tests\n- SUGGEST: add tests\n- NOTES: none", "OK", "OK"]
    overmind.DroneAgent = lambda *args, **kwargs: FakeDrone(outputs)

    passed, feedback = await hub._consistency_audit_shard(
        "A",
        "Do the thing",
        "output",
        {"depends_on": [], "inputs": [], "outputs": [], "success_criteria": []},
    )
    assert passed is False
    assert "REVISE" in feedback
    assert "LANGUAGE" in feedback

    outputs = [
        "OK\nLANGUAGE: PYTHON\nEVIDENCE: main.py:L1\nMISSING: none\nSUGGEST: none\nNOTES: none",
        "OK\nLANGUAGE: PYTHON\nEVIDENCE: src/app.py:L2\nMISSING: none\nSUGGEST: none\nNOTES: none",
        "OK\nLANGUAGE: PYTHON\nEVIDENCE: lib/core.py:L3\nMISSING: none\nSUGGEST: none\nNOTES: none",
    ]
    overmind.DroneAgent = lambda *args, **kwargs: FakeDrone(outputs)

    passed, feedback = await hub._consistency_audit_shard(
        "B",
        "Do the other thing",
        "output",
        {"depends_on": [], "inputs": [], "outputs": [], "success_criteria": []},
    )
    if not passed:
        raise AssertionError(f"Expected pass but got fail: {feedback}")
    assert feedback == ""


if __name__ == "__main__":
    asyncio.run(run_tests())
    print("test_consistency_critic.py: OK")
