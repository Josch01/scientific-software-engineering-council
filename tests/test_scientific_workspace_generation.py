from __future__ import annotations

import unittest
from pathlib import Path
import hashlib
import json
import tempfile
import tomllib
from unittest import mock

from scripts.agent_runtime import RuntimeCapabilities, RuntimeHandle, RuntimeResult, RuntimeStatus
from scripts.configuration import DEFAULT_CONFIG
from scripts.scientific_workspace_loader import load_scientific_workspace


try:
    from scripts import scientific_workspace_generation as generation
except ImportError:
    generation = None


def make_workspace(root: Path):
    model = b'{"model_type":"sir","status":"synthetic"}\n'
    observations = b'{"schema_version":1,"variables":[]}\n'
    evaluation = b'{"schema_version":1,"method":"test"}\n'
    unused = b"must not be sent to the agent"
    for path, content in (("models/sir.json", model),
                          ("data/observations.json", observations),
                          ("results/evaluation.json", evaluation),
                          ("private/unused.txt", unused)):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    resources = []
    for resource_id, kind, path, content in (
        ("model", "model_spec", "models/sir.json", model),
        ("observations", "observations", "data/observations.json", observations),
        ("evaluation", "observation_evaluation", "results/evaluation.json", evaluation),
        ("unused", "generic", "private/unused.txt", unused),
    ):
        resources.append({"id": resource_id, "kind": kind, "path": path,
                          "sha256": hashlib.sha256(content).hexdigest()})
    manifest = {
        "schema_version": 1,
        "workspace_id": "sir-study",
        "title": "Current SIR study",
        "resources": resources,
        "sections": [
            {"id": "model", "title": "Model", "components": [{
                "id": "equations", "type": "equation_view", "title": "Equations",
                "resource_refs": ["model"], "config": {},
            }]},
            {"id": "data", "title": "Data", "components": [{
                "id": "observations-view", "type": "observation_table",
                "title": "Observations", "resource_refs": ["observations"], "config": {},
            }]},
            {"id": "private", "title": "Private", "components": [{
                "id": "unused-view", "type": "artifact_browser", "title": "Unused",
                "resource_refs": ["unused"], "config": {},
            }]},
        ],
    }
    (root / "workspace.json").write_text(json.dumps(manifest), encoding="utf-8")
    return load_scientific_workspace(root, "workspace.json"), model, observations, unused


def layout_payload():
    return {
        "title": "SIR analysis",
        "description": "Synthetic workspace proposal",
        "sections": [
            {"id": "model", "title": "Model", "components": [{
                "id": "equations", "type": "equation_view", "title": "Equations",
                "resource_refs": ["model"], "config": {},
            }]},
            {"id": "data", "title": "Data", "components": [{
                "id": "observations-view", "type": "observation_table",
                "title": "Observations", "resource_refs": ["observations"], "config": {},
            }]},
        ],
    }


def marked_layout(payload=None):
    text = json.dumps(payload if payload is not None else layout_payload(), separators=(",", ":"))
    return f"{generation.BEGIN_MARKER}\n{text}\n{generation.END_MARKER}"


class StaticRuntime:
    def __init__(self, provider: str, *, available: bool = True, output: str | None = None,
                 safe_proposal_mode: bool | None = None):
        self.provider = provider
        self.available = available
        self.output = output if output is not None else marked_layout()
        if safe_proposal_mode is None:
            safe_proposal_mode = provider == "gemini" and available
        self.features = (("proposal_read_only_tool_policy",) if safe_proposal_mode else ())
        self.request = None
        self.tool_policy_contents = None
        self.stage_files = ()
        self.cleaned = False
        self.cancelled = False

    def discover_capabilities(self):
        return RuntimeCapabilities(self.provider, self.available, "test", self.features, None,
                                   native_subagents=mock.sentinel.native_agents)

    def launch(self, request):
        self.request = request
        if request.tool_policy_path is not None:
            self.tool_policy_contents = request.tool_policy_path.read_text(encoding="utf-8")
        self.stage_files = tuple(sorted(
            path.relative_to(request.cwd).as_posix()
            for path in request.cwd.rglob("*") if path.is_file()
        ))
        request.stdout_path.write_text(self._events(), encoding="utf-8")
        request.stderr_path.write_text("", encoding="utf-8")
        return RuntimeHandle("static-runtime", request.run_id, self.provider, 123)

    def _events(self):
        assistant = {"type": "message", "role": "assistant", "content": self.output}
        terminal = {"type": "result", "status": "success", "stats": {}}
        if self.provider == "codex":
            assistant = {"type": "item.completed", "item": {
                "type": "agent_message", "text": self.output,
            }}
            terminal = {"type": "turn.completed", "usage": {}}
        return "\n".join(json.dumps(event) for event in (assistant, terminal)) + "\n"

    def status(self, _handle):
        return RuntimeStatus.SUCCEEDED

    def stream_or_collect(self, handle):
        return RuntimeResult(
            schema_version=1, run_id=handle.run_id, provider=self.provider,
            status=RuntimeStatus.SUCCEEDED, exit_code=0, provider_session_id="test-session",
            stdout_path=self.request.stdout_path, stderr_path=self.request.stderr_path,
            stdout_sha256=hashlib.sha256(self.request.stdout_path.read_bytes()).hexdigest(),
            stderr_sha256=hashlib.sha256(b"").hexdigest(),
            started_at_utc="2026-01-01T00:00:00+00:00",
            finished_at_utc="2026-01-01T00:00:01+00:00",
            observed_child_agent_ids=(), error=None,
        )

    def cancel(self, _handle):
        self.cancelled = True
        return mock.sentinel.cancelled

    def timeout(self, _handle):
        self.cancelled = True
        return mock.sentinel.timed_out

    def cleanup(self, _handle):
        self.cleaned = True


class WorkspaceProposalGenerationTests(unittest.TestCase):
    def test_generation_module_exposes_safe_proposal_api(self):
        repository = Path(__file__).resolve().parents[1]
        module = repository / "scripts" / "scientific_workspace_generation.py"
        self.assertTrue(module.is_file(), "workspace proposal generation API is missing")


@unittest.skipIf(generation is None, "generation API is implemented in the next step")
class WorkspaceProposalGenerationBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace, self.model, self.observations, self.unused = make_workspace(self.root)
        self.original_admin_policy_check = generation.gemini_admin_policy_overrides_present
        policy_check = mock.patch.object(
            generation, "gemini_admin_policy_overrides_present", return_value=False
        )
        policy_check.start()
        self.addCleanup(policy_check.stop)

    def test_plan_includes_only_selected_verified_resources_and_bounded_objective(self):
        plan = generation.build_workspace_generation_plan(
            self.workspace, ("model", "observations"), "Add model and data views"
        )

        self.assertEqual(tuple(item.resource_id for item in plan.resources),
                         ("model", "observations"))
        self.assertIn("Add model and data views", plan.prompt)
        self.assertIn("models/sir.json", plan.prompt)
        self.assertIn("data/observations.json", plan.prompt)
        self.assertNotIn("unused", plan.prompt)
        self.assertNotIn("private/unused.txt", plan.prompt)
        with self.assertRaises(ValueError):
            generation.build_workspace_generation_plan(self.workspace, (), "show SIR")
        with self.assertRaisesRegex(ValueError, "unique"):
            generation.build_workspace_generation_plan(
                self.workspace, ("model", "model"), "show SIR"
            )

    def test_provider_candidates_exclude_codex_without_a_no_execution_policy(self):
        self.assertEqual(
            generation.configured_proposal_providers(
                dict(DEFAULT_CONFIG, provider_mode="codex")
            ),
            (),
        )
        self.assertEqual(
            generation.configured_proposal_providers(
                dict(DEFAULT_CONFIG, provider_mode="both")
            ),
            ("gemini",),
        )
        self.assertEqual(
            generation.configured_proposal_providers(
                dict(DEFAULT_CONFIG, provider_mode="agy")
            ),
            (),
        )

    def test_standard_gemini_admin_policies_disable_supplemental_proposal_policy(self):
        with tempfile.TemporaryDirectory() as system_policies:
            directory = Path(system_policies)
            with mock.patch.object(
                generation, "gemini_standard_admin_policy_directory", return_value=directory
            ):
                self.assertFalse(self.original_admin_policy_check())
                (directory / "local.toml").write_text("[[rule]]\n", encoding="utf-8")
                self.assertTrue(self.original_admin_policy_check())

    def test_selected_snapshot_excludes_unselected_project_files(self):
        plan = generation.build_workspace_generation_plan(
            self.workspace, ("model", "observations"), "show SIR"
        )
        with tempfile.TemporaryDirectory() as stage:
            paths = generation.stage_workspace_generation_inputs(plan, Path(stage))
            self.assertIn("models/sir.json", paths)
            self.assertIn("data/observations.json", paths)
            self.assertIn("ssec-workspace-context.json", paths)
            self.assertFalse((Path(stage) / "private" / "unused.txt").exists())
            self.assertEqual((Path(stage) / "models/sir.json").read_bytes(), self.model)
            self.assertEqual((Path(stage) / "data/observations.json").read_bytes(),
                             self.observations)

    def test_extracts_only_marked_assistant_output_for_supported_local_providers(self):
        for provider in ("codex", "gemini"):
            with self.subTest(provider=provider):
                runtime = StaticRuntime(provider)
                self.assertEqual(
                    generation.extract_workspace_layout(provider, runtime._events()),
                    layout_payload(),
                )

    def test_provider_output_parser_rejects_missing_duplicate_and_invalid_json_markers(self):
        cases = (
            ("codex", b'{"type":"turn.completed","usage":{}}\n'),
            ("gemini", ("{}\n" + "{}\n").encode()),
        )
        for provider, output in cases:
            with self.subTest(provider=provider), self.assertRaises(ValueError):
                generation.extract_workspace_layout(provider, output)

        duplicate = layout_payload()
        duplicate_text = json.dumps(duplicate, separators=(",", ":")).replace(
            '"title":"SIR analysis",', '"title":"SIR analysis","title":"forged",', 1
        )
        event_text = f"{generation.BEGIN_MARKER}\n{duplicate_text}\n{generation.END_MARKER}"
        output = "\n".join((
            json.dumps({"type": "message", "role": "assistant", "content": event_text}),
            json.dumps({"type": "result", "status": "success", "stats": {}}),
        ))
        with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
            generation.extract_workspace_layout("gemini", output)

    def test_candidate_manifest_contains_selected_digests_and_passes_workspace_validator(self):
        plan = generation.build_workspace_generation_plan(
            self.workspace, ("model", "observations"), "Create a scientific view"
        )
        manifest = generation.build_workspace_proposal_manifest(plan, layout_payload())

        from scripts.scientific_workspace import validate_workspace_manifest
        summary = validate_workspace_manifest(manifest)
        self.assertEqual(summary.workspace_id, "sir-study")
        self.assertEqual(summary.title, "SIR analysis")
        self.assertEqual([item["id"] for item in manifest["resources"]],
                         ["model", "observations"])
        self.assertEqual(manifest["resources"][0]["sha256"],
                         hashlib.sha256(self.model).hexdigest())
        self.assertNotIn("unused", json.dumps(manifest))

    def test_proposal_can_link_only_selected_model_and_observation_context(self):
        manifest_path = self.root / "workspace.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        fit_content = b'{"schema_version":1,"status":"CONVERGED"}\n'
        simulation_content = b'{"schema_version":1,"method":"RK4_FIXED_STEP"}\n'
        (self.root / "results").mkdir(exist_ok=True)
        (self.root / "results" / "fit.json").write_bytes(fit_content)
        (self.root / "results" / "simulation.json").write_bytes(simulation_content)
        manifest["resources"].append({
            "id": "fit", "kind": "fit_result", "path": "results/fit.json",
            "sha256": hashlib.sha256(fit_content).hexdigest(),
        })
        manifest["resources"].append({
            "id": "simulation", "kind": "simulation_result", "path": "results/simulation.json",
            "sha256": hashlib.sha256(simulation_content).hexdigest(),
        })
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        workspace = load_scientific_workspace(self.root, "workspace.json")
        plan = generation.build_workspace_generation_plan(
            workspace, ("model", "observations", "fit", "simulation"), "Show fit with context"
        )
        layout = {
            "title": "Fit with context", "description": "Verified resource links",
            "sections": [{"id": "results", "title": "Results", "components": [{
                "id": "fit-view", "type": "fit_summary", "title": "Fit",
                "resource_refs": ["fit"],
                "config": {"parameter_names": ["beta"],
                           "context_refs": ["model", "observations"]},
            }, {
                "id": "simulation-view", "type": "simulation_plot", "title": "Simulation",
                "resource_refs": ["simulation"],
                "config": {"x_axis": "time", "series": ["S"],
                           "context_refs": ["model"]},
            }]}],
        }

        proposal = generation.build_workspace_proposal_manifest(plan, layout)

        fit_component = proposal["sections"][0]["components"][0]
        simulation_component = proposal["sections"][0]["components"][1]
        self.assertEqual(fit_component["config"]["context_refs"], ["model", "observations"])
        self.assertEqual(simulation_component["config"]["context_refs"], ["model"])
        self.assertIn("optional_config", plan.prompt)
        layout["sections"][0]["components"][0]["config"]["context_refs"] = ["unused"]
        with self.assertRaisesRegex(ValueError, "unknown context resource reference"):
            generation.build_workspace_proposal_manifest(plan, layout)

    def test_residual_component_is_available_to_deterministic_proposals(self):
        plan = generation.build_workspace_generation_plan(
            self.workspace, ("evaluation",), "Show observations and residuals"
        )
        layout = {
            "title": "Residual analysis",
            "description": "Residual view generated without a provider call",
            "sections": [{"id": "results", "title": "Results", "components": [{
                "id": "residuals", "type": "residual_plot", "title": "Residuals",
                "resource_refs": ["evaluation"], "config": {},
            }]}],
        }

        candidate = generation.build_workspace_proposal_manifest(plan, layout)

        from scripts.scientific_workspace import validate_workspace_manifest
        summary = validate_workspace_manifest(candidate)
        self.assertEqual(summary.component_types, ("residual_plot",))

    def test_generation_persists_a_validated_unapproved_candidate_and_uses_read_only_runtime(self):
        runtime = StaticRuntime("gemini")
        config = dict(DEFAULT_CONFIG, provider_mode="gemini")
        before = {path.relative_to(self.root).as_posix(): path.read_bytes()
                  for path in self.root.rglob("*") if path.is_file()}

        result = generation.generate_workspace_proposal(
            self.root, self.workspace, ("model", "observations"),
            "Show equations, observations, and simulation", config,
            accept_unmetered_cost=True, runtime_factory=lambda _provider: runtime,
        )

        self.assertEqual(result["status"], "PROPOSAL_READY_NOT_APPROVED")
        self.assertEqual(result["release_status"], "NOT_APPROVED")
        self.assertEqual(result["scientific_validity"], "NOT_ASSESSED")
        candidate_path = self.root / result["proposal_relative_path"]
        self.assertTrue(candidate_path.is_file())
        load_scientific_workspace(self.root, result["proposal_relative_path"])
        self.assertFalse(runtime.request.writable)
        self.assertEqual(runtime.request.tool_policy_path.parent, runtime.request.cwd.parent)
        tool_policy = tomllib.loads(runtime.tool_policy_contents)
        self.assertEqual(tool_policy["rule"][0]["toolName"], "*")
        self.assertEqual(tool_policy["rule"][0]["decision"], "deny")
        self.assertEqual(tool_policy["rule"][1]["mcpName"], "*")
        self.assertEqual(tool_policy["rule"][1]["decision"], "deny")
        self.assertEqual(
            tool_policy["rule"][2]["toolName"],
            ["read_file", "list_directory", "glob", "grep_search"],
        )
        self.assertEqual(tool_policy["rule"][2]["decision"], "allow")
        self.assertTrue(runtime.request.cost_acknowledged)
        self.assertEqual(runtime.stage_files, (
            "data/observations.json", "models/sir.json", "ssec-workspace-context.json"
        ))
        self.assertTrue(runtime.cleaned)
        after = {path.relative_to(self.root).as_posix(): path.read_bytes()
                 for path in self.root.rglob("*") if path.is_file()
                 and ".ssec/runs/" not in path.relative_to(self.root).as_posix()}
        self.assertEqual(after, before)

    def test_both_provider_mode_uses_only_gemini_with_read_only_tool_policy(self):
        config = dict(DEFAULT_CONFIG, provider_mode="both")
        codex = StaticRuntime("codex", available=False)
        gemini = StaticRuntime("gemini", available=True)
        runtimes = {"codex": codex, "gemini": gemini}

        result = generation.generate_workspace_proposal(
            self.root, self.workspace, ("model",), "Create model views", config,
            accept_unmetered_cost=True, runtime_factory=lambda provider: runtimes[provider],
        )

        self.assertEqual(result["provider"], "gemini")
        self.assertIsNone(codex.request)
        self.assertIsNotNone(gemini.request)
        self.assertEqual(gemini.request.tool_policy_path.parent, gemini.request.cwd.parent)
        self.assertTrue(gemini.request.cost_acknowledged)
        self.assertEqual(result["release_status"], "NOT_APPROVED")

    def test_both_provider_mode_never_uses_codex_even_when_its_cli_is_available(self):
        config = dict(DEFAULT_CONFIG, provider_mode="both")
        codex = StaticRuntime("codex", available=True)
        gemini = StaticRuntime("gemini", available=True)
        runtimes = {"codex": codex, "gemini": gemini}

        result = generation.generate_workspace_proposal(
            self.root, self.workspace, ("model",), "Create model views", config,
            accept_unmetered_cost=True, runtime_factory=lambda provider: runtimes[provider],
        )

        self.assertEqual(result["provider"], "gemini")
        self.assertIsNone(codex.request)
        self.assertIsNotNone(gemini.request)

    def test_codex_only_mode_fails_closed_without_discovering_or_launching_provider(self):
        config = dict(DEFAULT_CONFIG, provider_mode="codex")
        factory_calls = []

        result = generation.generate_workspace_proposal(
            self.root, self.workspace, ("model",), "Create model views", config,
            accept_unmetered_cost=True,
            runtime_factory=lambda provider: factory_calls.append(provider),
        )

        self.assertEqual(result["status"], "PROVIDER_UNAVAILABLE")
        self.assertEqual(result["provider"], "codex")
        self.assertIn("no-execution", result["error"])
        self.assertEqual(factory_calls, [])
        self.assertIsNone(result["proposal_relative_path"])

    def test_gemini_without_enforced_read_only_tool_policy_is_not_launched(self):
        config = dict(DEFAULT_CONFIG, provider_mode="gemini")
        runtime = StaticRuntime("gemini", safe_proposal_mode=False)

        result = generation.generate_workspace_proposal(
            self.root, self.workspace, ("model",), "Create model views", config,
            accept_unmetered_cost=True, runtime_factory=lambda _provider: runtime,
        )

        self.assertEqual(result["status"], "PROVIDER_UNAVAILABLE")
        self.assertEqual(result["release_status"], "NOT_APPROVED")
        self.assertIsNone(runtime.request)
        self.assertIsNone(result["proposal_relative_path"])

    def test_missing_provider_keeps_failure_unapproved_and_does_not_write_candidate(self):
        runtime = StaticRuntime("codex", available=False)
        config = dict(DEFAULT_CONFIG, provider_mode="both")

        result = generation.generate_workspace_proposal(
            self.root, self.workspace, ("model",), "Create model views", config,
            accept_unmetered_cost=True, runtime_factory=lambda _provider: runtime,
        )

        self.assertEqual(result["status"], "PROVIDER_UNAVAILABLE")
        self.assertEqual(result["release_status"], "NOT_APPROVED")
        self.assertIsNone(result["proposal_relative_path"])
        self.assertEqual(runtime.provider, "codex")
        self.assertFalse(runtime.request)

    def test_declined_cost_ack_never_discovers_or_launches_provider(self):
        runtime = StaticRuntime("gemini")

        with self.assertRaisesRegex(ValueError, "explicit cost acknowledgement"):
            generation.generate_workspace_proposal(
                self.root, self.workspace, ("model",), "Create model views",
                dict(DEFAULT_CONFIG, provider_mode="gemini"),
                accept_unmetered_cost=False,
                runtime_factory=lambda _provider: runtime,
            )

        self.assertIsNone(runtime.request)


if __name__ == "__main__":
    unittest.main()
