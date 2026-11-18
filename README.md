# SwarmClaim

Run several coding agents on one project. SwarmClaim helps keep their edits
from colliding during one-night MVPs, hackathons, and team projects where
agents work in the same checkout.

## The problem

You ask one agent to build a login page and another to add authentication.
Both need to edit the routes file. Without a way to see what the other agent
plans to change, they can overwrite each other's work or leave you sorting
out conflicting edits.

## How SwarmClaim helps

Before editing, each agent posts a short plan and claims the files it needs.
If another agent already claimed a file, SwarmClaim shows who has it and what
they're doing. The second agent can coordinate with them or pick another task.
When the first agent finishes, it releases the files.

Claims are advisory. Every agent needs to use the same checkout and follow
the claim rules. Agents still have direct write access to the files.

## Install in your checkout

Requires Python 3.9+ on macOS or Linux. There are no third-party packages.

```sh
git clone https://github.com/Tamaz-sujashvili/swarmclaim.git
python3 swarmclaim/tools/install_agent_claims.py --root /path/to/your/checkout
cd /path/to/your/checkout
python3 tools/agent_claims.py status
```

The installer adds the CLI and a managed block in `AGENTS.md` and `CLAUDE.md`.
It also updates an existing `AGENTS.override.md` and adds a Git ignore rule for
runtime data. Review the changes and restart agents so they load the instructions.
For a quick trial, run the commands below directly from the SwarmClaim clone.

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

SwarmClaim is available under the [Sustainable Use License, Version 1.0](LICENSE).
It permits personal and noncommercial use, plus internal business use by
companies. It restricts paid redistribution and paid services using the
software. This is a source-available license, not an OSI-approved open-source
license.

## AI training

Training, fine-tuning, distillation, and other machine-learning use of
this repository — including of the source code and the licensor’s
documentation — is prohibited. See the [license](LICENSE) for the full
terms and the limited exceptions (including coding agents using the
tool as intended).

This reservation is declared for the purposes of Article 4 of
Directive (EU) 2019/790.
