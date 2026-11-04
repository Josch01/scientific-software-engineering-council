"""Optional PySide6 application shell for projects, agents and science workspaces."""
from __future__ import annotations

try:
    from .scientific_workspace_view import WorkspaceViewModel
    from .scientific_workspace_qt import QtCore, QtGui, QtWidgets, ScientificWorkspaceWindow
except ImportError:  # Support direct execution from scripts/.
    from scientific_workspace_view import WorkspaceViewModel
    from scientific_workspace_qt import QtCore, QtGui, QtWidgets, ScientificWorkspaceWindow


_WORKSPACE_CATEGORY_COMPONENT_TYPES = {
    "experiments": frozenset({
        "observation_table", "observation_evaluation", "simulation_plot",
    }),
    "code": frozenset({"code_view", "artifact_browser"}),
    "results": frozenset({
        "fit_summary", "sensitivity_plot", "residual_plot", "uncertainty_summary",
    }),
}


def workspace_section_index(view_model: WorkspaceViewModel, category: str) -> int | None:
    """Return the first existing workspace section relevant to a navigation category."""
    if category not in _WORKSPACE_CATEGORY_COMPONENT_TYPES:
        raise ValueError(f"unknown workspace category: {category!r}")
    component_types = _WORKSPACE_CATEGORY_COMPONENT_TYPES[category]
    for index, section in enumerate(view_model.sections):
        if any(component.component_type in component_types for component in section.components):
            return index
    return None


if QtWidgets is None:
    class ControlCenterWindow:  # pragma: no cover - Qt is optional.
        """Unavailable placeholder that keeps importing the optional shell safe."""

        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("PySide6 is required for the SSEC Control Center")

