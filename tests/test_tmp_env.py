"""Regression tests for issue #6: Dockerfile ENV keywords are case-insensitive.

Run with `python3 tests/test_tmp_env.py` or `pytest tests/test_tmp_env.py`.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_configs as v  # noqa: E402


def test_env_keyword_cases() -> None:
    """Lowercase, mixed-case and uppercase keywords are all detected."""
    cases = {
        "env": "env CASE_LOWER=1",
        "Env": "Env CASE_MIXED=1",
        "ENV": "ENV CASE_UPPER=1",
    }
    for keyword, instruction in cases.items():
        names = v.parse_dockerfile_env("FROM alpine\n" + instruction + "\n")
        expected = instruction.split()[1].split("=", 1)[0]
        assert names == {expected}, f"{keyword} instruction was not parsed: {names}"


def test_env_multiline_keyword_cases() -> None:
    """Every casing also works for a continued (multiline) ENV instruction."""
    cases = {
        "env": ("envLOWER_A", "envLOWER_B"),
        "Env": ("EnvMIXED_A", "EnvMIXED_B"),
        "ENV": ("ENVUPPER_A", "ENVUPPER_B"),
    }
    for keyword, (first, second) in cases.items():
        dockerfile = (
            "FROM alpine\n"
            f"{keyword} {first}=1 \\\n"
            f"  {second}=2\n"
        )
        names = v.parse_dockerfile_env(dockerfile)
        assert names == {first, second}, (
            f"multiline {keyword} instruction was not finalized: {names}"
        )


if __name__ == "__main__":
    test_env_keyword_cases()
    test_env_multiline_keyword_cases()
    print("ENV keyword-case tests passed")
