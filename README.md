# Plane MCP Skill

A reusable Agent Skill that calls the official Plane MCP server **on demand**.
It does not register tools with the host: only the skill name and description
need to be visible until a Plane task is requested.

Unofficial wrapper; not affiliated with Plane. Plane operations and live schemas
come from the official `plane-mcp-server`, not a reimplemented REST API.

## Install

Copy `skills/plane-mcp` into a skill directory supported by your agent:

- OMP / Agents-compatible hosts: `~/.agents/skills/plane-mcp/`
- Claude Code: `~/.claude/skills/plane-mcp/`
- Project-scoped: `.agents/skills/plane-mcp/` or `.claude/skills/plane-mcp/`

Install from GitHub with the Skills CLI:

```bash
npx skills add GeederX/Plane_MCP_Skill --skill plane-mcp
```

Start a new agent session after installation so it discovers the skill.

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) and
Python 3.10+. Script dependencies are pinned in PEP 723 metadata. `uv run`
provisions them on first invocation; the default server runs through `uvx`.
No npm install, API-key file in the repository, or background service.

## Configure

Set `PLANE_API_KEY` and `PLANE_WORKSPACE_SLUG` in your private `~/.env` or
process environment. Get a key from **Plane Workspace Settings → API tokens**.
Set `PLANE_BASE_URL` for self-hosted Plane. Never paste keys into agent chat.
See [configuration](skills/plane-mcp/references/configuration.md) for explicit
MCP config, hosted HTTP/PAT, and the external OAuth bridge.

If Plane is currently auto-mounted by your host, disable/remove that entry
and start a new session. **A skill does not unload an existing MCP server.**
This repository deliberately ships no host-discovered `.mcp.json`, plugin MCP
registration, or always-on extension.

## Use

Ask the agent to use Plane, for example: “List projects in my Plane workspace”.
OMP also supports `/skill:plane-mcp` once installed.

Or exercise the client directly from this repository:

```bash
uv run skills/plane-mcp/scripts/plane.py tools
uv run skills/plane-mcp/scripts/plane.py describe project
uv run skills/plane-mcp/scripts/plane.py call workspace '{"action":"retrieve"}'
```

`tools` returns names only. `describe` fetches one live schema. `call` preserves
the MCP result and exits nonzero on tool errors. Each command closes its
connection. PQL grammar is fetched only before PQL usage; no eager schema dump.

## Verification

Smoke-verified with Plane server 0.3.4 and MCP SDK 1.28.1:

- Real Plane stdio: discover 30 tool names, fetch the `project` schema, retrieve
  workspace metadata, and list projects through the authenticated API.
- Default pinned `uvx` server and an explicit existing MCP config both work.
- Invalid action returns MCP `isError:true` and exit 1; unknown tool and
  non-object arguments also exit 1.
- HTTP and SSE: local SDK servers exercised schema discovery, successful
  computation, and failed-tool exit handling. Hosted Plane HTTP/PAT and the
  OAuth login flow were not exercised.

The script's adjacent `.lock` file pins transitive client dependencies.
Each CLI command starts a fresh connection: lower prompt overhead trades off
against connection/server-start latency. Upstream tool descriptions are still
loaded into context when explicitly requested.

## Upstream updates

The **Check Plane MCP updates** GitHub Actions workflow runs every Monday at
03:17 UTC (11:17 China Standard Time). You can also run it from
**Actions → Check Plane MCP updates → Run workflow**.

It queries PyPI, selects the newest stable release with non-yanked files, and
compares it with the server pin in `skills/plane-mcp/scripts/plane.py`.
Prereleases, development/local versions, empty releases, and downgrades are
excluded. If an update exists, it changes only that pin and creates or updates
one PR on `automation/plane-mcp-update`, assigned to the repository owner.
No newer version means no PR. There is no automatic merge.

The workflow uses GitHub's built-in token; it needs no personal token and stores
no Plane API key. Repository settings must permit Actions to create pull
requests under **Settings → Actions → General → Workflow permissions**.
The workflow explicitly requests contents and pull-request write access.
GitHub schedules are best-effort; public repositories may have scheduled
workflows disabled after inactivity. Re-enable in Actions or run manually.

### Review and apply an upgrade

1. Read the upstream release notes linked from the PR.
2. In a local clone, check out the PR with `gh pr checkout PR_NUMBER`.
3. With credentials in your private `~/.env`, run:

   ```bash
   uv run skills/plane-mcp/scripts/plane.py tools
   uv run skills/plane-mcp/scripts/plane.py describe project
   uv run skills/plane-mcp/scripts/plane.py call project '{"action":"list"}'
   ```

4. Check any additional Plane operations you rely on, then merge manually.
5. Reinstall from GitHub using the installation command above, or synchronize
   `skills/plane-mcp` to your agent's installed skill directory. A repository
   merge does not automatically update an already-installed copy.

The automated checks validate the updater, **not authenticated Plane
compatibility**. PRs created with `GITHUB_TOKEN` do not trigger ordinary PR
workflows, and this repository does not rely on them for Plane verification.
An explicit client `--config` continues to use its configured server; the
automated update only affects the client's default pinned server.

For a local version check (no Plane credentials needed):

```bash
uv run --locked .github/scripts/check_plane_update.py
```

Add `--apply` to update the local pin. This does not commit or merge anything.
Client dependencies and their lock file are separate from the server pin.

## Development

```bash
uv run --with packaging==26.3 python -m unittest discover -s tests -v
```

Regression tests cover version ordering, excluded releases, dry-run behavior,
idempotent application, downgrade prevention, and ambiguous pin rejection.
The checker was also smoke-tested against real PyPI metadata, including its
apply path and GitHub step output, using a temporary source file.

Keep `skills/plane-mcp` intact so Agent Skills installers copy the scripts and
references together. The MIT license covers this wrapper; upstream server and
dependencies retain their own licenses. Never publish personal MCP configs,
credential files, or private Plane result exports.
