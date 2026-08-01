#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "pyramid-task"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
FRONTMATTER_NAME = re.compile(r"^name:\s*['\"]?([a-z0-9-]+)['\"]?\s*$", re.MULTILINE)
IGNORED_TREES = {".git", ".venv", "venv"}


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain a JSON object")
    return value


def main() -> int:
    errors: list[str] = []
    manifest_path = PLUGIN / ".codex-plugin" / "plugin.json"
    marketplace_path = ROOT / ".agents" / "plugins" / "marketplace.json"

    try:
        manifest = read_json(manifest_path)
        if manifest.get("name") != "pyramid-task":
            errors.append("plugin manifest name must be pyramid-task")
        if not SEMVER.match(str(manifest.get("version", ""))):
            errors.append("plugin version must use semantic versioning")
        if manifest.get("skills") != "./skills/":
            errors.append("plugin manifest must expose ./skills/")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))

    try:
        marketplace = read_json(marketplace_path)
        entries = [item for item in marketplace.get("plugins", []) if item.get("name") == "pyramid-task"]
        if len(entries) != 1:
            errors.append("marketplace must contain exactly one pyramid-task entry")
        elif entries[0].get("source", {}).get("path") != "./plugins/pyramid-task":
            errors.append("marketplace plugin path must be ./plugins/pyramid-task")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))

    skills_dir = PLUGIN / "skills"
    skill_dirs = sorted(path for path in skills_dir.iterdir() if path.is_dir()) if skills_dir.exists() else []
    if not skill_dirs:
        errors.append("plugin must contain at least one skill")
    for skill_dir in skill_dirs:
        skill_file = skill_dir / "SKILL.md"
        agent_file = skill_dir / "agents" / "openai.yaml"
        if not skill_file.exists():
            errors.append(f"{skill_dir.name}: missing SKILL.md")
            continue
        text = skill_file.read_text(encoding="utf-8")
        match = FRONTMATTER_NAME.search(text)
        if not match or match.group(1) != skill_dir.name:
            errors.append(f"{skill_dir.name}: frontmatter name must match folder")
        if "[TODO:" in text:
            errors.append(f"{skill_dir.name}: unresolved TODO placeholder")
        if not agent_file.exists():
            errors.append(f"{skill_dir.name}: missing agents/openai.yaml")
        for reference in re.findall(r"`(\.\./\.\./(?:references|assets)/[^`]+)`", text):
            if not (skill_dir / reference).resolve().exists():
                errors.append(f"{skill_dir.name}: missing referenced resource {reference}")

    schemas = sorted((PLUGIN / "schemas").glob("*.json"))
    if not schemas:
        errors.append("plugin must publish JSON schemas")
    for schema in schemas:
        try:
            read_json(schema)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(str(exc))

    forbidden = [
        path
        for path in ROOT.rglob("*")
        if path.name in {"__pycache__", ".DS_Store"}
        and not IGNORED_TREES.intersection(path.relative_to(ROOT).parts)
    ]
    errors.extend(f"forbidden generated path: {path.relative_to(ROOT)}" for path in forbidden)

    if errors:
        print("Repository validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Repository validation passed: {len(skill_dirs)} skills, {len(schemas)} schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
