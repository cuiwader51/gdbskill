# Reusable GDB Probes

Run a probe with `gdb --nx -x probes/<name>.gdb --args ./app <args>`. These scripts collect evidence
without calling debuggee functions or modifying its memory.

| Probe | Use |
|---|---|
| `crash.gdb` | Stop on fatal signals and collect the failing state |
| `deadlock.gdb` | Inspect every thread in an attached, stopped process |
| `heap-corruption.gdb` | Enable libc heap checks and stop at the first fatal signal |
| `watch-write.gdb` | Find the instruction that changes a known address |

The watchpoint probe needs a convenience variable set before sourcing it:

```gdb
set $probe_address = 0x7fffffffdc20
source probes/watch-write.gdb
continue
```

Prefer a typed watch expression entered directly in GDB when symbols are available, for example
`watch request->state`.