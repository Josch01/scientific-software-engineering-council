"""Portable role-owned work contracts; local validation grants no acceptance authority."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable


_FIELDS = frozenset({"id", "role", "reason", "risk", "inputs", "outputs", "dependencies",
                     "file_ownership", "tests", "required_reviewers", "acceptance_criteria"})
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_RESERVED = frozenset({"con", "prn", "aux", "nul", "conin$", "conout$"} |
                      {f"{prefix}{i}" for prefix in ("com", "lpt") for i in range(1, 10)})


@dataclass(frozen=True)
class WorkItem:
    id: str
    role: str
    reason: str
    risk: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    dependencies: tuple[str, ...]
    file_ownership: tuple[str, ...]
    tests: tuple[str, ...]
    required_reviewers: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip() or "\x00" in value:
        raise ValueError(f"{label} must be a nonempty NUL-free string")
    return value


def _strings(value: Any, label: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if type(value) is not list or (nonempty and not value):
        raise ValueError(f"{label} must be {'a nonempty' if nonempty else 'a'} list")
    result = tuple(_text(entry, label) for entry in value)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must not contain duplicates")
    return result


def _path(value: str, label: str) -> str:
    """Validate once and preserve the explicit trailing-slash scope marker.

    POSIX spellings are already canonical. Reject rather than repair ambiguous
    Windows aliases so the same packet has the same interpretation on both OSes.
    """
    if any(ord(char) < 32 for char in value) or any(char in value for char in '\\:*?[]<>|"'):
        raise ValueError(f"{label} must use safe repository-relative POSIX paths")
    components = value[:-1].split("/") if value.endswith("/") else value.split("/")
    for component in components:
        if (component in {"", ".", ".."} or component.endswith((".", " ")) or
                component.casefold() == ".git" or
                component.split(".", 1)[0].casefold() in _RESERVED):
            raise ValueError(f"{label} contains an unsafe or ambiguous path component")
    return value


def _paths(value: Any, label: str, *, nonempty: bool = False) -> tuple[str, ...]:
    return tuple(_path(entry, label) for entry in _strings(value, label, nonempty=nonempty))


def _covers(scope: str, output: str) -> bool:
    if scope.endswith("/"):
        return output.startswith(scope)
    return scope == output


def _collides(first: str, second: str) -> bool:
    # Even file scopes cannot occupy an ancestor of another role's file.
    first, second = first.rstrip("/").casefold(), second.rstrip("/").casefold()
    return first == second or first.startswith(second + "/") or second.startswith(first + "/")


def validate_work_items(task: dict[str, Any], worker_roles: Iterable[str],
                        required_reviewers: Iterable[str], check_ids: Iterable[str]) -> dict[str, WorkItem]:
    """Return immutable contracts keyed by router-selected worker role.

    Legacy packets may be loaded by the coordinator, but are not integration
    contracts: callers must explicitly handle missing ``work_items``.
    """
    if type(task) is not dict or type(task.get("work_items")) is not list:
        raise ValueError("work_items must be a list; integration requires role-owned work_items")
    roles, reviewers, checks = set(worker_roles), set(required_reviewers), set(check_ids)
    result: dict[str, WorkItem] = {}
    ids: set[str] = set()
    scopes: list[tuple[str, str]] = []
    for raw in task["work_items"]:
        if type(raw) is not dict or set(raw) != _FIELDS:
            raise ValueError("work_items entries must contain exactly the declared fields")
        identifier = _text(raw["id"], "work item id")
        if not _ID.fullmatch(identifier) or identifier.casefold() in ids:
            raise ValueError("work item IDs must be unique portable identifiers")
        ids.add(identifier.casefold())
        role = _text(raw["role"], "work item role")
        if role not in roles or role in result:
            raise ValueError("work_items must match the router worker role set exactly")
        reason = _text(raw["reason"], "work item reason")
        risk = _text(raw["risk"], "work item risk")
        if risk not in {"R0", "R1", "R2", "R3"}:
            raise ValueError("work item risk must be R0, R1, R2, or R3")
        inputs = _paths(raw["inputs"], "inputs")
        outputs = _paths(raw["outputs"], "outputs", nonempty=True)
        ownership = _paths(raw["file_ownership"], "file_ownership", nonempty=True)
        dependencies = _strings(raw["dependencies"], "dependencies")
        if dependencies:
            raise ValueError("work item dependencies are unsupported and must be empty")
        tests = _strings(raw["tests"], "tests", nonempty=bool(checks))
        if not set(tests) <= checks:
            raise ValueError("work item tests must reference declared check_specs IDs")
        item_reviewers = _strings(raw["required_reviewers"], "required_reviewers")
        if set(item_reviewers) != reviewers:
            raise ValueError("work item required_reviewers must match initialized reviewer roles")
        criteria = _strings(raw["acceptance_criteria"], "acceptance_criteria", nonempty=True)
        if any(not any(_covers(scope, output) for scope in ownership) for output in outputs):
            raise ValueError("work item outputs must be covered by file_ownership")
        for scope in ownership:
            if any(other_role != role and _collides(scope, other) for other_role, other in scopes):
                raise ValueError("work item file_ownership overlaps across roles")
            scopes.append((role, scope))
        result[role] = WorkItem(identifier, role, reason, risk, inputs, outputs, dependencies,
                                ownership, tests, item_reviewers, criteria)
    if set(result) != roles:
        raise ValueError("work_items must match the router worker role set exactly")
    return result
