# Core Dumps (Post-Mortem Analysis)

Analyze a program that already crashed, using its core file. No live process needed.

## 1. Locate the Core

Cores may not be where you expect. Check the pattern:

```bash
cat /proc/sys/kernel/core_pattern
```

- Starts with `|` → piped to a handler (often `systemd-coredump` or `apport`).
- A path/template → written to disk (`%e`=exe, `%p`=pid, `%t`=time, `%s`=signal).

If cores aren't being written:

```bash
ulimit -c unlimited                     # allow cores in this shell
echo 'core.%e.%p.%t' | sudo tee /proc/sys/kernel/core_pattern   # simple on-disk pattern
```

**systemd-coredump** systems:

```bash
coredumpctl list                        # recent crashes
coredumpctl info <PID|exe>              # metadata, signal, backtrace preview
coredumpctl dump <PID|exe> -o app.core  # extract the raw core
coredumpctl gdb <PID|exe>               # open directly in gdb
coredumpctl debug <PID|exe>             # newer alias
```

## 2. Load It Correctly

```bash
gdb ./app ./core
```

The **binary must match the core exactly**. Verify build IDs:

```bash
readelf -n ./app | grep -A2 'Build ID'
# vs the ID gdb reports on load; a mismatch => wrong binary => garbage backtraces
```

If the binary was deployed stripped, fetch its `debuginfo`:

```bash
# Debian/Ubuntu
sudo apt install <pkg>-dbgsym          # or dbg
# Fedora/RHEL
sudo dnf debuginfo-install <pkg>
# Point gdb at a debug dir if needed
gdb -ex 'set debug-file-directory /usr/lib/debug' ./app ./core
```

## 3. First Look

```gdb
set pagination off
set print pretty on

bt full                 # full backtrace with locals — where and why
info registers          # rip/pc + faulting regs
print $_siginfo         # signal details incl. fault address (si_addr)
info signal SIGSEGV
```

Read the fault address:

```gdb
p/x $_siginfo._sifields._sigfault.si_addr   # the address that faulted
```

- `0x0` or tiny offset → NULL pointer / offset from NULL struct.
- `0xffff...` or garbage → wild/uninitialized pointer or corruption.

## 4. Reconstruct State

```gdb
frame 2                 # move to your code (skip libc)
info args               # arguments to that frame
info locals             # local variables
list                    # source around the crash (needs source path)
p some_struct           # inspect the suspect data
p *ptr                  # deref carefully; may itself be bad
x/16xg $rsp             # raw stack words
```

Multi-threaded core? See every thread:

```gdb
info threads
thread apply all bt
thread apply all bt full   # heavier, but complete
```

## 5. Missing Source?

```gdb
directory /path/to/src              # add source search dir
set substitute-path /build/orig /local/checkout   # relocate build-time paths
info source
```

## 6. Shared Libraries Not Resolved

```gdb
info sharedlibrary                  # look for "No" in the "Syms Read" column
set solib-search-path /path/to/libs
set sysroot /path/to/target/root    # esp. for cross/embedded cores
sharedlibrary                       # re-scan
```

## 6b. Downloading & Attaching Symbols (`??` frames)

If a backtrace shows `??` or `<optimized out>`, symbols are missing. There are three ways to
get them — an agent/CLI can run all of these non-interactively.

### A. Auto-download with debuginfod (easiest)
Modern gdb can fetch matching debug info over the network on demand.

```bash
export DEBUGINFOD_URLS='https://debuginfod.ubuntu.com'    # or your distro/org server
gdb -iex 'set debuginfod enabled on' ./app ./core         # -iex = apply BEFORE loading the core
```
- Use `-iex` (init), **not** `-ex`: enabling it triggers a first-run `y/n` prompt that otherwise
  stalls in batch mode (answered `N`, so nothing downloads).
- Large packages (a whole interpreter/libc) can take a while; the first fetch is the slow one, then
  it's cached under `~/.cache/debuginfod_client/`.
- Distro debuginfod URLs: Ubuntu `https://debuginfod.ubuntu.com`, Fedora `https://debuginfod.fedoraproject.org`,
  Debian `https://debuginfod.debian.net`, or the aggregator `https://debuginfod.elfutils.org`.

### B. Install debug packages locally
```bash
# Debian/Ubuntu
sudo apt install <pkg>-dbgsym          # or libc6-dbg for glibc
# Fedora/RHEL
sudo dnf debuginfo-install <pkg>       # e.g. glibc
gdb -ex 'set debug-file-directory /usr/lib/debug' ./app ./core
```

### C. Manually attach a split debug file — `add-symbol-file`
For a stripped binary/library where you have the separate `.debug`, or a `.so`/kernel module loaded
at a known address. **You must pass the module's load address** (the `.text` VMA).

```gdb
# non-PIE executable: .text VMA is fixed (find it with: readelf -WS bin | awk '/ \.text /{print $4}')
add-symbol-file app.debug 0x401070

# shared library / PIE / kernel module: use the RUNTIME base from the core
info sharedlibrary                      # shows the load address of each .so
add-symbol-file libfoo.so 0x7f....      # <text load addr from the core>
```

Before/after this looks like:
```
BEFORE:  #0 0x401168 in ?? ()             #1 0x4011af in ?? ()
AFTER:   #0 compute_stats (...) at crash.c:16   #1 process (...) at crash.c:23
```
A runnable end-to-end example is in [../../examples/crash-demo/demo-add-symbol-file.sh](../../examples/crash-demo/demo-add-symbol-file.sh)
(builds, strips, then restores symbols with `add-symbol-file`).

### Gotchas
- The debug file's **build-id must match** the binary that produced the core, or symbols will be wrong.
- Split debug files auto-load via `.gnu_debuglink`/build-id if placed under `debug-file-directory`;
  `add-symbol-file` is the manual override when they can't be found or the module is relocated.
- **Kernel** symbols never auto-load into a userspace core — supply `vmlinux` + module symbols
  yourself (see [kernel-oops.md](./kernel-oops.md)).

## 7. Extract Evidence (batch)

```bash
gdb --batch --nx \
  -ex 'set pagination off' \
  -ex 'bt full' \
  -ex 'thread apply all bt' \
  -ex 'info registers' \
  -ex 'info sharedlibrary' \
  ./app ./core > core-triage.txt 2>&1
```

## Checklist
- [ ] Binary build-id matches core.
- [ ] Symbols/debuginfo loaded (`bt` shows names, not `??`).
- [ ] Fault address (`si_addr`) captured and classified.
- [ ] Backtrace of the crashing thread reaches *your* code.
- [ ] All threads inspected if multithreaded.
- [ ] Suspect data structures dumped before drawing conclusions.

## Related
- Corruption patterns → [memory-corruption.md](./memory-corruption.md)
- Threads/hangs → [deadlocks-hangs.md](./deadlocks-hangs.md)
- Commands → [gdb-cheatsheet.md](./gdb-cheatsheet.md)
