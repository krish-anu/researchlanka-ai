# Rolling two-week GitHub work plan — keep tasks open

This workflow only controls **when issues become available**.

- During Week 1, it creates Week 1 and Week 2.
- During Week 2, it creates Week 3 while keeping Week 1 and Week 2 open.
- During Week 3, it creates Week 4 while every earlier issue remains open.
- It continues this way through Week 10.
- It never automatically closes or deletes a task.

Earlier issues receive the `historical-week` label, but their state remains open.
You can close a task manually when the work is actually completed.

## Issue structure

```text
Week
└── Person / Shared Work
    └── Individual task
```

## One-time setup

1. Delete the incorrect previous import.
2. Copy this package into the root of `krish-anu/researchlanka-ai`.
3. Commit and push:

```bash
git add .github scripts
git commit -m "Add rolling weekly task workflow"
git push
```

4. Open **GitHub → Actions → Rolling weekly work plan → Run workflow**.
5. Enter `1` for the first run.

The first run creates Week 1 and Week 2.

## Automatic schedule

The workflow runs every Monday at 00:15 in `Asia/Colombo`.

Example:

```text
Week 1:
  Creates Week 1 and Week 2

Week 2:
  Keeps Week 1 and Week 2 open
  Creates Week 3

Week 3:
  Keeps Weeks 1, 2 and 3 open
  Creates Week 4
```

The hidden IDs inside issue bodies prevent duplicate creation.

## Assignees

Edit `.github/work-plan/owners.json`.

`krish-anu` is already configured for Anusan. Add the GitHub usernames for
Asma Rauff and Gishan Bandara to assign their issues automatically.
