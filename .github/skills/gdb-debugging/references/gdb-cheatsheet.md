# GDB Cheatsheet

Fast lookup for commands, flags, and language-specific setup. Anchors are referenced from other files.

## Launching

| Goal | Command |
|------|---------|
| Post-mortem | `gdb ./app ./core` |
| Attach live | `gdb -p <PID>` |
| Launch with args | `gdb --args ./app arg1 arg2` |
| Batch/headless | `gdb --batch --nx -ex '...' ./app ./core` |
| No init files | `gdb --nx` |
| Run a script | `gdb -x script.gdb ./app` |
| TUI (source view) | `gdb -tui ./app` or `Ctrl-x a` inside |

## Execution Control

| Command | Alias | Action |
|---------|-------|--------|
| `run` | `r` | start program |
| `continue` | `c` | resume |
| `next` | `n` | step over |
| `step` | `s` | step into |
| `finish` | | run to return of current frame |
| `until <line>` | `u` | run to a line (skip loops) |
| `stepi`/`nexti` | `si`/`ni` | instruction step |
| `return <val>` | | force return |
| `Ctrl-C` | | interrupt a running program |

## Breakpoints & Watchpoints

| Command | Purpose |
|---------|---------|
| `break f.c:42` / `break func` | line / function bp |
| `break func if cond` | conditional |
| `tbreak` | one-shot |
| `hbreak` | hardware bp (flash/ROM/kernel) |
| `watch v` / `rwatch v` / `awatch v` | write / read / read-write data bp |
| `catch throw` / `catch catch` | C++ exceptions |
| `catch syscall [name]` | syscall |
| `info breakpoints` | list |
| `delete`/`disable`/`enable N` | manage |
| `ignore N count` | skip hits |
| `condition N expr` | add/change condition |
| `commands N` … `end` | auto-run cmds on hit |

## Stack & Frames

| Command | Purpose |
|---------|---------|
| `bt` / `bt full` | backtrace / with locals |
| `bt N` / `bt -N` | top/bottom N frames |
| `frame N` / `up` / `down` | select frame |
| `info frame` | frame details/CFA |
| `info args` / `info locals` | frame data |

## Inspecting Data

| Command | Purpose |
|---------|---------|
| `print expr` (`p`) | evaluate/print |
| `p/x` `p/d` `p/t` `p/c` `p/a` | hex/dec/binary/char/address |
| `p *arr@10` | 10 elements |
| `p arr[2]@5` | slice |
| `ptype v` / `whatis v` | type layout / type |
| `x/16xw addr` | examine memory (16 words hex) |
| `x/i $pc` | disassemble at pc |
| `x/s ptr` | read C string |
| `info registers` / `p $rax` | registers |
| `set var x = 5` | modify variable |
| `call func(args)` | invoke function |
| `display expr` | auto-print each stop |

### `x` format quick key
`x/NFU addr` → N=count, F=format(`x`hex `d`dec `u`uns `s`str `i`instr `c`char `f`float `a`addr `t`bin),
U=unit(`b`yte `h`alf `w`ord `g`iant/8B). Example: `x/32xg $rsp`.

## Threads

| Command | Purpose |
|---------|---------|
| `info threads` | list all |
| `thread N` | switch |
| `thread apply all bt` | every stack |
| `thread apply all bt full` | + locals |
| `set scheduler-locking on` | step one thread only |
| `break func thread N` | thread-specific bp |
| `set non-stop on` | others keep running |

## Signals

| Command | Purpose |
|---------|---------|
| `info signals` | table |
| `handle SIG stop print nopass` | stop, show, don't deliver |
| `catch signal SIGSEGV` | stop at fault moment |
| `p $_siginfo` | signal detail |

## Memory / Disassembly

| Command | Purpose |
|---------|---------|
| `disassemble` / `disassemble func` | disasm |
| `disassemble /s` | interleave source |
| `info registers` / `info all-registers` | regs |
| `info proc mappings` | memory map |
| `maintenance info sections` | sections |
| `dump memory f.bin start end` | save memory |

## Symbols & Source

| Command | Purpose |
|---------|---------|
| `info sharedlibrary` | are syms loaded? |
| `-iex 'set debuginfod enabled on'` | auto-download debug info (use `-iex`, not `-ex`) |
| `set debug-file-directory /usr/lib/debug` | debuginfo dir |
| `add-symbol-file f.elf 0xADDR` | add relocated/split syms at load addr |
| `symbol-file f` | replace syms |
| `directory /src` | add source path |
| `set substitute-path /build /local` | remap build paths |
| `set sysroot /rootfs` | cross/embedded libs |
| `set solib-search-path ...` | lib search |

If backtrace is `??`: wrong binary/build-id, stripped exe (install `-dbgsym`/`debuginfo`), or missing
`set sysroot`. If values are `<optimized out>`: rebuild `-Og -g3`, or read from registers.

### Does gdb auto-load symbols? Three tiers
1. **Your binary** — automatic when built with `-g`/`-g3` and you pass the binary (`gdb ./app core`).
   Stripped? Use a split `.debug` (auto via `.gnu_debuglink`/build-id, or manual `add-symbol-file`).
2. **System libraries (libc, etc.)** — names auto-resolve from the core; **line numbers need debuginfo**.
   Get it via `debuginfod` (`-iex 'set debuginfod enabled on'`, set `DEBUGINFOD_URLS`) or `-dbgsym`/`debuginfo` packages.
3. **Linux kernel** — **never** auto-loads into a userspace core. Supply matching `vmlinux` + `System.map`
   (`linux-image-*-dbg` / `debuginfo-install kernel`); load module symbols with `add-symbol-file`/`mod -s`.

`add-symbol-file` needs the module's **load address**: non-PIE `.text` is fixed
(`readelf -WS bin | awk '/ \.text /{print "0x"$4}'`); PIE/.so/kernel modules use the runtime base from
`info sharedlibrary`. Full walkthrough: [core-dumps.md](./core-dumps.md#6b-downloading--attaching-symbols--frames).

## Reverse / Record

| Command | Purpose |
|---------|---------|
| `record full` / `record stop` | in-gdb recording |
| `reverse-continue` / `reverse-step` / `reverse-next` | backward exec |
| `rr record ./app` / `rr replay` | deterministic replay (external) |

## Convenience

| Command | Purpose |
|---------|---------|
| `set pagination off` | no `--More--` prompts |
| `set print pretty on` | readable structs |
| `set print frame-arguments all` | full args in bt |
| `set confirm off` | no y/n nags |
| `set logging enabled on` | log session to gdb.txt |
| `define name` … `end` | custom command |
| `python ...` / `source x.py` | Python scripting |
| `info line` / `list` | source context |

---

## Language-Specific Setup

### C / C++
```gdb
set print pretty on
set print object on          # show dynamic (most-derived) type
set print vtbl on
# STL pretty-printers ship with GCC's python; usually auto-loaded. If not:
python
import sys; sys.path.insert(0, '/usr/share/gcc/python')
from libstdcxx.v6.printers import register_libstdcxx_printers
register_libstdcxx_printers(None)
end
p mystring                   # shows "text", not internal fields
p myvector                   # shows elements
```
Beware inlining with `-O2`: `step` may skip; `<optimized out>` locals — rebuild `-Og -g3`.

### Rust
Use the wrapper so pretty-printers load:
```bash
rust-gdb ./target/debug/app ./core
```
```gdb
p my_vec                     # Vec<T> displays elements
p my_string                  # String displays text
bt                           # panics pass through core::panicking::panic*
break rust_panic             # stop at panic origin
```
For release binaries, add `debug = true` in `Cargo.toml` `[profile.release]`.

### Go
GDB works but Delve (`dlv`) is usually better for pure Go. GDB shines for cgo/native crashes.
```bash
# Load Go runtime support (path varies by install):
gdb -iex 'add-auto-load-safe-path /usr/local/go/src/runtime/runtime-gdb.py' ./app core
```
```gdb
info goroutines              # provided by runtime-gdb.py
goroutine 18 bt              # backtrace a specific goroutine
p someSlice                  # slice pretty-print
```
Note: Go's scheduler/GC can make stacks confusing; goroutine != OS thread.

### Mixed / cgo / FFI
Load each component's symbols; the crash may cross language boundaries:
```gdb
add-symbol-file libnative.so <text_addr>
info sharedlibrary
thread apply all bt          # see both the Go/Rust and C frames
```

## Minimal `~/.gdbinit` starter
See [../scripts/gdbinit-recommended](../scripts/gdbinit-recommended) for a ready-to-copy file.
