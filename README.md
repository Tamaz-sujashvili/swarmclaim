# Agent Claims

Reserve files before multiple coding agents edit the same checkout. Each agent
registers a short plan and the files it needs. Overlapping claims are rejected,
and everyone can see who is working on what.

Agent Claims uses Python 3.9+ on macOS or Linux with no third-party packages.
Every participating agent must run commands against the same physical checkout
and follow the claim rules. The CLI coordinates plans. Agents still have direct
write access to source files.

## Install in your checkout

```sh
git clone https://github.com/Tamaz-sujashvili/agent-claims.git
python3 agent-claims/tools/install_agent_claims.py --root /path/to/your/checkout
cd /path/to/your/checkout
python3 tools/agent_claims.py status
```

The installer adds the CLI and a managed block in `AGENTS.md` and `CLAUDE.md`.
It also updates an existing `AGENTS.override.md` and adds a Git ignore rule for
runtime data. Review the changes and restart agents so they load the instructions.
For a quick trial, run the commands below directly from the Agent Claims clone.

## Reserve, check, and release

```sh
python3 tools/agent_claims.py claim --agent codex-1 \
  --plan 'Fix config parsing' --target src/config.py

python3 tools/agent_claims.py status

# A second agent trying the same file gets a conflict (exit 2).
python3 tools/agent_claims.py claim --agent claude-1 \
  --plan 'Add config validation' --target src/config.py

python3 tools/agent_claims.py check --agent codex-1 --target src/config.py
python3 tools/agent_claims.py release --agent codex-1
```

Use a unique agent ID per session. Repeat `--target` to reserve multiple files in
one operation. To expand a claim, submit the complete target list again. Claims
survive process exits and stay active until released.

For scripting, use `status --json`. For a human-readable view, open
`.agent-coordination/ACTIVE_TASKS.md` in the shared checkout. See the
[usage guide](docs/agent_claims.md) for recovery, exit codes, and symbol claims.

## Development

```sh
python3 -m unittest discover -s tests -v
```

## License

Source available under the [Agent Claims Personal Use License](LICENSE).
Individuals may use and privately modify it for personal, noncommercial
projects. Commercial use, organizational use, and monetization require
written permission from the copyright holder.
