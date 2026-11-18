#!/usr/bin/env python3
# Copyright (c) 2026 Tamaz-sujashvili. Personal-use terms:
# https://github.com/Tamaz-sujashvili/agent-claims/blob/main/LICENSE
"""Coordinate coding agents sharing ONE repository/worktree (POSIX host).

Requires Python 3.9+, standard library only. Claims are advisory: use agent
instructions and, for hard safety, separate worktrees/branches.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import tempfile

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
STATE_NAME = "claims.json"
LOCK_NAME = "claims.lock"
BOARD_NAME = "ACTIVE_TASKS.md"
SCOPE_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*$")
AGENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_target(raw: str, root: Path) -> dict:
    """Normalize repo-relative path[::symbol] and prevent escaping repo."""
    value = raw.strip()
    parts = value.split("::")
    if len(parts) not in (1, 2):
        raise ValueError(f"Bad target {raw!r}: use path/to/file or path/to/file::symbol")
    raw_path = parts[0]
    symbol = parts[1] if len(parts) == 2 else None
    if symbol is not None and not SCOPE_RE.fullmatch(symbol):
        raise ValueError(f"Invalid symbol {symbol!r} in {raw!r}; use Class.method or functionName")
    if not raw_path or "\\" in raw_path or not raw_path.isprintable() or raw_path.startswith("/"):
        raise ValueError(f"Target must be a relative POSIX-style filename: {raw!r}")
    if ":" in raw_path:
        raise ValueError(f"Invalid path target: {raw!r}")
    if any(part == ".." for part in raw_path.split("/")):
        raise ValueError(f"Parent paths are forbidden: {raw!r}")
    rel = os.path.normpath(raw_path)
    if rel in ("", ".") or rel.startswith("../"):
        raise ValueError(f"Target must be a file: {raw!r}")
    resolved = (root / rel).resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise ValueError(f"Target escapes the repository through a symlink: {raw!r}")
    if resolved == root or resolved.is_dir():
        raise ValueError(f"Target must be a file: {raw!r}")
    return {"path": rel, "symbol": symbol}


def printable(t: dict) -> str:
    return t["path"] + ("::" + t["symbol"] if t["symbol"] else "")


def symbols_collide(left: str, right: str) -> bool:
    return left == right or left.startswith(right + ".") or right.startswith(left + ".")


def same_file(root: Path, left: str, right: str) -> bool:
    if left == right:
        return True
    first = (root / left).resolve()
    second = (root / right).resolve()
    if first == second:
        return True
    try:
        return first.samefile(second)
    except (FileNotFoundError, NotADirectoryError):
        return False


def conflicting(root: Path, a: dict, a_shared: bool, b: dict, b_shared: bool) -> bool:
    if not same_file(root, a["path"], b["path"]):
        return False
    # Whole-file claim wins. Different symbols share a file only when both
    # agents explicitly opt in. This does NOT guarantee clean concurrent edits.
    if not a["symbol"] or not b["symbol"]:
        return True
    if not (a_shared and b_shared):
        return True
    return symbols_collide(a["symbol"], b["symbol"])


def validate_agent(agent: str) -> None:
    if not AGENT_RE.fullmatch(agent):
        raise ValueError("Agent ID must be 1-80 letters, digits, dots, hyphens or underscores")


def atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
        try:
            flags = getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY
            dir_fd = os.open(path.parent, flags)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError as exc:
            print(f"WARNING: {path.name} was replaced, but its directory could not be synced: {exc}", file=sys.stderr)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def valid_claim(agent: str, claim: dict) -> bool:
    if not AGENT_RE.fullmatch(agent) or not isinstance(claim, dict):
        return False
    if not all(isinstance(claim.get(key), str) for key in ("plan", "created_at", "updated_at")):
        return False
    if not isinstance(claim.get("allow_disjoint_symbols", False), bool):
        return False
    targets = claim.get("targets")
    if not isinstance(targets, list) or not targets:
        return False
    for target in targets:
        if not isinstance(target, dict):
            return False
        path = target.get("path")
        symbol = target.get("symbol")
        if not isinstance(path, str) or os.path.isabs(path) or not path.isprintable():
            return False
        if path == "." or ".." in Path(path).parts or "symbol" not in target:
            return False
        if symbol is not None and (not isinstance(symbol, str) or not SCOPE_RE.fullmatch(symbol)):
            return False
    return True


@contextmanager
def locked_state(root: Path):
    data_dir = root / ".agent-coordination"
    if data_dir.is_symlink():
        raise RuntimeError(f"Coordination directory must not be a symlink: {data_dir}")
    data_dir.mkdir(exist_ok=True)
    with (data_dir / LOCK_NAME).open("a+") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            path = data_dir / STATE_NAME
            if path.exists():
                try:
                    state = json.loads(path.read_text(encoding="utf-8"))
                except (ValueError, UnicodeError) as exc:
                    raise RuntimeError(f"Coordination data invalid: {path}; refusing to overwrite ({exc})")
                if (
                    not isinstance(state, dict)
                    or type(state.get("schema")) is not int
                    or state["schema"] != 1
                    or not isinstance(state.get("claims"), dict)
                    or not all(valid_claim(agent, claim) for agent, claim in state["claims"].items())
                ):
                    raise RuntimeError(f"Unrecognized coordination data: {path}; refusing to overwrite")
            else:
                state = {"schema": 1, "claims": {}}
            yield state, data_dir
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def board(state: dict) -> str:
    lines = ["# Active agent claims", "", "Generated by `tools/agent_claims.py`. Do not edit this file manually.", "", "**Source of truth:** `.agent-coordination/claims.json`. Use the CLI to claim/release.", ""]
    if not state["claims"]:
        lines.append("No active claims.")
    for agent, claim in sorted(state["claims"].items()):
        plan = claim["plan"].replace("\n", " ").replace("\r", " ")
        lines.extend([f"## {agent}", "", f"**Plan:** {plan}", f"**Claimed:** {claim['created_at']}", "", "**Targets:**", ""])
        lines.extend(f"- `{printable(target)}`" for target in claim["targets"])
        if claim.get("allow_disjoint_symbols"):
            lines.extend(["", "Opted in to disjoint-symbol sharing (same-file edits still risky)."])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_state(state: dict, data_dir: Path) -> bool:
    atomic_write(data_dir / STATE_NAME, json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    try:
        atomic_write(data_dir / BOARD_NAME, board(state))
    except OSError as exc:
        print(f"WARNING: registry saved, but the task board could not be updated: {exc}", file=sys.stderr)
        print("Run status --refresh-board after fixing the board path.", file=sys.stderr)
        return False
    return True


def cmd_claim(args: argparse.Namespace, root: Path) -> int:
    validate_agent(args.agent)
    if not args.plan.strip():
        raise ValueError("--plan cannot be empty")
    if len(args.plan) > 2000:
        raise ValueError("--plan is too long (max 2000 characters)")
    targets = [normalize_target(t, root) for t in args.target]
    unique = {printable(t): t for t in targets}
    targets = list(unique.values())
    if not targets:
        raise ValueError("Claim at least one --target")

    with locked_state(root) as (state, data_dir):
        problems = []
        for other_agent, other in state["claims"].items():
            if other_agent == args.agent:
                continue
            for target in targets:
                for held in other["targets"]:
                    if conflicting(root, target, args.allow_disjoint_symbols, held, other.get("allow_disjoint_symbols", False)):
                        problems.append((printable(target), other_agent, printable(held), other["plan"]))
        if problems:
            print("REJECTED: conflicting active claims; nothing was changed.", file=sys.stderr)
            for target, owner, held, plan in problems:
                print(f"  {target} conflicts with {owner}: {held} (plan: {plan})", file=sys.stderr)
            return 2
        prior = state["claims"].get(args.agent)
        state["claims"][args.agent] = {
            "plan": args.plan.strip(),
            "targets": targets,
            "allow_disjoint_symbols": bool(args.allow_disjoint_symbols),
            "created_at": prior["created_at"] if prior else utc_now(),
            "updated_at": utc_now(),
        }
        board_updated = write_state(state, data_dir)
    print(f"CLAIMED for {args.agent}: " + ", ".join(printable(t) for t in targets))
    if args.allow_disjoint_symbols:
        print("WARNING: symbol sharing is a declaration-only check, not an AST/change guard or safe concurrent writing.")
    if board_updated:
        print("Plan written to .agent-coordination/ACTIVE_TASKS.md.")
    print("Release when done.")
    return 0


def cmd_status(args: argparse.Namespace, root: Path) -> int:
    with locked_state(root) as (state, data_dir):
        if args.refresh_board:
            atomic_write(data_dir / BOARD_NAME, board(state))
        if args.json:
            print(json.dumps(state, ensure_ascii=False, indent=2))
            return 0
        if not state["claims"]:
            print("No active claims.")
        for agent, claim in sorted(state["claims"].items()):
            print(f"[{agent}] {claim['plan']}")
            for target in claim["targets"]:
                print(f"  - {printable(target)}")
            print(f"  updated: {claim['updated_at']}")
    return 0


def cmd_check(args: argparse.Namespace, root: Path) -> int:
    validate_agent(args.agent)
    requested = [normalize_target(t, root) for t in args.target]
    with locked_state(root) as (state, _):
        held = state["claims"].get(args.agent)
        if not held:
            print(f"DENIED: {args.agent} has no active claim.", file=sys.stderr)
            return 2
        for wanted in requested:
            covers = any(
                same_file(root, t["path"], wanted["path"]) and (
                    t["symbol"] is None or (
                        wanted["symbol"] is not None and (
                            wanted["symbol"] == t["symbol"] or wanted["symbol"].startswith(t["symbol"] + ".")
                        )
                    )
                )
                for t in held["targets"]
            )
            if not covers:
                print(f"DENIED: {args.agent} did not claim {printable(wanted)}", file=sys.stderr)
                return 2
    print("OK: targets are claimed by this agent.")
    return 0


def cmd_release(args: argparse.Namespace, root: Path) -> int:
    validate_agent(args.agent)
    with locked_state(root) as (state, data_dir):
        if args.agent not in state["claims"]:
            print(f"No claim found for {args.agent}.")
            return 1
        if args.target:
            to_release = [normalize_target(t, root) for t in args.target]
            existing = state["claims"][args.agent]["targets"]
            released = set()
            for wanted in to_release:
                matches = {index for index, target in enumerate(existing)
                           if target["symbol"] == wanted["symbol"]
                           and same_file(root, target["path"], wanted["path"])}
                if not matches:
                    print(f"Not claimed by {args.agent}: {printable(wanted)}", file=sys.stderr)
                    return 2
                released.update(matches)
            remaining = [target for index, target in enumerate(existing) if index not in released]
            if remaining:
                state["claims"][args.agent]["targets"] = remaining
                state["claims"][args.agent]["updated_at"] = utc_now()
            else:
                del state["claims"][args.agent]
        else:
            del state["claims"][args.agent]
        write_state(state, data_dir)
    print(f"RELEASED claims for {args.agent}" + (": " + ", ".join(args.target) if args.target else ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="repo root (defaults to parent of tools/)")
    sub = parser.add_subparsers(dest="command", required=True)
    claim = sub.add_parser("claim", help="Atomically register a task plan and target claims")
    claim.add_argument("--agent", required=True, help="unique agent/session name")
    claim.add_argument("--plan", required=True, help="describe changes BEFORE coding")
    claim.add_argument("--target", action="append", required=True, help="repo-relative file or file::symbol; repeat for multiple targets")
    claim.add_argument("--allow-disjoint-symbols", action="store_true", help="opt into same-file different-symbol claims when both agents opt in")
    status = sub.add_parser("status", help="Read active plans")
    status.add_argument("--json", action="store_true", help="print the registry as JSON")
    status.add_argument("--refresh-board", action="store_true", help="regenerate the Markdown task board")
    check = sub.add_parser("check", help="Check that an agent has already claimed targets")
    check.add_argument("--agent", required=True)
    check.add_argument("--target", action="append", required=True)
    release = sub.add_parser("release", help="Release all or selected target claims")
    release.add_argument("--agent", required=True)
    release.add_argument("--target", action="append", help="release only these targets; default releases all")
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        parser.error(f"Not a directory: {root}")
    try:
        return {"claim": cmd_claim, "status": cmd_status, "check": cmd_check, "release": cmd_release}[args.command](args, root)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
