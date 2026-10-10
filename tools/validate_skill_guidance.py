#!/usr/bin/env python3
"""Validate this repository's intentionally narrow skill metadata and links.

Stdlib only. This is not a general YAML parser: unsupported YAML forms fail
closed. Installed skill/runtime users do not depend on this maintainer tool.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/pyramid-task"
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def scalar(value: str) -> str:
    if value.startswith('"'):
        parsed = json.loads(value)
        if not isinstance(parsed, str):
            raise ValueError("expected a JSON-quoted string")
        return parsed
    if (not value or value != value.strip() or value[0] in "-?:,[]{}#&*!|>'%`@"
            or ": " in value or " #" in value or "\t" in value
            or value.lower() in {"null", "true", "false", "yes", "no", "on", "off", "~", ".inf", ".nan"}
            or re.match(r"^[+-]?(?:\d|\.\d)", value)):
        raise ValueError("unsupported scalar; use a plain string or JSON-quoted string")
    return value


def mapping(lines: list[str], indentation: int = 0) -> dict[str, str]:
    result = {}
    for line in lines:
        match = re.fullmatch(r" {" + str(indentation) + r"}([a-z_][a-z_-]*): (.+)", line)
        if not match:
            raise ValueError("unsupported metadata syntax: " + line)
        key, value = match.groups()
        if key in result:
            raise ValueError("duplicate metadata key: " + key)
        result[key] = scalar(value)
    return result


def frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("missing opening frontmatter delimiter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("missing closing frontmatter delimiter") from exc
    fields = mapping(lines[1:end])
    if set(fields) != {"name", "description"}:
        raise ValueError("repository profile requires exactly name and description")
    return fields


def ui_metadata(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0] != "interface:":
        raise ValueError("repository UI profile requires one interface mapping")
    fields = mapping(lines[1:], 2)
    if set(fields) != {"display_name", "short_description", "default_prompt"}:
        raise ValueError("repository UI profile requires display_name, short_description, default_prompt")
    if not all(value.strip() for value in fields.values()):
        raise ValueError("UI values must be non-empty")
    if not 25 <= len(fields["short_description"]) <= 64:
        raise ValueError("UI short_description must contain 25–64 characters")
    return fields


def anchors(text: str) -> set[str]:
    counts: dict[str, int] = {}
    found = set()
    in_fence = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        match = re.match(r"^#{1,6} (.+)$", line) if not in_fence else None
        if not match:
            continue
        slug = re.sub(r"[^\w\s-]", "", match.group(1).lower()).replace(" ", "-")
        count = counts.get(slug, 0)
        found.add(slug + ("-" + str(count) if count else ""))
        counts[slug] = count + 1
    return found


def references(path: Path, plugin: Path) -> list[str]:
    text = path.read_text()
    targets = re.findall(r"`(\.\./\.\./(?:references|assets)/[^`]+)`", text)
    targets += re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)
    checked = []
    for target in targets:
        if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target):
            continue
        filename, _, anchor = target.partition("#")
        destination = (path.parent / filename).resolve() if filename else path.resolve()
        try:
            destination.relative_to(plugin.resolve())
        except ValueError as exc:
            raise ValueError("reference escapes plugin: " + target) from exc
        if not destination.is_file():
            raise ValueError("missing reference: " + target)
        if anchor and anchor not in anchors(destination.read_text()):
            raise ValueError("missing heading anchor: " + target)
        checked.append(target)
    return checked


def validate(plugin: Path) -> dict:
    skills, errors = [], []
    for directory in sorted((plugin / "skills").iterdir()):
        if not directory.is_dir():
            continue
        try:
            text = (directory / "SKILL.md").read_text()
            fields = frontmatter(text)
            name = fields["name"]
            if name != directory.name or not NAME.fullmatch(name) or len(name) > 64:
                raise ValueError("invalid skill name or directory binding")
            description = fields["description"]
            if not 1 <= len(description) <= 1024 or re.search(r"[<>]", description):
                raise ValueError("invalid skill description")
            ui = ui_metadata((directory / "agents/openai.yaml").read_text())
            if "$" + name not in ui["default_prompt"]:
                raise ValueError("default_prompt must identify its skill")
            if "[TODO:" in text:
                raise ValueError("unresolved scaffold")
            links = references(directory / "SKILL.md", plugin)
            skills.append({"name": name, "description_characters": len(description),
                           "lines": len(text.splitlines()), "links_checked": len(links)})
        except (OSError, ValueError) as exc:
            errors.append(directory.name + ": " + str(exc))
    for path in sorted((plugin / "references").glob("*.md")):
        try:
            references(path, plugin)
        except (OSError, ValueError) as exc:
            errors.append(path.name + ": " + str(exc))
    if not skills:
        errors.append("no valid skills found")
    return {"profile": "strict repository scalar-mapping subset; not general YAML",
            "skills": skills, "errors": errors, "passed": not errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin", type=Path, default=PLUGIN)
    result = validate(parser.parse_args().plugin)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
