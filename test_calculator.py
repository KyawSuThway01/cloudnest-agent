"""Simple tests for the calculator tool. Run with: python test_calculator.py

No pytest needed and no Gemini call is made. Importing agent.py only needs
GEMINI_API_KEY to be set (it is read from .env).
"""

from agent import calculator, load_policy


def test_refund_example():
    # Annual plan cancelled after 5 months: 7 full unused months, 10% fee
    assert calculator("(200 / 12) * 7 * 0.90") == "105.0"


def test_operator_precedence():
    assert calculator("2 + 3 * 4") == "14"


def test_division_by_zero_returns_error():
    assert calculator("1 / 0").startswith("Error")


def test_rejects_unsafe_input():
    assert calculator("__import__('os').system('echo hi')").startswith("Error")


def test_rejects_huge_exponent():
    assert calculator("9 ** 999").startswith("Error")


def test_policy_document_loads():
    assert "Annual" in load_policy()


if __name__ == "__main__":
    tests = [
        test_refund_example,
        test_operator_precedence,
        test_division_by_zero_returns_error,
        test_rejects_unsafe_input,
        test_rejects_huge_exponent,
        test_policy_document_loads,
    ]
    for test in tests:
        test()
        print(f"PASS  {test.__name__}")
    print(f"\nAll {len(tests)} tests passed.")