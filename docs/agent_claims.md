# Multi-agent change claims for one shared worktree

SwarmClaim coordinates Codex, Pi, Claude Code, Cursor, or other coding agents working in the **same checkout**. Agents publish a plan, reserve every file they expect to edit, and release their claims when finished. It uses Python 3.9+ on Linux or macOS.

## Install without overwriting existing instruction files

From an SwarmClaim clone, point the installer at your existing checkout:

```bash
python3 tools/install_agent_claims.py --root /path/to/your/repository
cd /path/to/your/repository
python3 tools/agent_claims.py status
```

The installer copies `tools/agent_claims.py`, manages a delimited section in `AGENTS.md`, `CLAUDE.md`, and any existing `AGENTS.override.md`, and ignores the runtime directory in Git. Repeating the same install leaves the checkout unchanged. If you already have a different version at `tools/agent_claims.py`, compare it with the new version and replace it deliberately before rerunning setup. Review `git status --short` and `git diff` after installing. Restart your agents so they pick up the instructions. For harnesses with other or nested instruction files, ensure their effective instructions include the coordination rules.

## Basic commands

```bash
# Codex announces a plan BEFORE writing any code
python3 tools/agent_claims.py claim \
  --agent codex-1 \
  --plan 'Refactor alpha scoring' \
  --target src/alpha/scorer.py \
  --target tests/test_scorer.py

# Pi sees everybody's task plan
python3 tools/agent_claims.py status
cat .agent-coordination/ACTIVE_TASKS.md

# Pi tries the same file: REJECTED, exit code 2
python3 tools/agent_claims.py claim \
  --agent pi-1 \
  --plan 'Modify alpha scorer error handling' \
  --target src/alpha/scorer.py

# Pi may reserve an unrelated file
python3 tools/agent_claims.py claim \
  --agent pi-1 \
  --plan 'Improve logs' \
  --target src/logging.py

# After coding and testing, explicitly release
python3 tools/agent_claims.py release --agent codex-1
python3 tools/agent_claims.py release --agent pi-1
```

A claim **replaces** that agent's previous target list atomically. To add a file, provide **all** currently held targets plus the new one. To release just one target: `release --agent codex-1 --target src/alpha/scorer.py`. Use a unique session-specific ID; one agent must not impersonate or release another agent's ID except as explicit administrative recovery.

Targets are checkout-relative file paths, including files you plan to create.
Existing aliases for the same file conflict. Use consistent path spelling for
files that do not exist yet, especially on a case-insensitive filesystem.

## Automation and recovery

- Exit **0** means success. For claim and release, the registry is authoritative even if the Markdown board update emits a warning.
- Exit **2** means a conflict, a denied check, an unheld target during partial release, or CLI argument syntax error.
- Exit **1** means an operational error, invalid data, or a release for an agent ID with no claim.
- Use `status --json` for the live registry and `status --refresh-board` to rebuild the board after resolving a write error.
- After a crash, confirm the agent has stopped editing before releasing its claim. Use `release --agent ID` to release everything held by that ID.

## Experimental function-level claims

Default blocks the **same file** even if different symbols would be edited, because simultaneous full-file saves, imports, formatters, and Git operations can still collide. For explicitly planned, nonoverlapping changes, **both agents** can opt into symbol-level claims:

```bash
python3 tools/agent_claims.py claim --agent codex-2 \
  --plan 'Update normalize() only' \
  --target 'src/alpha/scorer.py::normalize' --allow-disjoint-symbols

python3 tools/agent_claims.py claim --agent pi-2 \
  --plan 'Update rank() only' \
  --target 'src/alpha/scorer.py::rank' --allow-disjoint-symbols
```

The second claim passes, but `::normalize` vs `::normalize` or `::MyClass` vs `::MyClass.method` fails. **This is symbol-name comparison, not AST inspection or mandatory write enforcement.** For real code safety, serialize those edits or use separate worktrees and merge carefully. Be aware that import changes, shared helpers, or formatting change other code sections, requiring broader claims.

## Architecture and limitations

- `flock()` on a local POSIX filesystem protects the *claim registry* against races. It does **not** lock source files and cannot stop agents that ignore the protocol. All sessions must access the SAME physical `.agent-coordination/` folder; two independent clones, different mounts with broken locks, or Git sync do not share live claims.
- The registry is `.agent-coordination/claims.json`. The human-readable board is `.agent-coordination/ACTIVE_TASKS.md`. Both are transient workspace state, not for commits. The registry is written atomically; all registry reads/writes hold `claims.lock`.
- Claims persist after crashes. Check status and release a verified abandoned claim manually. There is no automatic TTL, to prevent accidental concurrent edits when agents run long tasks.
- Agents need a habit or harness hooks enforcing calls. Instructions alone do **not** guarantee compliance. For stronger isolation, use Git worktrees with integration rules or agent-harness tool hooks to block unclaimed writes.
- Run this on the **VPS** for all agents, including Mac/Windows-connected agents executing via SSH to that one checkout. The script uses Unix `fcntl` and does not run natively on Windows.
- Never use one agent ID for two concurrent sessions. Scope correctness requires the agent to declare every touched file; the script cannot discover unspecified edits or guarantee lock ownership by identity.

## Testing

```bash
python3 -m unittest discover -s tests -v
```
