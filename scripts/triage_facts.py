#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def read_json(relative: str, fallback: Any) -> Any:
    path = ROOT / relative
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def git(args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        encoding="utf-8",
        timeout=5,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def facts() -> dict[str, Any]:
    graph = read_json("docs/methodology/graph.json", {})
    status = git(["status", "--short"])
    skills = sorted(
        path.parent.name for path in (ROOT / ".agents" / "skills").glob("*/SKILL.md")
    )
    return {
        "repo": "rpg-map-projector",
        "git": {
            "branch": git(["branch", "--show-current"]),
            "head": git(["rev-parse", "--short", "HEAD"]),
            "dirty": bool(status),
            "status_short": status.splitlines()[:40],
        },
        "methodology": {
            "categories": len((graph.get("spec") or {}).get("categories") or []),
            "stories": len(graph.get("stories") or []),
            "adrs": len(graph.get("adrs") or []),
            "scouts": len(graph.get("scouts") or []),
            "evals": len(graph.get("evals") or []),
            "validation": graph.get("validation"),
        },
        "lanes": {
            "runtime_launcher": "present",
            "ui_scout": "deferred",
            "eval_golden": "deferred",
            "codebase_improvement": "absent",
            "remote_server": "post-mvp",
            "scout": "present",
            "adr": "present",
        },
        "skills": {
            "count": len(skills),
            "names": skills,
        },
    }


def print_text(payload: dict[str, Any]) -> None:
    print("rpg-map-projector triage facts")
    print(f"- branch: {payload['git']['branch']}")
    print(f"- dirty: {payload['git']['dirty']}")
    print(f"- categories: {payload['methodology']['categories']}")
    print(f"- stories: {payload['methodology']['stories']}")
    print(f"- ADRs: {payload['methodology']['adrs']}")
    print(f"- scouts: {payload['methodology']['scouts']}")
    print(f"- evals: {payload['methodology']['evals']} (deferred)")
    print(f"- remote server: {payload['lanes']['remote_server']}")
    print(f"- skills: {payload['skills']['count']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = facts()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_text(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
