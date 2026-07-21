from scripts import manage_weekly_work_plan as weekly_plan


def test_patch_issue_omits_state_when_preserving_closed_issue(monkeypatch):
    calls = []

    def fake_run(command, *, check=True, input_text=None):
        calls.append((command, input_text))

    monkeypatch.setattr(weekly_plan, "run", fake_run)

    weekly_plan.patch_issue(
        "owner/repo",
        123,
        labels=["work-plan", "historical-week"],
        state=None,
        execute=True,
    )

    _, payload = calls[0]
    assert '"labels": ["work-plan", "historical-week"]' in payload
    assert '"state"' not in payload


def test_ensure_issue_does_not_reopen_closed_existing_issue(monkeypatch):
    patch_calls = []
    edit_calls = []

    existing = {
        "number": 42,
        "title": "Old title",
        "body": weekly_plan.managed_marker("ROLL-WEEK-01", 1, "week"),
        "state": "CLOSED",
        "labels": [{"name": "work-plan"}],
    }

    def fake_patch_issue(repo, number, *, labels, state=None, execute):
        patch_calls.append(
            {
                "repo": repo,
                "number": number,
                "labels": labels,
                "state": state,
                "execute": execute,
            }
        )

    def fake_ensure_parent(repo, issue_number, parent_number, *, execute):
        pass

    def fake_run(command, *, check=True, input_text=None):
        edit_calls.append((command, input_text))

    monkeypatch.setattr(weekly_plan, "patch_issue", fake_patch_issue)
    monkeypatch.setattr(weekly_plan, "ensure_parent", fake_ensure_parent)
    monkeypatch.setattr(weekly_plan, "run", fake_run)

    result = weekly_plan.ensure_issue(
        repo="owner/repo",
        managed={"ROLL-WEEK-01": existing},
        marker_id="ROLL-WEEK-01",
        week=1,
        issue_type="week",
        title="Week 1: Updated",
        body="Updated body",
        labels=["work-plan", "historical-week"],
        parent=None,
        assignee=None,
        execute=True,
        delay=0,
    )

    assert patch_calls[0]["state"] is None
    assert result["state"] == "CLOSED"
    assert edit_calls


def test_mark_earlier_weeks_historical_preserves_closed_state(monkeypatch):
    patch_calls = []

    def fake_patch_issue(repo, number, *, labels, state=None, execute):
        patch_calls.append(
            {
                "number": number,
                "labels": labels,
                "state": state,
            }
        )

    monkeypatch.setattr(weekly_plan, "patch_issue", fake_patch_issue)

    weekly_plan.mark_earlier_weeks_historical(
        repo="owner/repo",
        managed={
            "ROLL-WEEK-01": {
                "number": 1,
                "title": "Week 1",
                "body": weekly_plan.managed_marker("ROLL-WEEK-01", 1, "week"),
                "state": "CLOSED",
                "labels": [{"name": "current-week"}],
            }
        },
        current_week=2,
        execute=True,
    )

    assert patch_calls == [
        {
            "number": 1,
            "labels": ["historical-week"],
            "state": None,
        }
    ]
