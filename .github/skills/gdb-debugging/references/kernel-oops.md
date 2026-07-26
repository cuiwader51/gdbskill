# Kernel Oops & Panic

Decode Linux kernel crashes: oops messages, panics, and full `vmcore` post-mortems.

> GDB debugs the *kernel*, not a userspace process here. Two modes:
> **(A)** read/decode an oops text trace, **(B)** open a `vmcore` with the matching `vmlinux`.

## A. Decode an Oops / Panic Trace (fast path)

You often only have `dmesg`/serial output. Extract the crash site without a full dump.

### 1. Identify the faulting instruction
The oops shows `RIP: 0010:function_name+0xNN/0xMM`. That `+0xNN` is the byte offset into the function.

```bash
# Resolve an address/symbol+offset to a source line:
addr2line -e vmlinux -f -i <address>
# Or decode symbol+offset against the built kernel:
./scripts/faddr2line vmlinux 'function_name+0xNN/0xMM'   # in kernel source tree
```

### 2. Decode the register/code dump
The `Code:` line is raw bytes around RIP. Turn it into instructions:

```bash
# From a saved dmesg containing the "Code:" line:
scripts/decodecode < oops.txt        # in the kernel source tree
```
This marks the exact faulting instruction with `<--`.

### 3. Read the call trace
The `Call Trace:` lists return addresses. Entries with `?` are unreliable (stale stack). Map the
reliable frames with `faddr2line`/`addr2line` to get file:line for each.

### 4. Classify the fault
- `BUG: unable to handle kernel NULL pointer dereference` → NULL deref; check the offset for which
  struct field (`function+0xNN` → field at that offset).
- `general protection fault` → often a poisoned/freed pointer (`0x6b6b...` SLUB poison, `0xdead...`).
- `Oops: 0002` (write) vs `0000` (read) — the error code bits tell read/write, user/kernel, present.

## B. Full vmcore Analysis

### 1. Get the pieces
You need a **`vmcore`** (from kdump) and a **`vmlinux` with debug symbols** matching the exact kernel.

```bash
# vmcores from kdump usually land here:
ls /var/crash/*/vmcore
# Matching debug kernel:
#   Fedora/RHEL:  sudo dnf debuginfo-install kernel-<version>
#                 -> /usr/lib/debug/lib/modules/<ver>/vmlinux
#   Debian/Ubuntu: linux-image-<ver>-dbg
uname -r
```

### 2a. crash utility (recommended for kernels)
`crash` wraps GDB with kernel awareness — usually far easier than raw gdb:

```bash
crash /usr/lib/debug/lib/modules/$(uname -r)/vmlinux /var/crash/.../vmcore
```

Inside `crash`:
```
bt                 # backtrace of the panicking task
bt -a              # backtrace ALL cpus/tasks
ps                 # process list at crash time
log                # the dmesg buffer (the oops itself)
dmesg              # same
foreach bt         # every task's stack
dev                # device state
kmem -i            # memory usage
struct task_struct <addr>   # inspect kernel structures
mod -S             # load module symbols
```

### 2b. Raw GDB on vmcore
```bash
gdb vmlinux vmcore          # limited; crash is preferred, but works for symbol/line lookups
```

### 3. Live kernel debugging (optional)
- **KGDB** over serial/console: boot with `kgdboc=ttyS0,115200 kgdbwait`, then
  `gdb vmlinux` + `target remote /dev/ttyS0`. See [remote-embedded.md](./remote-embedded.md).
- **QEMU**: `qemu -s -S` exposes a gdbstub on `:1234`; `target remote :1234`.

## Module Symbols
If the crash is in a driver/module, load its symbols:
```
# In crash:
mod -s <module_name> /path/to/module.ko
# In raw gdb, compute .text base from /sys and:
add-symbol-file module.ko <text_addr>
```

## Common Root Causes
- **NULL deref in a struct** — offset in `func+0xNN` pinpoints the field.
- **Use-after-free** — SLUB poison values (`0x6b6b6b6b`, `0x6b...`) in registers/args.
- **Stack overflow** — corrupted/`0x00` return frames, `Thread overran stack` messages.
- **Race / locking** — `bt -a` shows two CPUs in the same subsystem; check spinlock owners.
- **Bad DMA / hardware** — faults at physical-ish addresses, `Machine Check` events.

## Checklist
- [ ] `vmlinux`/`System.map` matches the crashed kernel (`uname -r`).
- [ ] Faulting RIP resolved to file:line (`faddr2line`/`addr2line`).
- [ ] `Code:` decoded to find the exact instruction.
- [ ] Reliable call-trace frames mapped (ignore `?` entries).
- [ ] Module symbols loaded if crash is in a driver.
- [ ] Error code (read/write, user/kernel) classified.

## Related
- Remote/KGDB/QEMU → [remote-embedded.md](./remote-embedded.md)
- Corruption signatures → [memory-corruption.md](./memory-corruption.md)
