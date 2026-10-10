# Local configuration

This skill does not change the agent host's MCP configuration. To get the
context reduction, remove or disable the existing Plane auto-mounted server in
that host, then start a new session. Installing a skill alone cannot remove
already-injected schemas, routes, or instructions from an existing conversation.

## Default local server

Install [uv](https://docs.astral.sh/uv/getting-started/installation/). Keep
credentials in `~/.env` (restrict file permissions), or export them in the
process environment. Example file shape; replace placeholders locally:

```dotenv
PLANE_API_KEY=your-local-api-token
PLANE_WORKSPACE_SLUG=your-workspace
# Only for self-hosted Plane:
# PLANE_BASE_URL=https://plane.example.com
```

The script loads `~/.env` automatically, **not the current project's `.env`**.
Use `--env-file /path/to/private.env` to choose another file. Environment
variables override dotenv values; explicit server `env` overrides both.
Dotenv interpolation and shell evaluation are disabled.

## Reuse an explicit MCP config

```bash
uv run /path/to/skill/scripts/plane.py --config /path/to/mcp.json --server plane describe workitem
```

Supports `mcpServers.NAME` with `stdio` (`command`, `args`, `env`, `cwd`),
streamable `http` (`url`, `headers`), or legacy `sse` (`url`, `headers`).
Omitted `type` is inferred from `url`/`command`. `${NAME}` values are expanded
from the selected dotenv file and process environment; missing variables fail.

Only the explicitly selected entry is used, even if it has `enabled:false`
for the host. No auto-discovery, host credential store, `!command`
substitution, or host `auth`/`oauth` handling. `cwd` and paths must be portable
for the user's machine; use absolute paths or `${HOME}` where appropriate.
Only use trusted config files: a stdio command executes local code.

An HTTP/PAT config kept **outside host auto-discovery paths**:

```json
{
  "mcpServers": {
    "plane": {
      "type": "http",
      "url": "https://mcp.plane.so/http/api-key/mcp",
      "headers": {
        "Authorization": "Bearer ${PLANE_API_KEY}",
        "X-Workspace-slug": "${PLANE_WORKSPACE_SLUG}"
      }
    }
  }
}
```

The hosted endpoint is supplied by Plane. Self-hosted MCP endpoints can use the
same transport. HTTP redirects are not followed by the streamable HTTP client.

## OAuth through an external bridge

Native OAuth login/refresh is not implemented by this skill. For hosted OAuth,
use Plane's documented `mcp-remote` stdio bridge (Node.js 22+). It owns browser
login and local token storage; the skill only owns the MCP client connection:

```json
{
  "mcpServers": {
    "plane": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://mcp.plane.so/http/mcp"]
    }
  }
}
```

First login may require an interactive terminal. Keep this config out of the
host's automatic MCP registration. Prefer API-key stdio for unattended usage.

## Errors and output

- `tools`: tool names only. `describe`: one complete live tool schema.
- `call`: complete MCP result, including text and structured content.
- Exit 0 on success, 1 for config/connection/tool errors, 130 for interruption.
- No automatic retry, especially for writes with uncertain outcomes.
- Request timeout covers initialization and individual MCP requests, not the
  entire CLI lifetime. Initial `uv run` dependency provisioning happens before
  the script starts; a spawned `uvx` server's startup happens during initialization.
- Local server stderr is captured, redacted, and printed on client failures.
  Known credential environment/header values are redacted from output; this
  is best-effort, not a guarantee against a malicious server. Do not enable
  server payload logging or publish raw results containing private Plane data.

Upstream references:
[Plane MCP package](https://pypi.org/project/plane-mcp-server/),
[Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk).
