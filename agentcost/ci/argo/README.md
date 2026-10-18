# Argo Workflows

| File | What it is |
|---|---|
| [workflows/agentcost.yaml](workflows/agentcost.yaml) | The agentcost check as an in-repo Argo `Workflow`. Copy it to `.argo/agentcost.yaml` in your agent repo. |

## Use it

1. Copy [workflows/agentcost.yaml](workflows/agentcost.yaml) into your agent repo as `.argo/agentcost.yaml`.
2. Create the `agentcost` Secret in the namespace where your CI workflows run:

   ```bash
   kubectl -n <ci-namespace> create secret generic agentcost \
     --from-literal=anthropic-api-key=sk-ant-... \
     --from-literal=github-token=ghp_...        # optional: contents read, pull requests write
   ```

3. Set `install-command` in the file to however your agent installs (default `pip install -e .`).
4. Map your Argo CI's PR context onto the workflow's parameters:

| Parameter | Value | Required |
|---|---|---|
| `revision` | PR head commit SHA, **not** a merge commit | yes |
| `repo-url` | https clone URL | yes |
| `pr-number` | PR number, to post the sticky comment | no |
| `github-repo` | `owner/name`, needed with `pr-number` | no |

Try it by hand before wiring it to PRs:

```bash
argo submit --watch .argo/agentcost.yaml \
  -p repo-url=https://github.com/my-org/my-agent.git \
  -p revision=$(git rev-parse HEAD)
```

## How a check runs

```text
check    init container   git clone (full history), checkout PR head      GitHub token; no repo code runs
         main container   install-command, pip install ezop-agentcost,    provider keys only; NO GitHub token
                          ezop-agentcost compare (merge base vs. head)
comment  upsert the sticky PR comment from check's output                 GitHub token; no repo code runs
gate     exit 0 ok/inconclusive · 1 regression (workflow fails) · 2 error
```

`compare` finds the merge base with `origin/<ci.main_branch>` itself, checks it out next to the PR head, and runs
both sides interleaved behind the recording proxy. Unlike the GitHub Action, there are no cached baselines from
`main`, so **both sides run every time**: budget about twice the cost of a head-only run, and keep
`spend_cap_usd` set in `agentcost.yml`.

Outputs: the workflow succeeds or fails with the verdict, the `verdict` output parameter holds `regression`,
`inconclusive`, `ok`, or `error`, and with an artifact repository configured, `.agentcost/` (`comment.md`,
`diff.json`, `base.json`, `head.json`) is saved as `agentcost-report`.

## Security

A PR's code (its `install-command` and the agent itself) runs during the check, next to your provider keys.

- **Run it only for trusted PRs**: branches in this repo, opened by owners, members, or collaborators. Never
  for forks. If your Argo CI runs `.argo/` workflows for every PR by default, add that condition there.
- **The GitHub token never reaches PR code.** Cloning happens in an init container that runs only git, with the
  token passed per command so it isn't saved in `.git/config`. The comment is posted by a separate pod that never
  runs repo code.
- **Provider keys are exposed to PR code by necessity**, since the agent calls the model. Use dedicated CI keys
  with low spend limits.
- **No production write credentials.** agentcost runs your real tools; mount sandbox or read-only credentials only.

## Adapting it

- **Tools that need services** (Postgres, Redis): add them as `sidecars` on the `check` template and point the
  agent at `localhost`.
- **A prebuilt agent image**: swap the `check` container's `image` for yours (it needs `git` and Python 3.10+) and
  set `install-command` to `true`.
- **Your runner already checks the repo out**: you can drop the init container and point `workingDir` at that
  checkout, as long as it has full history and the PR head checked out.
- **Non-GitHub hosting**: leave `pr-number` empty; the check still gates, and `comment.md` is in the artifact.
