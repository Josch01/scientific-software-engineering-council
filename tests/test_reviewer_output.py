import json
from pathlib import Path
import tempfile
import unittest

from scripts.reviewer_output import extract_final_response


class ReviewerOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "stdout.jsonl"

    def write_events(self, events):
        self.path.write_text("".join(json.dumps(event) + "\n" for event in events),
                             encoding="utf-8")

    def test_codex_extracts_one_completed_agent_message_before_success(self):
        self.write_events([
            {"type": "thread.started", "thread_id": "session-1"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "{\"verdict\":\"FINDINGS\"}"}},
            {"type": "turn.completed", "usage": {}},
        ])

        self.assertEqual(extract_final_response("codex", self.path),
                         '{"verdict":"FINDINGS"}')

    def test_gemini_extracts_one_assistant_message_before_success(self):
        self.write_events([
            {"type": "init", "session_id": "session-1"},
            {"type": "message", "role": "assistant", "content": "{\"verdict\":\"CLEAR\"}"},
            {"type": "result", "status": "success", "stats": {}},
        ])

        self.assertEqual(extract_final_response("gemini", self.path),
                         '{"verdict":"CLEAR"}')

    def test_missing_or_failed_terminal_event_is_rejected(self):
        cases = (
            ([{"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}}],
             "codex"),
            ([{"type": "message", "role": "assistant", "content": "ok"},
              {"type": "result", "status": "error", "stats": {}}], "gemini"),
        )
        for events, provider in cases:
            with self.subTest(provider=provider, events=events):
                self.write_events(events)
                with self.assertRaises(ValueError):
                    extract_final_response(provider, self.path)

    def test_multiple_candidate_responses_are_rejected_as_ambiguous(self):
        self.write_events([
            {"type": "item.completed", "item": {"type": "agent_message", "text": "first"}},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "second"}},
            {"type": "turn.completed", "usage": {}},
        ])

        with self.assertRaisesRegex(ValueError, "ambiguous"):
            extract_final_response("codex", self.path)

    def test_response_after_terminal_is_rejected(self):
        self.write_events([
            {"type": "turn.completed", "usage": {}},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "late"}},
        ])

        with self.assertRaises(ValueError):
            extract_final_response("codex", self.path)

    def test_malformed_json_duplicate_keys_and_invalid_response_types_are_rejected(self):
        malformed = (
            b'{"type":"turn.completed","usage":{}}\n{broken\n',
            b'{"type":"turn.completed","type":"turn.completed","usage":{}}\n',
        )
        for content in malformed:
            with self.subTest(content=content):
                self.path.write_bytes(content)
                with self.assertRaises(ValueError):
                    extract_final_response("codex", self.path)

        self.write_events([
            {"type": "item.completed", "item": {"type": "agent_message", "text": []}},
            {"type": "turn.completed", "usage": {}},
        ])
        with self.assertRaises(ValueError):
            extract_final_response("codex", self.path)

    def test_blank_responses_and_unsupported_provider_are_rejected(self):
        self.write_events([
            {"type": "item.completed", "item": {"type": "agent_message", "text": "  "}},
            {"type": "turn.completed", "usage": {}},
        ])
        with self.assertRaises(ValueError):
            extract_final_response("codex", self.path)

        with self.assertRaisesRegex(ValueError, "unsupported"):
            extract_final_response("fake", self.path)

    def test_output_size_is_bounded(self):
        self.path.write_bytes(b" " * (16 * 1024 * 1024 + 1))

        with self.assertRaisesRegex(ValueError, "too large"):
            extract_final_response("codex", self.path)

    def test_missing_file_is_reported_as_value_error(self):
        with self.assertRaises(ValueError):
            extract_final_response("codex", self.path)


if __name__ == "__main__":
    unittest.main()
