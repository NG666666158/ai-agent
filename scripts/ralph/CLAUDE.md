# Orion Agent Ralph Runner Instructions

You are an autonomous coding agent working on the `Orion Agent` project.

## Your Task

1. Read the PRD at `scripts/ralph/prd.json`
2. Read the progress log at `scripts/ralph/progress.txt` and check `## Codebase Patterns` first
3. Check that the current git branch matches `branchName` in `scripts/ralph/prd.json`
4. Pick the highest priority user story where `passes: false`
5. Implement only that single story
6. Run the relevant quality checks for this project
7. If you discover reusable project knowledge, append it to `scripts/ralph/progress.txt`
8. If checks pass, commit all changes with message: `feat: [Story ID] - [Story Title]`
9. Update `scripts/ralph/prd.json` to set the completed story `passes: true`
10. If all stories are complete, reply with `<promise>COMPLETE</promise>`

## Project Context

- Backend: `src/orion_agent/`
- Frontend: `frontend/src/`
- Backend tests: `tests/`
- Product planning docs: `docs/` and `tasks/`

## Quality Checks

Choose the smallest checks that match the story scope, but do not skip verification.

### For backend / model / API stories

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.unit.test_execution_nodes
```

If you touch additional backend execution code, expand to the relevant unittest modules.

### For frontend stories

```powershell
cd frontend
cmd /c npm run build
```

### For mixed stories

Run both backend and frontend checks that match the files changed.

## Important Project Conventions

- Prefer updating the unified `execution_nodes` flow for primary execution visualization.
- Keep `progress_updates`, `tool_invocations`, and other legacy fields compatible, but do not make them the primary UI path for new work.
- Use concise Chinese text for user-facing labels in the frontend.
- Use `apply_patch`-style focused changes rather than broad rewrites unless cleanup is necessary.
- Do not revert unrelated user changes in the working tree.

## Progress Report Format

Append to `scripts/ralph/progress.txt`:

```text
## [Date/Time] - [Story ID]
- What was implemented
- Files changed
- Quality checks run
- Learnings for future iterations
---
```

## Stop Condition

If all user stories in `scripts/ralph/prd.json` have `passes: true`, output:

```xml
<promise>COMPLETE</promise>
```
