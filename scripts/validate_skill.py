#!/usr/bin/env python3
"""Structural validator for the SSEC SKILL.md bundle (not a scientific audit)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANDATORY = [
    "README.md", "SKILL.md", "references/ROUTER.md", "references/MULTI_AGENT.md",
    "references/SCIENTIFIC_BOUNDARY.md", "references/TEST_MATRIX.md",
    "references/GUI_DESKTOP.md", "references/IDL_ADAPTER.md",
    "references/DEPENDENCY_SKILLS.md", "references/RELEASE_POLICY.md",
    "references/ARCHITECTURE.md", "references/PROVIDER_MODES.md", "references/RUNNER.md",
    "references/CONFIG_PANEL.md", "scripts/configuration.py",
    "scripts/config_panel.py", "scripts/prepare_agents.py", "scripts/run_agents.py", "scripts/route_task.py", "scripts/release_gate.py",
    "templates/TASK_PACKET.json", ".github/workflows/validate.yml",
]


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for filename in MANDATORY:
        if not (root / filename).is_file():
            errors.append(f"missing: {filename}")
    skill = root / "SKILL.md"
    if not skill.is_file():
        return errors
    body = skill.read_text(encoding="utf-8")
    if not body.startswith("---\n") or "\n---\n" not in body[4:]:
        errors.append("SKILL.md must start with YAML frontmatter")
        return errors
    header = body.split("\n---\n", 1)[0].removeprefix("---\n")
    name = re.search(r"(?m)^name:\s*([a-z0-9-]+)\s*$", header)
    description = re.search(r"(?m)^description:\s*(.+)$", header)
    if name is None or name.group(1) != root.name or "--" in root.name:
        errors.append("frontmatter name must match root directory name")
    if description is None or not 1 <= len(description.group(1).strip('"\'')) <= 1024:
        errors.append("description missing or too long")
    for path in re.findall(r"`((?:references|scripts|templates)/[A-Za-z0-9_.-]+)`", body):
        if not (root / path).is_file():
            errors.append(f"SKILL.md broken path: {path}")
    for example in (root / "examples").glob("*.json"):
        try:
            json.loads(example.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid JSON {example.name}: {exc}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("INVALID SKILL\n" + "\n".join(errors))
        return 1
    print("VALID STRUCTURE — not a guarantee of software/scientific correctness")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
