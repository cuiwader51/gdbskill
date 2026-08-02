# Driving Real GDB from an Agent / CLI

How an AI agent (Copilot CLI/VS Code) actually runs `gdb` against a binary + core, both
non-interactively (one-shot) and interactively (persistent session). GDB is an interactive REPL, so
choose the mode that fits the task.

## Decision: which mode?

| Situation | Mode |
|-----------|------|
| Extract a crash summary, run a fixed set of commands, CI/fleet | **Batch (one-shot)** |
| Iterative investigation: inspect, decide next command, step, set breakpoints | **Interactive (persistent)** |

Prefer **batch** — it's deterministic, returns full output at once, and needs no TTY. Escalate to an
**interactive** session only when later commands depend on earlier output.

## Prerequisite: is gdb available and can it read the core?

```bash
gdb --version
file ./core            # tells you the target ABI (e.g. "ELF 64-bit ... x86-64")
```

**Cross-OS note:** a Linux core needs **Linux gdb**. On Windows, use WSL:
```bash
wsl gdb --version
wsl gdb --batch -ex 'bt full' ./app ./core
```
Windows-native (MinGW) gdb only reads Windows/MinGW dumps, not Linux ELF cores. macOS uses `lldb`
by default; install gdb via Homebrew if required (and it needs codesigning to attach).

## Mode 1 — Batch (one-shot, non-interactive)

Run gdb, execute commands, exit — capture everything. This is the agent's default.

```bash
# Inline commands:
gdb --batch --nx \
    -ex 'set pagination off' \
    -ex 'bt full' \
    -ex 'thread apply all bt' \
    -ex 'info registers' \
    ./app ./core

# Or source the bundled script (preferred, more complete):
gdb --batch --nx -x ../scripts/triage.gdb ./app ./core
```

Flags that matter for automation:
- `--batch` — run commands then quit; exits non-interactively.
- `--nx` — ignore `~/.gdbinit` (reproducible, no surprise settings).
- `-ex 'CMD'` — run a command; repeatable and ordered.
- `-x FILE` — run a command script (keep complex logic in a `.gdb` file).
- `set pagination off` — **critical**: otherwise gdb blocks on a `--More--` prompt with no TTY.
- `set confirm off` — avoid y/n prompts hanging the run.

The agent runs this with its normal terminal tool, reads stdout/stderr inline, and reasons about the
backtrace. No interaction required.

### Attaching to a live process in batch
```bash
gdb --batch -p <PID> -ex 'thread apply all bt full' -ex 'detach'
# Non-invasive snapshot instead of freezing production:
gcore -o snapshot <PID> && gdb --batch -x ../scripts/triage.gdb ./app snapshot.<PID>
```

## Mode 2 — Interactive (persistent session)

When the next command depends on what the last one showed (e.g. `bt` → pick a frame → `p` a struct).
The agent starts gdb in an **async/background terminal**, then sends one command at a time, reading
output between each.

Recommended startup so output is parseable and never blocks:
```bash
gdb -q -nx \
    -ex 'set pagination off' \
    -ex 'set confirm off' \
    -ex 'set print pretty on' \
    ./app ./core
```

Then the agent drives it like a human, one command per send:
```
bt
frame 3
info locals
p *my_struct
x/16xg $rsp
quit
```

### Agent loop (pseudocode)
```
start gdb in async terminal  ->  wait for the "(gdb)" prompt
send "bt"                     ->  read output up to next "(gdb)"
decide next command from output
send "frame 3" / "p x" ...    ->  read output
... repeat ...
send "quit"                   ->  (answer "y" if asked; or use `-batch`/`set confirm off`)
```

Tips for reliable prompt detection:
- The default prompt is `(gdb) `. You can make it unambiguous:
  `-ex 'set prompt (GDBREADY) '` and wait for that exact marker.
- Always `set pagination off` first, or long backtraces stall waiting for `--More--`.
- Send **one** command per turn and read the result before sending the next.

## Mode 3 — GDB/MI (programmatic, for tooling)

For building a wrapper/tool rather than reading text, use the Machine Interface:
```bash
gdb --interpreter=mi2 ./app ./core
```
MI emits structured records (`^done`, `*stopped`, `~"..."`). Send MI commands like `-stack-list-frames`,
`-thread-info`, `-data-evaluate-expression`. Heavier to parse than text; only worth it for a real
integration. Editors (VS Code C/C++ extension) use MI under the hood.

### Bundled JSON-lines controller

`scripts/gdb_agent.py session` wraps GDB/MI with a small allowlisted protocol. Start it as a persistent
process:

```bash
python3 scripts/gdb_agent.py session ./app -- arg1 arg2
```

Send one JSON object per line and wait for one JSON response before sending the next:

```json
{"operation":"breakpoint","location":"main"}
{"operation":"run"}
{"operation":"next"}
{"operation":"locals"}
{"operation":"evaluate","expression":"request->state"}
{"operation":"watch","expression":"request->state"}
{"operation":"continue"}
{"operation":"quit"}
```

Supported operations are `breakpoint`, `watch`, `run`, `continue`, `next`, `step`, `finish`, `frames`,
`locals`, `threads`, `registers`, and `evaluate`. Resume operations wait for GDB's `*stopped` event and
return `stop_reason`. Arbitrary console commands and debuggee mutation are intentionally unavailable.

## Structured developer commands

Check the environment before spending time on a misleading trace:

```bash
python3 scripts/gdb_agent.py doctor ./app --core ./core
```

Create a bounded evidence bundle containing `report.json`, `report.md`, and `gdb.txt`:

```bash
python3 scripts/gdb_agent.py collect ./app ./core --output debug-bundle
```

Select a guided plan for `crash`, `hang`, `memory`, or `remote`:

```bash
python3 scripts/gdb_agent.py guide memory
```

Reproduce a failure before editing, then prove a clean run after rebuilding:

```bash
python3 scripts/gdb_agent.py verify --expect crash ./app -- failing-input
python3 scripts/gdb_agent.py verify --expect clean --output verification.json ./app -- failing-input
```

These commands emit JSON so an agent or CI job can distinguish evidence from narration.

## CI crash collection

Wrap a native test command and retain its original exit code:

```bash
scripts/ci-triage.sh ./build/app ./debug-bundles -- ./build/native-tests
```

On failure, the wrapper searches three directory levels for conventional core names and creates one
bundle per core. Linux runners must permit core creation; hosted environments using `systemd-coredump`
may require a runner-specific retrieval step before collection.

## Turning a session into a repeatable script

Once you know the commands, capture them so any run is one shot:
```gdb
# investigate.gdb
set pagination off
bt full
frame 3
p *my_struct
p some_global
```
```bash
gdb --batch --nx -x investigate.gdb ./app ./core > findings.txt
```
Commit the `.gdb` script alongside the bug so the analysis is reproducible.

## Logging a session for the record
```gdb
set logging file gdb-session.txt
set logging enabled on
# ... commands ...
set logging enabled off
```

## Common automation pitfalls
- **Hangs with no output** → forgot `set pagination off` (waiting on `--More--`) or a y/n `confirm`.
- **debuginfod does nothing** → enable it with `-iex 'set debuginfod enabled on'` (init, before load) so it
  skips the first-run y/n prompt; set `DEBUGINFOD_URLS`. See [core-dumps.md](./core-dumps.md#6b-downloading--attaching-symbols--frames).
- **`add-symbol-file` frames still `??`** → wrong load address; pass the `.text` VMA (non-PIE fixed, PIE/.so from `info sharedlibrary`).
- **`No such file or directory` for core** → wrong cwd; pass absolute paths.
- **`ptrace: Operation not permitted`** on attach → `sysctl kernel.yama.ptrace_scope=0` or run as root.
- **Backtrace `??`** → wrong binary/build-id or missing debuginfo; fix symbols before analyzing
  (see [gdb-cheatsheet.md](./gdb-cheatsheet.md#symbols--source)).
- **Windows agent, Linux core** → run gdb under `wsl`.
- **Interactive session won't exit** → `quit` may prompt "A debugging session is active... Quit anyway?";
  answer `y`, or start with `set confirm off`, or just use batch mode.

## Related
- One-shot script → [../scripts/triage.gdb](../scripts/triage.gdb)
- Batch a directory of cores → [../scripts/triage-core.sh](../scripts/triage-core.sh)
- Live attach details → [live-debugging.md](./live-debugging.md)
- Command reference → [gdb-cheatsheet.md](./gdb-cheatsheet.md)
