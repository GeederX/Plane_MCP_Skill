# /// script
# requires-python = ">=3.10"
# dependencies = ["packaging==26.3"]
# ///
"""Check stable, non-yanked Plane MCP releases; optionally update the server pin."""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version

PYPI_URL = "https://pypi.org/pypi/plane-mcp-server/json"
DEFAULT_SOURCE = Path(__file__).resolve().parents[2] / "skills/plane-mcp/scripts/plane.py"
PIN = re.compile(r"plane-mcp-server==([A-Za-z0-9.!+_-]+)")


def latest_release(metadata):
    candidates = []
    for name, files in metadata["releases"].items():
        try:
            version = Version(name)
        except InvalidVersion:
            continue
        if version.is_prerelease or version.is_devrelease or version.local is not None:
            continue
        if any(not file.get("yanked", False) for file in files):
            candidates.append(version)
    if not candidates:
        raise ValueError("PyPI has no stable, non-yanked release files")
    return max(candidates)


def check_update(source_path, metadata, apply=False):
    source = source_path.read_text(encoding="utf-8")
    matches = list(PIN.finditer(source))
    if len(matches) != 1:
        raise ValueError("Expected exactly one Plane MCP server version pin")
    match = matches[0]
    current = Version(match.group(1))
    latest = latest_release(metadata)
    available = latest > current
    if available and apply:
        # Replace only the version capture; leave the client and its lock untouched.
        updated = source[:match.start(1)] + str(latest) + source[match.end(1):]
        source_path.write_text(updated, encoding="utf-8")
    return {
        "current_version": str(current),
        "latest_version": str(latest),
        "update_available": available,
        "applied": available and apply,
        "release_url": f"https://pypi.org/project/plane-mcp-server/{latest}/",
    }


def fetch_metadata():
    request = Request(PYPI_URL, headers={"User-Agent": "Plane-MCP-Skill-update-checker"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="client source containing the server pin")
    parser.add_argument("--apply", action="store_true", help="update the pin when a newer stable version exists")
    parser.add_argument("--github-output", type=Path, help="append step outputs for GitHub Actions")
    args = parser.parse_args()
    try:
        result = check_update(args.source, fetch_metadata(), apply=args.apply)
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8") as output:
                for key, value in result.items():
                    text = str(value).lower() if isinstance(value, bool) else value
                    output.write(f"{key}={text}\n")
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(f"Update check failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
