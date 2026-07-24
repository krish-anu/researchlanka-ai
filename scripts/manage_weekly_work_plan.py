#!/usr/bin/env python3
"""
Maintain a rolling two-week GitHub issue hierarchy:

Current week
  └── Person / Shared Work
        └── Individual task

Next week
  └── Person / Shared Work
        └── Individual task

The script is idempotent. Each managed issue has a unique hidden marker, so
re-running it updates existing items instead of creating duplicates. Issues
that were manually closed stay closed.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / ".github" / "work-plan"


def run(
    command: list[str],
    *,
    check: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        text=True,
        input=input_text,
        capture_output=True,
    )
    if check and result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"Command failed ({result.returncode}):\n"
            f"{' '.join(command)}\n\n{details}"
        )
    return result


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_tasks(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    required = {"task_id", "week", "period", "theme", "owner", "title"}
    if not rows:
        raise ValueError(f"No tasks found in {path}")

    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"Missing CSV columns: {', '.join(sorted(missing))}")

    return rows


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def managed_marker(marker_id: str, week: int, issue_type: str) -> str:
    return (
        f"<!-- rolling-work-plan: id={marker_id}; "
        f"week={week}; type={issue_type} -->"
    )


MARKER_RE = re.compile(
    r"<!-- rolling-work-plan:\s*"
    r"id=(?P<id>[^;]+);\s*"
    r"week=(?P<week>\d+);\s*"
    r"type=(?P<type>week|group|task)\s*-->"
)


def parse_marker(body: str | None) -> dict[str, Any] | None:
    match = MARKER_RE.search(body or "")
    if not match:
        return None
    return {
        "id": match.group("id").strip(),
        "week": int(match.group("week")),
        "type": match.group("type"),
    }


def current_project_week(
    *,
    start: date,
    timezone_name: str,
    override: int | None,
) -> int:
    if override is not None:
        return override

    today = datetime.now(ZoneInfo(timezone_name)).date()
    delta_days = (today - start).days

    if delta_days < 0:
        return 1

    return (delta_days // 7) + 1


def group_tasks(
    rows: list[dict[str, str]],
) -> dict[int, dict[str, list[dict[str, str]]]]:
    grouped: dict[int, dict[str, list[dict[str, str]]]] = {}

    for row in rows:
        week = int(row["week"])
        grouped.setdefault(week, {}).setdefault(row["owner"], []).append(row)

    return dict(sorted(grouped.items()))


def gh_json(command: list[str]) -> Any:
    result = run(command)
    return json.loads(result.stdout or "[]")


def fetch_managed_issues(repo: str) -> tuple[
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
]:
    issues = gh_json(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "all",
            "--label",
            "work-plan",
            "--limit",
            "1000",
            "--json",
            "number,title,body,state,labels,url",
        ]
    )

    managed: dict[str, dict[str, Any]] = {}
    old_imports: list[dict[str, Any]] = []

    for issue in issues:
        marker = parse_marker(issue.get("body"))
        if marker:
            issue["_marker"] = marker
            managed[marker["id"]] = issue
        elif "<!-- work-plan-id:" in (issue.get("body") or ""):
            old_imports.append(issue)

    return managed, old_imports


def ensure_label(
    repo: str,
    name: str,
    color: str,
    description: str,
    *,
    execute: bool,
) -> None:
    if not execute:
        return

    run(
        [
            "gh",
            "label",
            "create",
            name,
            "--repo",
            repo,
            "--color",
            color,
            "--description",
            description[:100],
            "--force",
        ]
    )


def ensure_labels(
    repo: str,
    grouped: dict[int, dict[str, list[dict[str, str]]]],
    *,
    execute: bool,
) -> None:
    labels: dict[str, tuple[str, str]] = {
        "work-plan": ("1D76DB", "Managed by the rolling weekly work-plan workflow"),
        "weekly-plan": ("5319E7", "Top-level week issue"),
        "person-plan": ("8250DF", "Person or shared-work group"),
        "individual-task": ("C5DEF5", "Individual task"),
        "current-week": ("0E8A16", "Work for the current project week"),
        "next-week": ("FBCA04", "Work planned for the next project week"),
        "historical-week": ("D4C5F9", "Work from an earlier project week"),
        "shared-work": ("1D76DB", "Shared team task"),
        "evaluation-tasks": ("B60205", "Evaluation work"),
    }

    for week in grouped:
        labels[f"week-{week:02d}"] = (
            "BFDADC",
            f"Project work scheduled for week {week}",
        )

    owners = {
        owner
        for owner_groups in grouped.values()
        for owner in owner_groups
    }
    for owner in sorted(owners):
        labels[f"owner-{slug(owner)}"] = (
            "C2E0C6",
            f"Work assigned to {owner}",
        )

    for name, (color, description) in labels.items():
        ensure_label(repo, name, color, description, execute=execute)


def label_names(issue: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for item in issue.get("labels") or []:
        if isinstance(item, dict):
            name = item.get("name")
        else:
            name = str(item)
        if name:
            names.add(str(name))
    return names


def issue_is_closed(issue: dict[str, Any]) -> bool:
    return str(issue.get("state") or "").lower() == "closed"


def patch_issue(
    repo: str,
    number: int,
    *,
    labels: list[str],
    state: str | None = None,
    execute: bool,
) -> None:
    if not execute:
        return

    payload: dict[str, Any] = {
        "labels": labels,
    }
    if state is not None:
        payload["state"] = state
    if state == "closed":
        payload["state_reason"] = "completed"

    run(
        [
            "gh",
            "api",
            "--method",
            "PATCH",
            f"repos/{repo}/issues/{number}",
            "--input",
            "-",
        ],
        input_text=json.dumps(payload),
    )


def ensure_parent(
    repo: str,
    issue_number: int,
    parent_number: int | None,
    *,
    execute: bool,
) -> None:
    if not execute or parent_number is None:
        return

    result = run(
        [
            "gh",
            "issue",
            "edit",
            str(issue_number),
            "--repo",
            repo,
            "--parent",
            str(parent_number),
        ],
        check=False,
    )

    if result.returncode == 0:
        return

    details = "\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part and part.strip()
    )

    # Reruns are idempotent: GitHub returns an error when the issue is
    # already attached to this parent. That relationship is already correct.
    duplicate_messages = (
        "duplicate sub-issues",
        "may not contain duplicate sub-issues",
        "already a sub-issue",
    )
    if any(message in details.lower() for message in duplicate_messages):
        print(
            f"PARENT ALREADY SET: issue #{issue_number} "
            f"is already under #{parent_number}"
        )
        return

    raise RuntimeError(
        "Failed to set parent relationship:\n"
        f"issue #{issue_number} -> parent #{parent_number}\n\n{details}"
    )


def create_issue(
    *,
    repo: str,
    title: str,
    body: str,
    labels: list[str],
    parent: int | None,
    assignee: str | None,
    execute: bool,
) -> dict[str, Any]:
    if not execute:
        return {
            "number": -1,
            "title": title,
            "body": body,
            "state": "OPEN",
            "labels": [{"name": name} for name in labels],
            "url": "(preview)",
        }

    command = [
        "gh",
        "issue",
        "create",
        "--repo",
        repo,
        "--title",
        title,
        "--body-file",
        "-",
    ]

    for label in labels:
        command.extend(["--label", label])

    if parent is not None:
        command.extend(["--parent", str(parent)])

    if assignee:
        command.extend(["--assignee", assignee])

    result = run(command, input_text=body)
    url = result.stdout.strip()
    number_match = re.search(r"/issues/(\d+)\s*$", url)

    if not number_match:
        raise RuntimeError(f"Could not determine issue number from: {url}")

    return {
        "number": int(number_match.group(1)),
        "title": title,
        "body": body,
        "state": "OPEN",
        "labels": [{"name": name} for name in labels],
        "url": url,
    }


def ensure_issue(
    *,
    repo: str,
    managed: dict[str, dict[str, Any]],
    marker_id: str,
    week: int,
    issue_type: str,
    title: str,
    body: str,
    labels: list[str],
    parent: int | None,
    assignee: str | None,
    execute: bool,
    delay: float,
) -> dict[str, Any]:
    existing = managed.get(marker_id)

    if existing:
        is_closed = issue_is_closed(existing)
        action = "SYNC CLOSED" if is_closed else "UPDATE"
        print(f"{action} #{existing['number']}: {title}")
        patch_issue(
            repo,
            int(existing["number"]),
            labels=labels,
            state=None if is_closed else "open",
            execute=execute,
        )
        ensure_parent(
            repo,
            int(existing["number"]),
            parent,
            execute=execute,
        )
        if execute:
            # Keep title/body synchronized with the source data.
            edit_command = [
                "gh",
                "issue",
                "edit",
                str(existing["number"]),
                "--repo",
                repo,
                "--title",
                title,
                "--body-file",
                "-",
            ]
            # Apply the configured owner to issues that already exist.
            # GitHub treats adding an already assigned user as idempotent.
            if assignee:
                edit_command.extend(["--add-assignee", assignee])

            run(edit_command, input_text=body)
        existing.update(
            {
                "title": title,
                "body": body,
                "state": "CLOSED" if is_closed else "OPEN",
                "labels": [{"name": name} for name in labels],
            }
        )
        return existing

    print(f"CREATE: {title}")
    created = create_issue(
        repo=repo,
        title=title,
        body=body,
        labels=labels,
        parent=parent,
        assignee=assignee,
        execute=execute,
    )
    managed[marker_id] = created

    if execute:
        time.sleep(max(delay, 0))

    return created


def status_label(week: int, current_week: int) -> str:
    if week == current_week:
        return "current-week"
    if week == current_week + 1:
        return "next-week"
    return "historical-week"


def week_body(
    *,
    week: int,
    period: str,
    theme: str,
    owners: dict[str, list[dict[str, str]]],
    outputs: list[str],
) -> str:
    parts = [
        f"# {theme}",
        "",
        f"**Project week:** {week}",
        f"**Period:** {period}",
        "",
        "## Work groups",
        "",
    ]

    for owner, tasks in owners.items():
        parts.append(f"- **{owner}:** {len(tasks)} tasks")

    if outputs:
        parts.extend(["", "## Expected outputs", ""])
        parts.extend(f"- [ ] {output}" for output in outputs)

    parts.extend(
        [
            "",
            "---",
            "Managed automatically by the rolling two-week workflow.",
            managed_marker(f"ROLL-WEEK-{week:02d}", week, "week"),
        ]
    )
    return "\n".join(parts)


def group_body(
    *,
    week: int,
    period: str,
    theme: str,
    owner: str,
    task_count: int,
) -> str:
    return "\n".join(
        [
            f"# {owner} — Week {week}",
            "",
            f"**Period:** {period}",
            f"**Workstream:** {theme}",
            f"**Individual tasks:** {task_count}",
            "",
            "The work items below are individual task sub-issues.",
            "",
            managed_marker(
                f"ROLL-W{week:02d}-GROUP-{slug(owner).upper()}",
                week,
                "group",
            ),
        ]
    )


def task_body(row: dict[str, str]) -> str:
    week = int(row["week"])
    return "\n".join(
        [
            f"**Owner/group:** {row['owner']}",
            f"**Week:** {row['week']} — {row['period']}",
            f"**Workstream:** {row['theme']}",
            "",
            "## Task",
            row["title"],
            "",
            managed_marker(f"ROLL-{row['task_id']}", week, "task"),
        ]
    )


def mark_earlier_weeks_historical(
    *,
    repo: str,
    managed: dict[str, dict[str, Any]],
    current_week: int,
    execute: bool,
) -> None:
    """Mark earlier managed issues historical without reopening closed items."""
    for issue in managed.values():
        marker = issue.get("_marker") or parse_marker(issue.get("body"))
        if not marker or marker["week"] >= current_week:
            continue

        labels = label_names(issue)
        labels.discard("current-week")
        labels.discard("next-week")
        labels.add("historical-week")

        is_closed = issue_is_closed(issue)
        action = "MARK HISTORICAL CLOSED" if is_closed else "KEEP OPEN / MARK HISTORICAL"
        print(f"{action} #{issue['number']}: {issue['title']}")
        patch_issue(
            repo,
            int(issue["number"]),
            labels=sorted(labels),
            state=None if is_closed else "open",
            execute=execute,
        )

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Maintain current-week and next-week GitHub issue hierarchies."
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY"),
        help="Repository in OWNER/REPO format.",
    )
    parser.add_argument(
        "--week",
        type=int,
        help="Override the automatically calculated current project week.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply GitHub changes. Without this flag, only preview actions.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between issue creations to reduce secondary rate limiting.",
    )
    args = parser.parse_args()

    config = load_json(DATA_DIR / "config.json")
    rows = load_tasks(DATA_DIR / "tasks.csv")
    weeks_list = load_json(DATA_DIR / "weeks.json")
    owners = load_json(DATA_DIR / "owners.json")

    repo = args.repo or str(config["repository"])
    timezone_name = str(config.get("timezone", "UTC"))
    start = date.fromisoformat(str(config["project_start"]))

    grouped = group_tasks(rows)
    week_metadata = {int(item["week"]): item for item in weeks_list}
    total_weeks = max(grouped)

    current_week = current_project_week(
        start=start,
        timezone_name=timezone_name,
        override=args.week,
    )

    if current_week < 1:
        current_week = 1

    target_weeks = [
        week
        for week in (current_week, current_week + 1)
        if 1 <= week <= total_weeks
    ]

    print(f"Repository: {repo}")
    print(f"Project start: {start}")
    print(f"Timezone: {timezone_name}")
    print(f"Current project week: {current_week}")
    print(f"Target open weeks: {target_weeks}")
    print("Earlier weeks: remain open and are marked historical")
    print(f"Execute: {args.execute}")

    if args.execute:
        run(["gh", "auth", "status"])

    ensure_labels(repo, grouped, execute=args.execute)
    managed, old_imports = fetch_managed_issues(repo) if args.execute else ({}, [])

    if old_imports:
        issue_numbers = ", ".join(f"#{item['number']}" for item in old_imports[:10])
        more = "" if len(old_imports) <= 10 else f" and {len(old_imports) - 10} more"
        raise RuntimeError(
            "Older bulk-import issues still exist "
            f"({issue_numbers}{more}). Delete the previous import first, then rerun."
        )

    if current_week > total_weeks:
        print("The project period has ended.")
        mark_earlier_weeks_historical(
            repo=repo,
            managed=managed,
            current_week=current_week,
            execute=args.execute,
        )
        return 0

    for week in target_weeks:
        owner_groups = grouped[week]
        first_task = next(iter(next(iter(owner_groups.values()))))
        meta = week_metadata.get(week, {})
        period = str(meta.get("period") or first_task["period"])
        theme = str(meta.get("theme") or first_task["theme"])
        outputs = list(meta.get("expected_outputs") or [])
        availability = status_label(week, current_week)
        week_label = f"week-{week:02d}"

        week_marker_id = f"ROLL-WEEK-{week:02d}"
        week_issue = ensure_issue(
            repo=repo,
            managed=managed,
            marker_id=week_marker_id,
            week=week,
            issue_type="week",
            title=f"Week {week}: {theme}",
            body=week_body(
                week=week,
                period=period,
                theme=theme,
                owners=owner_groups,
                outputs=outputs,
            ),
            labels=[
                "work-plan",
                "weekly-plan",
                week_label,
                availability,
            ],
            parent=None,
            assignee=None,
            execute=args.execute,
            delay=args.delay,
        )

        week_number = int(week_issue["number"])

        for owner, owner_tasks in owner_groups.items():
            owner_label = f"owner-{slug(owner)}"
            group_labels = [
                "work-plan",
                "person-plan",
                week_label,
                owner_label,
                availability,
            ]
            if owner == "Shared Work":
                group_labels.append("shared-work")
            if owner == "Evaluation Tasks":
                group_labels.append("evaluation-tasks")

            group_marker_id = f"ROLL-W{week:02d}-GROUP-{slug(owner).upper()}"
            assignee = str(owners.get(owner, "")).strip() or None

            group_issue = ensure_issue(
                repo=repo,
                managed=managed,
                marker_id=group_marker_id,
                week=week,
                issue_type="group",
                title=f"[W{week}] {owner} tasks",
                body=group_body(
                    week=week,
                    period=period,
                    theme=theme,
                    owner=owner,
                    task_count=len(owner_tasks),
                ),
                labels=group_labels,
                parent=week_number,
                assignee=assignee,
                execute=args.execute,
                delay=args.delay,
            )

            group_number = int(group_issue["number"])

            for row in owner_tasks:
                task_labels = [
                    "work-plan",
                    "individual-task",
                    week_label,
                    owner_label,
                    availability,
                ]
                if owner == "Shared Work":
                    task_labels.append("shared-work")
                if owner == "Evaluation Tasks":
                    task_labels.append("evaluation-tasks")

                ensure_issue(
                    repo=repo,
                    managed=managed,
                    marker_id=f"ROLL-{row['task_id']}",
                    week=week,
                    issue_type="task",
                    title=f"[W{week}] {row['title']}",
                    body=task_body(row),
                    labels=task_labels,
                    parent=group_number,
                    assignee=assignee,
                    execute=args.execute,
                    delay=args.delay,
                )

    mark_earlier_weeks_historical(
        repo=repo,
        managed=managed,
        current_week=current_week,
        execute=args.execute,
    )

    print("\nRolling two-week work plan is up to date.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped by user.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
