# GitHub Actions

| File | What it is |
|---|---|
| [action.yml](action.yml) | The composite action: installs agentcost, runs `ezop-agentcost ci`, uploads reports and baselines, and sets the check status |
| [workflows/agentcost.yml](workflows/agentcost.yml) | Example workflow: baseline on pushes to `main`, a sticky comment on every PR. `ezop-agentcost init` writes the same file. |

## Use it

Copy [workflows/agentcost.yml](workflows/agentcost.yml) into your agent repo's `.github/workflows/`. Add
`ANTHROPIC_API_KEY` (and/or `OPENAI_API_KEY`) as a repository secret, then push. The workflow references the action
by path:

```yaml
- uses: ezop-ai/ezop/agentcost/ci/github@main
```

Pin a tag or commit SHA instead of `main` once releases exist.

Inputs, outputs, how baselines flow, controlling spend, and fork PRs are covered in
[docs/github-action.md](../../docs/github-action.md).
