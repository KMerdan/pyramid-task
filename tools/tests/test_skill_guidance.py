"""Maintainer validator and trace grader false-positive regression tests."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validate_skill_guidance import anchors, frontmatter, references, scalar, ui_metadata, validate
from eval_skill_guidance import CASES, ROOT, grade, read_events, valid_response


class MetadataTests(unittest.TestCase):
    def test_reject_duplicate_missing_nested_and_implicit_scalar_metadata(self):
        for text in [
            "---\nname: take\nname: audit\ndescription: A claim\n---\n",
            "---\nname: take\n---\n",
            "---\nname: take\ndescription: |\n  A claim\n---\n",
            "---\nname: take\ndescription: 123\n---\n",
            "---\nname: take\ndescription: true\n---\n",
            "---\nname: take\ndescription: null\n---\n",
            "---\nname: take\ndescription: A claim # hidden\n---\n",
            "---\nname: take\ndescription: A claim\n",
        ]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                frontmatter(text)

    def test_quoted_colon_and_unicode_roundtrip(self):
        description = 'Claim: "one" task — 当前上下文'
        text = '---\nname: take\ndescription: ' + json.dumps(description) + '\n---\n'
        self.assertEqual(frontmatter(text)["description"], description)
        self.assertEqual(scalar("An ordinary apostrophe's string"), "An ordinary apostrophe's string")

    def test_ui_rejects_non_string_and_unknown_keys(self):
        for text in [
            'interface:\n  display_name: []\n  short_description: "A description that is long enough"\n  default_prompt: "Use $take"',
            'interface:\n  display_name: "Take"\n  short_description: "A description that is long enough"\n  default_prompt: "Use $take"\npolicy:\n  allow_implicit_invocation: false',
        ]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                ui_metadata(text)

    def test_links_reject_missing_anchor_file_and_plugin_escape(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.md"
            source.write_text("# A, heading\n[ok](#a-heading)\n")
            self.assertEqual(references(source, root), ["#a-heading"])
            for target in ["#absent", "absent.md", "../outside.md"]:
                source.write_text(f"# A, heading\n[bad]({target})\n")
                with self.subTest(target=target), self.assertRaises(ValueError):
                    references(source, root)

    def test_fenced_headings_do_not_satisfy_links(self):
        self.assertEqual(anchors("# Visible\n```md\n## Invisible\n```\n# Visible\n"), {"visible", "visible-1"})

    def test_repository_profile_accepts_current_skills(self):
        result = validate(ROOT / "plugins/pyramid-task")
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(len(result["skills"]), 17)


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.plugin = Path("/tmp/evaluation/plugin")
        self.case = next(c for c in json.loads(CASES.read_text())["cases"] if c["id"] == "helper-preflight")
        self.response = {"primary_skill": "pyramid-task:take", "next_action": "bounded-helper",
                         "helper": "consider-preflight", "reasoning": "Read the contract before choosing.",
                         "limitations": "No actual dispatch or task execution."}
        self.events = [
            {"type": "system", "subtype": "init", "plugins": [{"path": str(self.plugin)}], "model": "fixture-model"},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "skill", "name": "Skill", "input": {"skill": "pyramid-task:take"}},
                {"type": "tool_use", "id": "read", "name": "Read", "input": {"file_path": str(self.plugin / "references/intra-task-helpers.md")}},
            ]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "skill", "content": "loaded"},
                {"type": "tool_result", "tool_use_id": "read", "content": "contract"},
            ]}},
            {"type": "result", "is_error": False, "structured_output": self.response},
        ]

    def test_positive_fixture_is_trace_assertion_not_semantic_certification(self):
        result = grade(self.events, self.case, self.plugin)
        self.assertTrue(result["automated_pass"])
        self.assertEqual(result["semantic_review"]["status"], "pending")
        self.assertIsNone(result["usage"])

    def test_self_report_without_successful_skill_load_does_not_pass(self):
        self.events[2]["message"]["content"][0]["is_error"] = True
        self.assertFalse(grade(self.events, self.case, self.plugin)["assertions"]["native_skill_loaded"])

    def test_denied_reference_read_does_not_pass(self):
        self.events[2]["message"]["content"][1]["is_error"] = True
        self.assertFalse(grade(self.events, self.case, self.plugin)["assertions"]["required_reference_reads"])

    def test_reading_installed_reference_does_not_qualify_candidate(self):
        self.events[1]["message"]["content"][1]["input"]["file_path"] = "/tmp/installed/references/intra-task-helpers.md"
        self.assertFalse(grade(self.events, self.case, self.plugin)["assertions"]["required_reference_reads"])

    def test_other_plugin_binding_is_not_candidate_binding(self):
        self.events[0]["plugins"][0]["path"] = "/tmp/installed"
        self.assertFalse(grade(self.events, self.case, self.plugin)["assertions"]["candidate_plugin_bound"])

    def test_same_named_skill_from_another_plugin_does_not_pass(self):
        self.events[1]["message"]["content"][0]["input"]["skill"] = "other-plugin:take"
        self.assertFalse(grade(self.events, self.case, self.plugin)["assertions"]["native_skill_loaded"])

    def test_contract_supported_helper_route_is_accepted_but_unrelated_route_is_not(self):
        for skill, expected in [("orchestrate", True), ("create", False)]:
            self.response["primary_skill"] = "pyramid-task:" + skill
            self.events[1]["message"]["content"][0]["input"]["skill"] = "pyramid-task:" + skill
            self.assertEqual(grade(self.events, self.case, self.plugin)["assertions"]["reported_route"], expected)

    def test_no_helper_alias_is_case_scoped_and_does_not_accept_a_candidate_helper(self):
        case = next(c for c in json.loads(CASES.read_text())["cases"] if c["id"] == "small-fix")
        for helper, expected in [("none", True), ("serial", True), ("consider-candidate", False)]:
            self.response["helper"] = helper
            self.assertEqual(grade(self.events, case, self.plugin)["assertions"]["reported_helper_choice"], expected)
        self.response["helper"] = "serial"
        self.assertFalse(grade(self.events, self.case, self.plugin)["assertions"]["reported_helper_choice"])

    def test_unauthorized_tool_request_fails_even_when_reported_choice_is_correct(self):
        self.events[1]["message"]["content"].append({"type": "tool_use", "id": "agent", "name": "Agent", "input": {}})
        self.assertFalse(grade(self.events, self.case, self.plugin)["assertions"]["only_allowed_tools_requested"])

    def test_incomplete_or_malformed_final_is_not_a_pass(self):
        self.assertFalse(grade(self.events[:-1], self.case, self.plugin)["automated_pass"])
        for response in [{}, dict(self.response, primary_skill=None), dict(self.response, extra="unexpected")]:
            self.assertFalse(valid_response(response))

    def test_invalid_jsonl_is_preserved_and_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            trace = Path(temporary) / "trace.jsonl"
            trace.write_text('{}\nnot json\n[]\n')
            events, invalid = read_events(trace)
            self.assertEqual(events, [{}])
            self.assertEqual(invalid, [2, 3])


if __name__ == "__main__":
    unittest.main()
