# Live & Attach Debugging

Debug a running, crashing, or freshly-launched process — plus reverse/record-replay.

## Attach to a Running Process

```bash
gdb -p <PID>                 # attach; process pauses while you're stopped
# or inside gdb:
gdb ./app
(gdb) attach <PID>
```

If you get `ptrace: Operation not permitted`:

```bash
cat /proc/sys/kernel/yama/ptrace_scope     # 0 = allow, 1 = child only, 2/3 = restricted
sudo sysctl -w kernel.yama.ptrace_scope=0  # temporary; or run gdb as root
```

**Production-safe alternative** — snapshot instead of freezing:

```bash
gcore <PID>                  # dump a core without killing the process
gdb ./app core.<PID>         # analyze the copy offline
```

When done, `detach` (leaves the process running) rather than `quit` (may kill it if you `run`-launched it).

## Launch and Stop on Crash

```bash
gdb ./app
(gdb) set args --flag value          # program arguments
(gdb) set environment KEY=val
(gdb) catch signal SIGSEGV           # stop at the moment of the fault (not after)
(gdb) run
# ... crash ...
(gdb) bt full
```

Handle signals deliberately:

```gdb
info signals
handle SIGSEGV stop print nopass     # stop, show, don't deliver to app yet
handle SIGPIPE nostop noprint pass   # ignore noisy signals
```

## Breakpoints, Watchpoints, Catchpoints

```gdb
break file.c:123                     # line
break func                           # function
break func if x > 10                 # conditional
tbreak func                          # one-shot
break file.c:123 thread 3            # only for thread 3

watch var                            # stop when var changes (data breakpoint)
rwatch var                           # on read
awatch var                           # on read or write
watch -l *(int*)0x600d00             # watch a raw address/location

catch throw                          # C++ exception thrown
catch catch                          # exception caught
catch syscall write                  # specific syscall
catch fork / catch exec              # process lifecycle
```

Manage them:

```gdb
info breakpoints
disable 2 / enable 2 / delete 2
ignore 2 100                         # skip next 100 hits
commands 2                           # run cmds automatically when bp 2 hits
> silent
> print var
> continue
> end
```

## Stepping & Navigation

```gdb
next (n)     # over
step (s)     # into
finish       # run until current frame returns
until 130    # run until line 130 (skip loops)
continue (c)
stepi / nexti # instruction-level
frame N / up / down
return <val> # force-return from current frame
```

## Inspect & Manipulate

```gdb
print expr            # p/x hex, p/t binary, p/c char, p/d decimal
print *array@10       # 10 elements
print arr[2]@5        # slice
ptype var             # type layout
whatis var
x/16xw &buf           # examine memory (16 words, hex)
set var x = 42        # change a variable
call func(args)       # invoke a function (careful in prod!)
info functions regex
info variables regex
```

## Multithreading

```gdb
info threads
thread 4                       # switch
thread apply all bt            # all stacks
thread apply all bt full
set scheduler-locking on       # step one thread without others running
break func thread 4
```

## Follow fork/exec

```gdb
set follow-fork-mode child     # or parent
set detach-on-fork off         # keep both under debugger control
set follow-exec-mode new
```

## Reverse Debugging

### Native GDB record
```gdb
record full                    # start recording (slow, in-process)
# ... let it run/crash ...
reverse-continue               # run backwards to previous stop
reverse-step / reverse-next
reverse-finish
record stop
```
Limitations: no recording across most syscalls/`fork`; memory heavy.

### rr (recommended for reliable replay)
```bash
rr record ./app --args         # deterministic recording
rr replay                      # opens a gdb session over the recording
# inside: use normal gdb + reverse-* commands; fully deterministic
rr replay -p <pid>             # target a specific process
```
rr is the go-to for heisenbugs and races — replays are bit-for-bit identical.

## Non-Stop & Async (advanced)
```gdb
set non-stop on                # other threads keep running while one is stopped
set target-async on
```

## Related
- Segfault/corruption specifics → [memory-corruption.md](./memory-corruption.md)
- Hangs/deadlocks → [deadlocks-hangs.md](./deadlocks-hangs.md)
- Remote targets → [remote-embedded.md](./remote-embedded.md)
