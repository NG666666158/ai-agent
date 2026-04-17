# Orion Agent Ralph Runner Instructions

You are an autonomous coding agent working on the `Orion Agent` project.

Read:

1. `scripts/ralph/prd.json`
2. `scripts/ralph/progress.txt`

Then:

1. Check out the branch from `branchName`
2. Pick the highest priority story where `passes: false`
3. Implement only that story
4. Run the smallest relevant quality checks
5. Update `scripts/ralph/prd.json` to mark the story complete
6. Append progress to `scripts/ralph/progress.txt`
7. Commit with `feat: [Story ID] - [Story Title]`

Quality checks:

- Backend: `$env:PYTHONPATH='src'; python -m unittest tests.unit.test_execution_nodes`
- Frontend: `cd frontend && cmd /c npm run build`

If all stories are complete, output:

```xml
<promise>COMPLETE</promise>
```
