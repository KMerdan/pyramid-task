"""Packaging/entrypoint checks only; actual drafts need semantic evaluation."""
from pathlib import Path
import json
import re
import unittest


PLUGIN = Path(__file__).resolve().parents[1]


class GoalPromptPackagingTests(unittest.TestCase):
    def test_shared_skill_is_discoverable_with_valid_metadata_and_references(self):
        skill = PLUGIN / 'skills/goal-prompt'
        text = (skill / 'SKILL.md').read_text()
        frontmatter = dict(line.split(': ', 1) for line in text.split('---', 2)[1].strip().splitlines())
        self.assertEqual('goal-prompt', frontmatter['name'])
        self.assertIsInstance(frontmatter['description'], str)
        metadata = (skill / 'agents/openai.yaml').read_text()
        # The repository's metadata uses simple JSON-quoted YAML strings.
        # Full YAML syntax is checked separately by the bundled validator.
        interface = {key: json.loads(value) for key, value in
                     re.findall(r'^  ([a-z_]+): (".*")$', metadata, re.MULTILINE)}
        self.assertTrue(25 <= len(interface['short_description']) <= 64)
        self.assertIn('$goal-prompt', interface['default_prompt'])
        self.assertNotIn('allow_implicit_invocation: false', metadata)
        for reference in re.findall(r'`(../../references/[^`]+)`', text):
            self.assertTrue((skill / reference).resolve().is_file(), reference)

    def test_entry_has_no_runtime_script_or_second_canonical_store(self):
        # This is a drafting method, not an autonomous controller. This check
        # cannot establish model compliance with its permission instructions.
        skill = PLUGIN / 'skills/goal-prompt'
        self.assertEqual({'SKILL.md', 'agents/openai.yaml'},
                         {p.relative_to(skill).as_posix() for p in skill.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()
