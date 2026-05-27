#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
IDEAL_PATH = ROOT / "docs" / "ideal.md"
SPEC_PATH = ROOT / "docs" / "spec.md"
STATE_PATH = ROOT / "docs" / "methodology" / "state.yaml"
GRAPH_PATH = ROOT / "docs" / "methodology" / "graph.json"
STORIES_DIR = ROOT / "docs" / "stories"
STORIES_INDEX_PATH = ROOT / "docs" / "stories.md"
EVALS_PATH = ROOT / "docs" / "evals" / "registry.yaml"
ADRS_DIR = ROOT / "docs" / "decisions"
SCOUT_INDEX_PATH = ROOT / "docs" / "scout.md"
SCOUT_DIR = ROOT / "docs" / "scout"

SPEC_CATEGORY_RE = re.compile(r"^##\s+(spec:\d+)\s+[—-]\s+(.+)$")
SPEC_SECTION_RE = re.compile(r"^###\s+(spec:\d+(?:\.\d+)*)\s+[—-]\s+(.+)$")
COMPROMISE_RE = re.compile(r"^\*\*((?:B|C|W)\d+):\s*([^*]+)\*\*")
STORY_FILE_RE = re.compile(r"^story-(\d{3})-[a-z0-9-]+\.md$")
SPEC_REF_RE = re.compile(r"\bspec:\d+(?:\.\d+)*\b")
COMPROMISE_REF_RE = re.compile(r"\b(?:B|C|W)\d+\b")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_json_file(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    text = read_text(path).strip()
    if not text:
        return fallback
    return json.loads(text)


def parse_ideal() -> dict[str, Any]:
    title = "Ideal"
    for line in read_text(IDEAL_PATH).splitlines():
        if line.startswith("# "):
            title = line.removeprefix("# ").strip()
            break
    return {"path": rel(IDEAL_PATH), "title": title}


def parse_spec() -> dict[str, Any]:
    categories: list[dict[str, Any]] = []
    compromises: list[dict[str, Any]] = []
    current_category: str | None = None
    for line in read_text(SPEC_PATH).splitlines():
        category = SPEC_CATEGORY_RE.match(line)
        if category:
            current_category = category.group(1)
            categories.append(
                {"id": current_category, "title": category.group(2).strip(), "sections": []}
            )
            continue
        section = SPEC_SECTION_RE.match(line)
        if section and current_category:
            categories[-1]["sections"].append(
                {"id": section.group(1), "title": section.group(2).strip()}
            )
            continue
        compromise = COMPROMISE_RE.match(line)
        if compromise and current_category:
            compromises.append(
                {
                    "id": compromise.group(1),
                    "title": compromise.group(2).strip(),
                    "category_id": current_category,
                }
            )
    return {"path": rel(SPEC_PATH), "categories": categories, "compromises": compromises}


def parse_json_frontmatter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError(f"Unterminated frontmatter in {rel(path)}")
    raw = text[4:end].strip()
    body = text[end + len("\n---\n") :]
    if not raw:
        return {}, body
    return json.loads(raw), body


def list_field(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        return [value] if value else []
    return []


def parse_story(path: Path) -> dict[str, Any]:
    match = STORY_FILE_RE.match(path.name)
    if not match:
        raise ValueError(f"Story filename is not canonical: {rel(path)}")
    text = read_text(path)
    frontmatter, body = parse_json_frontmatter(text, path)
    heading = next((line for line in body.splitlines() if line.startswith("# ")), path.stem)
    body_refs = " ".join(SPEC_REF_RE.findall(body))
    body_compromises = " ".join(COMPROMISE_REF_RE.findall(body))
    return {
        "id": match.group(1),
        "title": str(frontmatter.get("title") or heading.removeprefix("# ").strip()),
        "path": rel(path),
        "status": str(frontmatter.get("status") or "Draft"),
        "priority": str(frontmatter.get("priority") or "Medium"),
        "origin": str(frontmatter.get("origin") or ""),
        "ideal_refs": list_field(frontmatter.get("ideal_refs")),
        "spec_refs": sorted(set(list_field(frontmatter.get("spec_refs")) + SPEC_REF_RE.findall(body_refs))),
        "depends_on": list_field(frontmatter.get("depends_on")),
        "category_refs": sorted(set(list_field(frontmatter.get("category_refs")))),
        "compromise_refs": sorted(
            set(list_field(frontmatter.get("compromise_refs")) + COMPROMISE_REF_RE.findall(body_compromises))
        ),
    }


def parse_stories() -> list[dict[str, Any]]:
    if not STORIES_DIR.exists():
        return []
    return [parse_story(path) for path in sorted(STORIES_DIR.glob("story-*.md"))]


def parse_evals() -> list[dict[str, Any]]:
    payload = read_json_file(EVALS_PATH, [])
    if isinstance(payload, dict):
        payload = payload.get("evals", [])
    return payload if isinstance(payload, list) else []


def parse_adrs() -> list[dict[str, Any]]:
    if not ADRS_DIR.exists():
        return []
    records: list[dict[str, Any]] = []
    paths = sorted(ADRS_DIR.glob("adr-*.md")) + sorted(ADRS_DIR.glob("adr-*/adr.md"))
    for path in paths:
        text = read_text(path)
        heading = next((line for line in text.splitlines() if line.startswith("# ")), path.stem)
        adr_match = re.search(r"ADR-(\d{3})", heading) or re.search(r"adr-(\d{3})", path.as_posix())
        if not adr_match:
            continue
        status_match = re.search(r"^## Status\s*\n+([^\n]+)", text, re.MULTILINE)
        title = re.sub(r"^#\s*ADR-\d{3}\s*[-—:]\s*", "", heading).strip()
        records.append(
            {
                "id": f"ADR-{adr_match.group(1)}",
                "title": title,
                "path": rel(path),
                "status": status_match.group(1).strip() if status_match else "Unknown",
                "spec_refs": sorted(set(SPEC_REF_RE.findall(text))),
                "compromise_refs": sorted(set(COMPROMISE_REF_RE.findall(text))),
            }
        )
    return records


def parse_scouts() -> list[dict[str, Any]]:
    if not SCOUT_DIR.exists():
        return []
    records = []
    for path in sorted(SCOUT_DIR.glob("scout-*.md")):
        match = re.match(r"scout-(\d{3})-(.+)\.md$", path.name)
        if not match:
            continue
        text = read_text(path)
        heading = next((line for line in text.splitlines() if line.startswith("# ")), path.stem)
        status_match = re.search(r"^\*\*Status:\*\*\s*(.+)$", text, re.MULTILINE)
        records.append(
            {
                "id": match.group(1),
                "title": re.sub(r"^#\s*Scout\s+\d{3}\s*[-—:]\s*", "", heading).strip(),
                "path": rel(path),
                "status": status_match.group(1).strip() if status_match else "Unknown",
                "spec_refs": sorted(set(SPEC_REF_RE.findall(text))),
            }
        )
    return records


def build_graph() -> dict[str, Any]:
    state = read_json_file(STATE_PATH, {})
    spec = parse_spec()
    stories = parse_stories()
    evals = parse_evals()
    adrs = parse_adrs()
    scouts = parse_scouts()
    category_ids = {entry["id"] for entry in spec["categories"]}
    compromise_category = {entry["id"]: entry["category_id"] for entry in spec["compromises"]}

    for story in stories:
        refs = set(story["category_refs"])
        for spec_ref in story["spec_refs"]:
            refs.add(spec_ref.split(".")[0])
        for compromise in story["compromise_refs"]:
            category = compromise_category.get(compromise)
            if category:
                refs.add(category)
        story["category_refs"] = sorted(ref for ref in refs if ref in category_ids)

    categories = []
    for category in spec["categories"]:
        category_id = category["id"]
        categories.append(
            {
                **category,
                "state": state.get("categories", {}).get(category_id),
                "story_ids": [
                    story["id"] for story in stories if category_id in story["category_refs"]
                ],
                "eval_ids": [
                    entry.get("id") for entry in evals if category_id in entry.get("category_refs", [])
                ],
            }
        )

    compromises = []
    for compromise in spec["compromises"]:
        compromise_id = compromise["id"]
        compromises.append(
            {
                **compromise,
                "state": state.get("compromises", {}).get(compromise_id),
                "story_ids": [
                    story["id"] for story in stories if compromise_id in story["compromise_refs"]
                ],
            }
        )

    graph = {
        "version": 1,
        "paths": {
            "ideal": rel(IDEAL_PATH),
            "spec": rel(SPEC_PATH),
            "state": rel(STATE_PATH),
            "graph": rel(GRAPH_PATH),
            "stories_dir": rel(STORIES_DIR),
            "stories_index": rel(STORIES_INDEX_PATH),
            "evals": rel(EVALS_PATH),
            "adrs_dir": rel(ADRS_DIR),
            "scout_index": rel(SCOUT_INDEX_PATH),
            "scout_dir": rel(SCOUT_DIR),
        },
        "ideal": parse_ideal(),
        "spec": {
            "path": rel(SPEC_PATH),
            "categories": categories,
            "compromises": compromises,
        },
        "state": state,
        "stories": stories,
        "adrs": adrs,
        "scouts": scouts,
        "evals": evals,
    }
    graph["validation"] = validate_graph(graph)
    return graph


def validate_graph(graph: dict[str, Any]) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    categories = graph["spec"]["categories"]
    compromises = graph["spec"]["compromises"]
    category_ids = {entry["id"] for entry in categories}
    section_ids = {section["id"] for entry in categories for section in entry["sections"]}
    compromise_ids = {entry["id"] for entry in compromises}

    if not category_ids:
        errors.append("docs/spec.md has no spec:N categories")

    for category_id in graph["state"].get("categories", {}):
        if category_id not in category_ids:
            errors.append(f"state category {category_id} is not in docs/spec.md")
    for compromise_id in graph["state"].get("compromises", {}):
        if compromise_id not in compromise_ids:
            errors.append(f"state compromise {compromise_id} is not in docs/spec.md")

    for story in graph["stories"]:
        for spec_ref in story["spec_refs"]:
            if spec_ref not in category_ids and spec_ref not in section_ids:
                errors.append(f"story {story['id']} references missing {spec_ref}")
        for compromise in story["compromise_refs"]:
            if compromise not in compromise_ids:
                errors.append(f"story {story['id']} references missing {compromise}")
        if story["status"] not in {"Draft", "Pending", "In Progress", "Blocked", "Done"}:
            warnings.append(f"story {story['id']} has non-standard status {story['status']}")

    for entry in graph["evals"]:
        for spec_ref in entry.get("spec_refs", []):
            if spec_ref not in category_ids and spec_ref not in section_ids:
                errors.append(f"eval {entry.get('id')} references missing {spec_ref}")

    for adr in graph.get("adrs", []):
        for spec_ref in adr.get("spec_refs", []):
            if spec_ref not in category_ids and spec_ref not in section_ids:
                errors.append(f"{adr['id']} references missing {spec_ref}")
        for compromise in adr.get("compromise_refs", []):
            if compromise not in compromise_ids:
                errors.append(f"{adr['id']} references missing {compromise}")

    for scout in graph.get("scouts", []):
        for spec_ref in scout.get("spec_refs", []):
            if spec_ref not in category_ids and spec_ref not in section_ids:
                errors.append(f"scout {scout['id']} references missing {spec_ref}")

    return {"errors": errors, "warnings": warnings}


def render_stories_index(graph: dict[str, Any]) -> str:
    lines = [
        "# Stories",
        "",
        "> Generated from story metadata and `docs/methodology/state.yaml`. Do not edit manually.",
        "",
        "## Status Key",
        "- **Draft** — Worth preserving but not yet build-ready",
        "- **Pending** — Buildable now with known proof requirements",
        "- **In Progress** — Currently being built",
        "- **Blocked** — Waiting on a named blocker",
        "- **Done** — Built, validated, and closed",
        "",
        "## Index",
        "",
        "| ID | Title | Priority | Status | Depends On | Link |",
        "|---|---|---|---|---|---|",
    ]
    for story in sorted(graph["stories"], key=lambda item: int(item["id"])):
        depends_on = ", ".join(story["depends_on"]) if story["depends_on"] else "-"
        title = story["title"].replace("|", "\\|")
        link = story["path"].replace("docs/", "")
        lines.append(
            f"| {story['id']} | {title} | {story['priority']} | {story['status']} | "
            f"{depends_on} | [story]({link}) |"
        )
    return "\n".join(lines).rstrip() + "\n"


def run(command: str) -> int:
    graph = build_graph()
    if graph["validation"]["errors"]:
        print("Methodology graph validation failed:", file=sys.stderr)
        for error in graph["validation"]["errors"]:
            print(f"- {error}", file=sys.stderr)
        return 1
    for warning in graph["validation"]["warnings"]:
        print(f"warning: {warning}", file=sys.stderr)

    serialized = json.dumps(graph, indent=2) + "\n"
    stories_index = render_stories_index(graph)
    if command == "print":
        print(serialized, end="")
        return 0
    if command == "check":
        if not GRAPH_PATH.exists() or read_text(GRAPH_PATH) != serialized:
            print("docs/methodology/graph.json is out of date. Run make methodology-compile.", file=sys.stderr)
            return 1
        if not STORIES_INDEX_PATH.exists() or read_text(STORIES_INDEX_PATH) != stories_index:
            print("docs/stories.md is out of date. Run make methodology-compile.", file=sys.stderr)
            return 1
        print("Methodology graph is current: docs/methodology/graph.json")
        return 0
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_PATH.write_text(serialized, encoding="utf-8")
    STORIES_INDEX_PATH.write_text(stories_index, encoding="utf-8")
    print("Wrote docs/methodology/graph.json")
    print("Wrote docs/stories.md")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["build", "check", "print"], nargs="?", default="build")
    return run(parser.parse_args().command)


if __name__ == "__main__":
    raise SystemExit(main())
