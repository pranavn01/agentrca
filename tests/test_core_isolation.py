"""D15 structural guard: the core stays plug-in-free and domain-agnostic."""

import ast
import re
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent / "src" / "rca" / "core"
FORBIDDEN_IMPORT_PREFIXES = ("rca.adapters", "rca.verifiers", "rca.llm")
FORBIDDEN_NOUNS = ["jira", "swe", "repro", "patch", "openhands", "langgraph", "otel"]


def core_modules() -> list[Path]:
    return sorted(CORE.rglob("*.py"))


def test_core_exists():
    assert CORE.is_dir() and core_modules()


def test_core_imports_no_plugins():
    for path in core_modules():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert not name.startswith(FORBIDDEN_IMPORT_PREFIXES), (
                    f"{path.name} imports {name}; core must not import plug-ins (D15)"
                )


def test_core_contains_no_domain_nouns():
    pattern = re.compile(r"\b(" + "|".join(FORBIDDEN_NOUNS) + r")\b", re.IGNORECASE)
    for path in core_modules():
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            match = pattern.search(line)
            assert match is None, (
                f"{path.name}:{lineno} contains domain noun '{match.group()}' (D15)"
            )
