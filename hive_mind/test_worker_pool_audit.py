from worker_pool import WorkerPool


def test_audit_interpretation():
    cases = [
        ("OK", True),
        ("ok", True),
        ("REVISE: missing symbol", False),
        ("PASS", True),
        ("FAIL: parse error", False),
        ("OK REVISE: conflict", False),
        ("", False),
    ]

    for text, expected in cases:
        passed, _, _ = WorkerPool._interpret_audit_result(text)
        assert passed == expected, (text, passed, expected)


if __name__ == "__main__":
    test_audit_interpretation()
    print("test_worker_pool_audit.py: OK")
