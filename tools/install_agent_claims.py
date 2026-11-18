#!/usr/bin/env python3
# Copyright (c) 2026 Tamaz-sujashvili. Personal-use terms:
# https://github.com/Tamaz-sujashvili/swarmclaim/blob/main/LICENSE
"""Install SwarmClaim and add coordination rules to a shared checkout."""
import argparse
from pathlib import Path
from stat import S_IMODE
import sys

from agent_claims import atomic_write

SOURCE = Path(__file__).resolve().with_name('agent_claims.py')
IGNORE_RULE = '/.agent-coordination/'
START = '<!-- AGENT-CLAIMS:START -->'
END = '<!-- AGENT-CLAIMS:END -->'
RULES = f'''{START}
## Multi-agent shared-worktree coordination (mandatory)

This repository can have multiple coding agents working simultaneously. Before editing
or creating ANY project code/config/test/documentation file, follow these rules:

1. Inspect `python3 tools/agent_claims.py status` and read relevant existing code.
2. Make a concrete edit plan. Reserve EVERY file you intend to touch, using a unique
   ID per live agent session. Example:
   `python3 tools/agent_claims.py claim --agent codex-refactor-1 --plan "Change optimizer validation" --target src/optimizer.py --target tests/test_optimizer.py`
3. **STOP if claim exits nonzero.** Do not edit the conflicting file. Coordinate,
   select other targets, or wait until the owner has released it. Do not overwrite
   other agents' claims.
4. Before adding a new edit target, re-run `claim` with your COMPLETE intended
   target list; it atomically updates your set of reserved files. For extra safety,
   run `python3 tools/agent_claims.py check --agent ID --target path/to/file`.
5. Keep your edits within claimed targets. Changes via formatters, code generators,
   migrations, or test fixups ALSO need claims. Don't use `git reset`, `git clean`,
   blanket staging, or other commands that can discard or commit other agents' work.
6. After completing edits/tests, release with
   `python3 tools/agent_claims.py release --agent ID`.
   If work is paused, KEEP the claim until you have safely handed it off.
7. Default to whole-file claims. `file.py::function` is an experimental opt-in
   (`--allow-disjoint-symbols`) and is not safe for concurrent same-file writes;
   only use it when both agents explicitly choose it and changes can be serialized.

Claims live in `.agent-coordination/claims.json`, with a readable plan in
`.agent-coordination/ACTIVE_TASKS.md`. Do not edit either manually. These are
runtime data on this ONE shared filesystem, NOT Git-synchronized coordination.
{END}
'''


def read_destination(path: Path) -> tuple:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f'Expected a regular file or missing path: {path}')
    if not path.exists():
        return '', 0o644
    # Preserve existing line endings and everything outside the managed block.
    return path.read_bytes().decode('utf-8'), S_IMODE(path.stat().st_mode)


def append_block(content: str, block: str, newline: str) -> str:
    separator = ('' if content.endswith('\n') else newline) + newline if content else ''
    return content + separator + block + newline


def instruction_text(path: Path, content: str) -> str:
    newline = '\r\n' if '\r\n' in content else '\n'
    start = content.find(START)
    end = content.find(END)
    block = RULES.rstrip('\n').replace('\n', newline)
    if start == end == -1:
        return append_block(content, block, newline)
    if start == -1 or end < start or content.count(START) != 1 or content.count(END) != 1:
        raise ValueError(f'Invalid SwarmClaim markers in {path}')
    return content[:start] + block + content[end + len(END):]


def install(root: Path) -> None:
    tools = root / 'tools'
    if tools.is_symlink() or (tools.exists() and not tools.is_dir()):
        raise ValueError(f'Expected a directory or missing path: {tools}')
    destination = tools / SOURCE.name
    source = SOURCE.read_bytes().decode('utf-8')
    current, _ = read_destination(destination)
    if destination.exists() and current != source:
        raise ValueError(f'Different CLI already exists at {destination}. Compare the files before replacing it.')

    names = ['AGENTS.md', 'CLAUDE.md']
    override = root / 'AGENTS.override.md'
    if override.exists() or override.is_symlink():
        names.append(override.name)
    updates = []
    for name in names:
        path = root / name
        content, mode = read_destination(path)
        updated = instruction_text(path, content)
        if updated != content:
            updates.append((path, updated, mode))
    gitignore = root / '.gitignore'
    content, mode = read_destination(gitignore)
    rules = content.rstrip().splitlines()
    if not rules or rules[-1] not in (IGNORE_RULE, '.agent-coordination/'):
        newline = '\r\n' if '\r\n' in content else '\n'
        entry = f'# Runtime claims shared by simultaneous agents{newline}{IGNORE_RULE}'
        updates.insert(0, (gitignore, append_block(content, entry, newline), mode))

    if not destination.exists():
        tools.mkdir(exist_ok=True)
        atomic_write(destination, source, 0o644)
        print(f'Installed {destination.relative_to(root)}')
    for path, updated, mode in updates:
        atomic_write(path, updated, mode)
        print(f'Updated {path.name}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=SOURCE.parent.parent,
                        help='destination checkout (defaults to the parent of tools/)')
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        parser.error(f'Not a directory: {root}')
    try:
        install(root)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    print('\nSetup done. Restart active coding-agent sessions to reload instructions.')
    print(f'Checkout: {root}')
    print('From that checkout run: python3 tools/agent_claims.py status')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
