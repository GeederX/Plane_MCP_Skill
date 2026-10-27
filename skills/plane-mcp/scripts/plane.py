# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp==1.28.1", "python-dotenv==1.2.2"]
# ///
"""Short-lived Plane MCP client. No host registration or schema cache."""

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
from contextlib import AsyncExitStack
from datetime import timedelta
from pathlib import Path

import httpx
from dotenv import dotenv_values
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import PaginatedRequestParams


DEFAULT_SERVER = {
    "type": "stdio",
    "command": "uvx",
    "args": ["plane-mcp-server==0.3.5", "stdio"],
}
ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
SECRET_NAME = re.compile(r"key|token|secret|password|authorization|cookie", re.I)


def expand(value, env):
    """Expand only ${NAME}; never evaluate shell commands."""
    if isinstance(value, str):
        def replace(match):
            name = match.group(1)
            if not env.get(name):
                raise ValueError(f"Missing environment variable: {name}")
            return env[name]
        return ENV_PATTERN.sub(replace, value)
    if isinstance(value, list):
        return [expand(item, env) for item in value]
    if isinstance(value, dict):
        return {key: expand(item, env) for key, item in value.items()}
    return value


def load_settings(args):
    env_path = Path(args.env_file).expanduser()
    if args.env_file != "~/.env" and not env_path.is_file():
        raise ValueError(f"Environment file not found: {env_path}")
    env = {key: value for key, value in dotenv_values(env_path, interpolate=False).items()
           if value is not None} if env_path.is_file() else {}
    env.update(os.environ)
    if args.config:
        config = json.loads(Path(args.config).expanduser().read_text())
        server = config["mcpServers"][args.server]
        # An explicitly selected entry can be enabled:false in the host config.
        # Host-specific OAuth credentials and !command expansion are not portable.
        if server.get("auth") or server.get("oauth"):
            raise ValueError("Host-managed auth is unsupported; use API-key environment variables, PAT headers, or an authenticated stdio bridge")
    else:
        server = dict(DEFAULT_SERVER)
        for key in ("PLANE_API_KEY", "PLANE_WORKSPACE_SLUG"):
            if not env.get(key):
                raise ValueError(f"Missing environment variable: {key}")
    server = expand(server, env)
    env.update(server.get("env", {}))
    env.setdefault("LOG_PAYLOADS", "false")
    env.setdefault("LOG_USER_INFO", "false")
    return server, env


def redact(text, env, server):
    secrets = [value for key, value in env.items() if SECRET_NAME.search(key) and value]
    secrets.extend(value for key, value in server.get("headers", {}).items()
                   if SECRET_NAME.search(key) and value)
    # Also remove bearer values when an error omits the prefix.
    secrets.extend(value[7:] for value in list(secrets) if value.lower().startswith("bearer "))
    for value in sorted(set(secrets), key=len, reverse=True):
        text = text.replace(value, "<redacted>")
    return text


def exception_message(exc):
    children = getattr(exc, "exceptions", None)
    if children:
        return "; ".join(exception_message(child) for child in children)
    return f"{type(exc).__name__}: {exc}"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default="~/.env", help="dotenv file; process environment takes precedence")
    parser.add_argument("--config", help="explicit MCP JSON file; never auto-discovered")
    parser.add_argument("--server", default="plane", help="entry in mcpServers")
    parser.add_argument("--timeout", type=float, default=60, help="MCP request timeout in seconds")
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("tools", help="list tool names only")
    describe = commands.add_parser("describe", help="fetch one tool's description and JSON schema")
    describe.add_argument("tool")
    call = commands.add_parser("call", help="call a tool with a JSON object; '-' reads stdin")
    call.add_argument("tool")
    call.add_argument("arguments", nargs="?", default="{}")
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    return args


async def execute(args, server, env, errlog):
    # Validate JSON before spawning a process or contacting a server.
    arguments = None
    if args.operation == "call":
        arguments = json.loads(sys.stdin.read() if args.arguments == "-" else args.arguments)
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be a JSON object")
    kind = server.get("type", "http" if "url" in server else "stdio")
    async with AsyncExitStack() as stack:
        if kind == "stdio":
            streams = await stack.enter_async_context(stdio_client(
                StdioServerParameters(command=server["command"], args=server.get("args", []),
                                      env=env, cwd=server.get("cwd")), errlog=errlog))
        elif kind == "http":
            http = await stack.enter_async_context(httpx.AsyncClient(
                headers=server.get("headers", {}), timeout=args.timeout, follow_redirects=False))
            streams = await stack.enter_async_context(streamable_http_client(server["url"], http_client=http))
        elif kind == "sse":
            streams = await stack.enter_async_context(sse_client(
                server["url"], headers=server.get("headers", {}),
                timeout=args.timeout, sse_read_timeout=args.timeout))
        else:
            raise ValueError(f"Unsupported transport: {kind}")
        session = await stack.enter_async_context(ClientSession(
            streams[0], streams[1], read_timeout_seconds=timedelta(seconds=args.timeout)))
        await session.initialize()
        if args.operation == "call":
            result = await session.call_tool(args.tool, arguments)
            return result.model_dump(mode="json", by_alias=True, exclude_none=True), 1 if result.isError else 0
        tools = []
        cursor = None
        while True:
            page = await session.list_tools(params=PaginatedRequestParams(cursor=cursor) if cursor else None)
            for tool in page.tools:
                if args.operation == "describe" and tool.name == args.tool:
                    return tool.model_dump(mode="json", by_alias=True, exclude_none=True), 0
                tools.append(tool.name)
            cursor = page.nextCursor
            if not cursor:
                break
        if args.operation == "describe":
            raise ValueError(f"Unknown tool: {args.tool}")
        return {"tools": tools}, 0


def main():
    args = parse_args()
    server, env = {}, dict(os.environ)
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errlog:
        try:
            server, env = load_settings(args)
            result, status = asyncio.run(execute(args, server, env, errlog))
            print(redact(json.dumps(result, ensure_ascii=False, indent=2), env, server))
            return status
        except (Exception, KeyboardInterrupt) as exc:
            print(redact(exception_message(exc), env, server), file=sys.stderr)
            errlog.seek(0)
            diagnostics = errlog.read()
            if diagnostics:
                print(redact(diagnostics, env, server), file=sys.stderr)
            return 130 if isinstance(exc, KeyboardInterrupt) else 1


if __name__ == "__main__":
    sys.exit(main())
