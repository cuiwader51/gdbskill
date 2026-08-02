# gdb-debugging skill

An on-demand **agent skill** that turns your coding agent into a GDB expert for triaging and
root-causing native crashes: core dumps, kernel oops/panics, segfaults, memory corruption,
deadlocks/hangs, and remote/embedded targets. Works for **C, C++, Rust, Go, and mixed** binaries.

## What's inside

```
gdb-debugging/
├── SKILL.md                     # entry point: triage flow + golden rules
├── references/
│   ├── core-dumps.md            # post-mortem core analysis
│   ├── kernel-oops.md           # oops/panic decode + vmcore/crash utility
│   ├── live-debugging.md        # attach, breakpoints, reverse/rr
│   ├── memory-corruption.md     # SIGSEGV, UAF, double-free, overflows, poison bytes
│   ├── deadlocks-hangs.md       # thread stacks, lock ownership, spin vs block
│   ├── remote-embedded.md       # gdbserver, cross, KGDB, QEMU, JTAG/OpenOCD
│   ├── agent-automation.md      # drive gdb from an agent/CLI: batch, interactive, MI, WSL
│   └── gdb-cheatsheet.md        # command reference + per-language setup
└── scripts/
    ├── triage.gdb               # one-shot crash summary (gdb -x)
    ├── triage-core.sh           # batch a directory of cores into reports
    ├── gdb_agent.py             # doctor, bundle, verify, guide, JSON-lines GDB/MI
    ├── ci-triage.sh             # preserve failed-test status and bundle cores
    └── gdbinit-recommended      # sane ~/.gdbinit defaults + custom commands
  ├── probes/                      # crash, deadlock, heap, and watchpoint probes
  └── tests/                       # dependency-free controller/report tests
```

## How agents use it

When you describe a crash/dump/hang, the agent loads `SKILL.md`, follows the triage decision flow,
and pulls in only the relevant reference file. The scripts are runnable directly.

## Requirements / environment

- **GDB** (`gdb`), and for cross/kernel work `gdb-multiarch`. For heap bugs, `valgrind`/ASan help.
- The binary's **debug info** (`-g`), or matching `-dbgsym`/`debuginfo` packages / `debuginfod`.
- **On Windows**, Linux core dumps need **Linux GDB** — run everything under **WSL**.
  A Windows-native (MinGW) gdb cannot read a Linux ELF core.
  ```powershell
  # from PowerShell, drive Linux gdb via WSL:
  wsl gdb --batch -x scripts/triage.gdb ./app ./core
  ```
  The agent does this automatically; see [references/agent-automation.md](references/agent-automation.md).

## Try it in the GitHub Copilot CLI

The [GitHub Copilot CLI](https://docs.github.com/copilot/github-copilot-cli) reads the **same skill
format**, so you can use this skill from your terminal.

**Option A — install for your agent (recommended).** Copy the `gdb-debugging/` folder into a skills
directory your tool scans (see [Install](#install) for the full list), then run your agent:
```powershell
Copy-Item -Recurse gdb-debugging "$HOME/.copilot/skills/gdb-debugging"   # GitHub Copilot CLI
copilot
# then ask, e.g.:  "analyze the core at examples/crash-demo/core with binary examples/crash-demo/crash"
```

**Option B — team-shared in a repo.** Commit the folder under a location the tool scans, e.g.
`.github/skills/gdb-debugging/` (Copilot) or `.claude/skills/gdb-debugging/` (Claude), and the CLI
auto-discovers it when run from that repo.

**One-shot / non-interactive:**
```powershell
copilot -p "Using the gdb-debugging skill, run examples/crash-demo/demo-add-symbol-file.sh under WSL and explain the before/after"
```

Notes:
- Approve the terminal commands when prompted (or start with `copilot --allow-all-tools` if you trust the flow).
- On Windows the CLI must call `wsl gdb ...` for Linux cores — the skill already instructs this.
- `gh copilot suggest/explain` is a *different* tool (command suggestions, not agentic skill execution);
  use the standalone `copilot` CLI for this skill.

## Example: real GDB output

Running the bundled [examples/crash-demo/demo-add-symbol-file.sh](../examples/crash-demo/demo-add-symbol-file.sh)
through the Copilot CLI drives real GDB and recovers a symbol-less backtrace with `add-symbol-file`:

![Copilot CLI running the gdb-debugging skill: before/after add-symbol-file](docs/images/copilot-cli-add-symbol-file.png)

The actual GDB text it produced:
```text
########## BEFORE: stripped binary, no symbols ##########
#0  0x0000000000401168 in ?? ()
#1  0x00000000004011af in ?? ()
#2  0x00000000004011e9 in ?? ()
#3  __libc_start_call_main ...

########## AFTER: add-symbol-file cnp.debug 0x401070 ##########
#0  compute_stats (ds=ds@entry=0x7fff186cd450) at crash.c:16
        i = 0
        sum = 0
#1  process (ds=ds@entry=0x7fff186cd450) at crash.c:23
#2  main (argc=<optimized out>, argv=<optimized out>) at crash.c:31
        ds = {count = 5, samples = 0x0}      # <-- root cause: samples is NULL
        avg = <optimized out>
```
Same core, same addresses — but after attaching the split debug file, GDB maps them to functions,
source lines (`crash.c:16`), and locals, exposing the NULL `samples` that caused the SIGSEGV.

## Install

`SKILL.md` is a tool-agnostic format. Copy the whole `gdb-debugging/` folder (keep the structure
intact) into a location your agent scans:

| Tool | Project (team-shared) | Personal (all workspaces) |
|------|-----------------------|---------------------------|
| GitHub Copilot (VS Code + CLI) | `.github/skills/gdb-debugging/` | `~/.copilot/skills/gdb-debugging/` |
| Claude Code / Claude CLI | `.claude/skills/gdb-debugging/` | `~/.claude/skills/gdb-debugging/` |
| Open-convention agents | `.agents/skills/gdb-debugging/` | `~/.agents/skills/gdb-debugging/` |

```powershell
# example: install personally for GitHub Copilot
Copy-Item -Recurse gdb-debugging "$HOME/.copilot/skills/gdb-debugging"
```

**Any other CLI/agent** (Cursor, Aider, a plain chat, …): it's just Markdown + scripts, so point the
agent at it — *"read gdb-debugging/SKILL.md and follow it"* — or run the scripts directly (below).

## Use the scripts standalone

```bash
# One core:
gdb --batch --nx -x scripts/triage.gdb ./app ./core > triage.txt

# A directory of cores:
scripts/triage-core.sh ./app /var/crash ./reports

# Better defaults for every session:
cp scripts/gdbinit-recommended ~/.gdbinit
```

## Structured agent tooling

The dependency-free Python CLI turns the playbook into an interface agents and CI can consume:

```bash
# Validate GDB, target compatibility, build ID, and symbols
python3 scripts/gdb_agent.py doctor ./app --core ./core

# Produce report.json, report.md, and bounded raw evidence
python3 scripts/gdb_agent.py collect ./app ./core --output debug-bundle

# Capture before/after evidence using the same reproduction arguments
python3 scripts/gdb_agent.py verify --expect crash ./app -- bad-input
python3 scripts/gdb_agent.py verify --expect clean ./app -- bad-input

# Get a guided crash, hang, memory, or remote investigation plan
python3 scripts/gdb_agent.py guide crash
```

For adaptive stepping, keep a JSON-lines GDB/MI session alive:

```bash
python3 scripts/gdb_agent.py session ./app -- bad-input
```

```json
{"operation":"breakpoint","location":"main"}
{"operation":"run"}
{"operation":"next"}
{"operation":"locals"}
{"operation":"continue"}
{"operation":"quit"}
```

Resume operations wait until the debuggee stops and return a structured `stop_reason`. The controller
allowlists inspection and execution-control operations; arbitrary console commands and state mutation
are excluded. See [agent automation](references/agent-automation.md) for the full protocol and
[probes](probes/) for reusable investigations.

For CI:

```bash
scripts/ci-triage.sh ./build/app ./debug-bundles -- ./build/native-tests
```

The wrapper returns the native test's exit code while creating a structured bundle for each discovered
core. The included GitHub Actions workflow validates the Python and shell automation itself.

## Scope

Native code with a GDB backend. **Not** for pure Python/Java/JavaScript (use their own debuggers).
Cores contain process memory (secrets/PII) — handle and share them carefully.
