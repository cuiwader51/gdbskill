---
name: gdb-debugging
description: 'Debug crashes, core dumps, kernel oops/panics, segfaults, memory corruption, deadlocks, and hangs with GDB like an expert. Covers C, C++, Rust, Go, and mixed binaries; live process attach, post-mortem core analysis, remote/embedded gdbserver + JTAG, reverse debugging, and scripted triage. USE FOR: analyze core dump, debug segfault, backtrace a crash, kernel oops/panic, decode oops, gdb attach to process, corrupted stack, heap corruption, use-after-free, double free, deadlock, hung process, thread apply all bt, remote gdbserver, embedded target debugging, reverse debugging, pretty-print STL, symbol/source not found, strip/optimize -O2 confusing, watchpoints, conditional breakpoints, gdb scripting/Python, ASan/Valgrind interplay. DO NOT USE FOR: writing new features, non-native languages without a gdb backend (pure Python/Java/JS — use their own debuggers).'
argument-hint: 'Describe the crash/dump/symptom, and point to the binary + core (or attach target)'
---

# GDB Debugging (Crashes, Dumps, Oops, and Hangs)

Expert workflows for triaging and root-causing native failures with GDB. Start here, then load the
matching reference for deep procedures.

## When to Use
- A program crashed and you have a **core dump** to analyze post-mortem.
- A process is **live-crashing, hung, or deadlocked** and you can attach.
- A **Linux kernel oops/panic** or `vmcore` needs decoding.
- Segfaults, **stack/heap corruption, use-after-free, double-free**, or wild pointers.
- **Remote/embedded** targets over `gdbserver`, serial, or JTAG.
- You need **scripted/batch triage** across many cores.

## Golden Rules (read first)
1. **Symbols + matching binary are everything.** The core/dump must be paired with the *exact* binary
   (and its debug info) that produced it. Mismatched builds give lies, not backtraces.
2. **Do not recompile before capturing evidence.** Rebuilding can change addresses and destroy the
   ability to map the existing core. Snapshot first, investigate second.
3. **Prefer `-Og`/`-O0 -g3` when reproducible.** With `-O2` and inlining, variables read `<optimized out>`.
   Get symbols before fighting the optimizer.
4. **Reproduce deterministically if you can.** `set follow-fork-mode`, record/replay, and rr turn flaky
   bugs into repeatable ones.
5. **Confirm, don't guess.** Read actual register/memory/frame values before forming a theory.

## Triage Decision Flow

| Symptom / Evidence | Go to |
|--------------------|-------|
| You have a `core` file / crashed post-mortem | [Core dumps](./references/core-dumps.md) |
| Kernel oops, panic, `dmesg` trace, `vmcore` | [Kernel oops & panic](./references/kernel-oops.md) |
| Process is running; attach to crash/inspect | [Live & attach debugging](./references/live-debugging.md) |
| SIGSEGV, corrupted stack, UAF, double-free, wild ptr | [Memory corruption](./references/memory-corruption.md) |
| Process hangs, spins, or deadlocks | [Deadlocks & hangs](./references/deadlocks-hangs.md) |
| Remote board, `gdbserver`, serial, JTAG/OpenOCD | [Remote & embedded](./references/remote-embedded.md) |
| **Actually run/drive gdb from an agent or CLI** | [Agent automation](./references/agent-automation.md) |
| Need a command/flag fast | [GDB cheatsheet](./references/gdb-cheatsheet.md) |

## Universal First 90 Seconds

Whatever the symptom, run this triage skeleton, then branch to the reference above.

```bash
# 1) Confirm what you're loading (build id must match the core/binary)
file ./app
gdb --batch -ex 'info build-id' ./app 2>/dev/null || readelf -n ./app | grep -i build

# 2) Load with the core (post-mortem) OR attach (live)
gdb ./app ./core            # post-mortem
# gdb -p <PID>              # live attach
```

Inside gdb, the opening moves:

```gdb
set pagination off
set print pretty on
set print frame-arguments all

bt full                 # where did it die + locals
info registers          # esp. rip/pc, rsp/sp, and the faulting address
thread apply all bt     # every thread's stack (deadlocks/races)
info sharedlibrary      # are symbols actually loaded?
```

If frames show `??` or `<optimized out>`, fix symbols first — see
[Symbols & source setup](./references/gdb-cheatsheet.md#symbols--source).

## Language-Specific Setup
- **C / C++**: enable STL/pretty-printers; watch for inlining. See [cheatsheet](./references/gdb-cheatsheet.md#c--c).
- **Rust**: use `rust-gdb` wrapper for pretty-printers; panics unwind through `core::panicking`.
  See [cheatsheet](./references/gdb-cheatsheet.md#rust).
- **Go**: use `runtime` support; `info goroutines` requires the Go runtime script.
  Prefer Delve for Go, but GDB works for cgo/crashes. See [cheatsheet](./references/gdb-cheatsheet.md#go).
- **Mixed / cgo / FFI**: symbols may span multiple debug files; load each with `add-symbol-file`.

## Scripted & Batch Triage
For CI, fleets of cores, or repeatable extraction, run GDB headless:

```bash
gdb --batch --nx \
    -ex 'set pagination off' \
    -ex 'bt full' \
    -ex 'thread apply all bt' \
    -ex 'info registers' \
    ./app ./core > triage.txt 2>&1
```

**Driving gdb as an agent/CLI** (start gdb, connect to a core, run commands, read output): use
batch mode above for one-shot analysis, or a persistent interactive session for iterative digging.
Full patterns — including WSL for Linux cores on Windows, prompt handling, and GDB/MI — are in
[agent-automation.md](./references/agent-automation.md).

Reusable helpers live in [scripts/](./scripts/):
- [triage.gdb](./scripts/triage.gdb) — one-shot crash summary (source with `gdb -x`).
- [triage-core.sh](./scripts/triage-core.sh) — batch a directory of cores into reports.
- [gdbinit-recommended](./scripts/gdbinit-recommended) — sane defaults for `~/.gdbinit`.

## Reverse / Record-Replay Debugging
When "how did we get here" matters more than "where are we":
- Native GDB: `record full` then `reverse-continue`, `reverse-step`, `reverse-next`.
- **rr** (`rr record` / `rr replay`) for deterministic replay with real backward execution.
See [live-debugging.md](./references/live-debugging.md#reverse-debugging).

## Common Pitfalls
- **`Cannot access memory at address 0x...`** — usually a bad pointer *or* missing symbols/wrong binary.
- **Backtrace is all `??`** — build id mismatch, stripped binary, or missing `debuginfo` package.
- **Values are `<optimized out>`** — rebuild with `-Og -g3`, or read them from registers/adjacent frames.
- **`ptrace: Operation not permitted`** — `/proc/sys/kernel/yama/ptrace_scope`, or run under sudo/root.
- **No core file appears** — `ulimit -c unlimited`, check `/proc/sys/kernel/core_pattern` (may pipe to systemd-coredump; use `coredumpctl`).

## Safety
- Treat cores as **sensitive**: they contain memory (passwords, PII, keys). Handle/share carefully.
- Attaching to production processes can **pause them**. Prefer `gcore` to snapshot, then debug the copy.
- Never `set`/`call` into a live production process casually — it can execute code and mutate state.
