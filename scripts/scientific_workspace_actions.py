"""Human-approved, host-injected simulation callbacks for loaded workspaces."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import re
import threading
from types import MappingProxyType

try:
    from .scientific_core import OdeSolution, SirModelDefinition, solve_sir_model
    from .scientific_workspace_loader import LoadedWorkspace
    from .scientific_workspace_view import ComponentView, build_simulation_result_view
except ImportError:  # Support direct execution/import from scripts directory.
    from scientific_core import OdeSolution, SirModelDefinition, solve_sir_model
    from scientific_workspace_loader import LoadedWorkspace
    from scientific_workspace_view import ComponentView, build_simulation_result_view


_WORKSPACE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_RUN_TOKEN = object()


@dataclass(frozen=True, slots=True)
class ApprovedSimulationAction:
    """Callback supplied by trusted host code; projects cannot register callbacks."""

    workspace_id: str
    label: str
    callback: Callable[[LoadedWorkspace, ComponentView], OdeSolution]

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_id, str) or not _WORKSPACE_ID.fullmatch(self.workspace_id):
            raise ValueError("approved action workspace_id must be a portable workspace ID")
        if (not isinstance(self.label, str) or not self.label.strip() or len(self.label) > 120
                or any(ord(character) < 32 for character in self.label)):
            raise ValueError("approved action label must be a short printable string")
        if not callable(self.callback):
            raise ValueError("approved action callback must be callable")


class ApprovedSimulationRun:
    """One-shot execution ticket returned only after the UI's human confirmation."""

    __slots__ = ("action", "workspace", "component", "_used", "_lock")

    def __init__(
        self,
        action: ApprovedSimulationAction,
        workspace: LoadedWorkspace,
        component: ComponentView,
        *,
        _token: object | None = None,
    ) -> None:
        if _token is not _RUN_TOKEN:
            raise TypeError("simulation run tickets require human confirmation")
        self.action = action
        self.workspace = workspace
        self.component = component
        self._used = False
        self._lock = threading.Lock()

    def consume(self) -> None:
        with self._lock:
            if self._used:
                raise RuntimeError("simulation approval ticket was already consumed")
            self._used = True


def _simulation_config(workspace: LoadedWorkspace, component_id: str) -> Mapping[str, object]:
    for section in workspace.manifest["sections"]:
        for raw_component in section["components"]:
            if raw_component["id"] == component_id:
                if raw_component["type"] != "simulation_plot":
                    break
                return raw_component["config"]
    raise ValueError("simulation_plot component is not part of the verified workspace")


def request_approved_simulation(
    action: ApprovedSimulationAction,
    workspace: LoadedWorkspace,
    component: ComponentView,
    *,
    confirm: Callable[[str], bool],
) -> ApprovedSimulationRun | None:
    """Ask for human confirmation and return a one-shot ticket, without running code."""
    if not isinstance(action, ApprovedSimulationAction):
        raise TypeError("action must be an ApprovedSimulationAction from trusted host code")
    if not isinstance(workspace, LoadedWorkspace):
        raise TypeError("workspace must come from the safe workspace loader")
    if not isinstance(component, ComponentView) or component.component_type != "simulation_plot":
        raise ValueError("approved simulation actions require a simulation_plot component")
    if workspace.summary.workspace_id != action.workspace_id:
        raise ValueError("approved action workspace_id does not match the loaded workspace")
    _simulation_config(workspace, component.component_id)
    if not callable(confirm):
        raise TypeError("confirm must be a human confirmation callback")
    prompt = (
        "Esta acción ejecutará código Python confiable en el proceso local de SSEC.\n\n"
        f"Acción: {action.label}\nEspacio: {workspace.summary.workspace_id}\n"
        f"Componente: {component.title}\n\n"
        "Confirma solo si revisaste y aprobaste la implementación del callback. "
        "No es un sandbox y el resultado no valida el modelo ni su validez científica. "
        "¿Ejecutar?"
    )
    if confirm(prompt) is not True:
        return None
    return ApprovedSimulationRun(action, workspace, component, _token=_RUN_TOKEN)


def run_approved_simulation(ticket: ApprovedSimulationRun) -> ComponentView:
    """Run one confirmed callback and return a schema-validated in-memory view."""
    if not isinstance(ticket, ApprovedSimulationRun):
        raise TypeError("ticket must be returned by request_approved_simulation")
    ticket.consume()
    solution = ticket.action.callback(ticket.workspace, ticket.component)
    config = _simulation_config(ticket.workspace, ticket.component.component_id)
    return build_simulation_result_view(
        ticket.component,
        solution,
        series=config["series"],
        action_label=ticket.action.label,
    )


def sir_simulation_actions_for_workspace(
    workspace: LoadedWorkspace,
) -> Mapping[str, ApprovedSimulationAction]:
    """Bind the built-in SIR solver to simulation plots in one verified workspace.

    The model contract is parsed from loader-captured bytes. No project path is
    imported or reopened, and every run rechecks the resource digest.
    """
    if not isinstance(workspace, LoadedWorkspace):
        raise TypeError("workspace must come from the safe workspace loader")
    model_resources = tuple(resource for resource in workspace.resources
                            if resource.kind == "model_spec")
    if not model_resources:
        return MappingProxyType({})
    if len(model_resources) != 1:
        raise ValueError("built-in SIR action requires exactly one model_spec resource")
    model_resource = model_resources[0]
    definition = SirModelDefinition.from_json(model_resource.content)
    declared_components = {
        component["id"]: component
        for section in workspace.manifest["sections"]
        for component in section["components"]
        if component["type"] == "simulation_plot"
    }
    actions: dict[str, ApprovedSimulationAction] = {}
    label = f"SIR · RK4_FIXED_STEP · SHA-256 {model_resource.sha256}"
    for component_id, raw_component in declared_components.items():
        series = raw_component["config"]["series"]
        if any(name not in definition.state_names for name in series):
            raise ValueError(
                f"simulation_plot {component_id!r} requests a state outside the SIR model"
            )
        def callback(
            loaded: LoadedWorkspace,
            _component: ComponentView,
            *,
            expected_workspace_id=workspace.summary.workspace_id,
            expected_resource_id=model_resource.resource_id,
            expected_sha256=model_resource.sha256,
            model=definition,
        ) -> OdeSolution:
            if loaded.summary.workspace_id != expected_workspace_id:
                raise ValueError("approved SIR action belongs to a different workspace")
            matches = tuple(
                resource for resource in loaded.resources
                if resource.resource_id == expected_resource_id
                and resource.kind == "model_spec"
            )
            if len(matches) != 1 or matches[0].sha256 != expected_sha256:
                raise ValueError("verified SIR model_spec digest changed after approval setup")
            return solve_sir_model(model)

        actions[component_id] = ApprovedSimulationAction(
            workspace_id=workspace.summary.workspace_id,
            label=label,
            callback=callback,
        )
    return MappingProxyType(actions)
