# Memory Corruption (SIGSEGV, UAF, Overflows)

Root-cause segfaults, stack/heap corruption, use-after-free, double-free, and wild pointers.

## Step 1: Classify the Fault Address

```gdb
p/x $_siginfo._sifields._sigfault.si_addr   # the address that faulted
info registers
x/i $pc                                     # the faulting instruction
```

| Fault address | Likely cause |
|---------------|--------------|
| `0x0` | NULL pointer dereference |
| Small (`0x8`, `0x20`…) | NULL + struct field offset (`ptr->field` on NULL) |
| `0xffffffffffffffff` / huge | uninitialized/wild pointer, sign-extended `-1` |
| `0x7f...` mid-range | valid-looking but freed/dangling heap/stack |
| Repeated byte pattern | poisoned freed memory (see signatures below) |

## Step 2: Read the Faulting Instruction

```gdb
x/i $pc                 # e.g. mov (%rax),%rbx  => it dereferenced %rax
p/x $rax                # was %rax the bad pointer?
```
Map the register in the instruction back to a source variable via `info locals`/`info args` and `list`.

## Poison / Sentinel Signatures (memorize these)

| Bytes | Meaning |
|-------|---------|
| `0x6b6b6b6b` (`kkkk`) | SLUB freed memory poison (kernel) |
| `0x5a5a5a5a` (`ZZZZ`) | SLAB uninitialized poison |
| `0xdeadbeef` | classic freed/sentinel marker |
| `0xdeadc0de` / `0xdead...` | freed markers |
| `0xcccccccc` | MSVC uninitialized stack |
| `0xcdcdcdcd` | MSVC uninitialized heap |
| `0xfeeefeee` | MSVC freed heap |
| `0xbaadf00d` | uninitialized (LocalAlloc) |
| `0xa5a5a5a5` | common uninitialized fill |

Seeing these in a pointer/arg means **use-after-free** or **uninitialized read**.

## Stack Corruption

Symptoms: garbage/`??` backtrace, `Backtrace stopped: previous frame inner to this frame`, crash in
`__stack_chk_fail`.

```gdb
bt                              # if it's nonsense, the stack is smashed
info frame                      # frame/CFA sanity
x/32xg $rsp                     # dump raw stack, look for overwritten return addrs
p $rip                          # is the return target sane code?
```

- Crash in `__stack_chk_fail` → **stack canary tripped** = buffer overflow on the stack.
- Return address overwritten with ASCII (`0x4141...` = `AAAA`) → classic overflow.

Reproduce with tooling — far faster than manual gdb:
```bash
gcc -g -O0 -fsanitize=address -fno-omit-frame-pointer app.c   # ASan pinpoints the exact overflow
gcc -g -O0 -fsanitize=undefined app.c                          # UBSan for OOB/overflow/UB
```

## Heap Corruption / Double-Free / UAF

glibc will often abort with a diagnostic:
- `free(): double free detected in tcache 2`
- `malloc(): corrupted top size`
- `free(): invalid pointer`

```gdb
catch signal SIGABRT            # stop at the glibc abort
run
bt                              # walk up past malloc/free internals to your call site
frame N                         # your code
p ptr                           # the pointer being freed
```

Find where a pointer was freed vs used:
```gdb
watch ptr                       # catch when the pointer value changes
# or set a breakpoint on free and log:
break free if $rdi == <ptr_value>
```

Best tools for heap bugs:
```bash
valgrind --leak-check=full --track-origins=yes ./app   # UAF, invalid free, leaks, uninit reads
gcc -fsanitize=address ./app                            # ASan: fast UAF/heap-overflow with stacks
export MALLOC_CHECK_=3                                  # glibc extra checks
export MALLOC_PERTURB_=42                               # fill freed mem to surface UAF
```

## Wild / Uninitialized Pointers

```gdb
p ptr                           # obviously bogus value?
info locals                     # is it declared but never assigned near the crash?
```
Catch first bad write with a hardware watchpoint on the pointer variable, then step forward.

## Buffer Over-read/Over-write Localization

```gdb
watch -l buf[63]                # trip when the byte just past the array is touched
rwatch buf[len]                 # catch out-of-bounds reads
```

## Finding "Who Wrote This?"

Hardware watchpoint on the corrupted location, then let it run backward or forward:
```gdb
watch *(int*)0xADDRESS
continue          # stops on the write that corrupts it
bt                # the culprit's stack
# or with rr/record: reverse-continue to the write
```

## Checklist
- [ ] Fault address classified (NULL vs offset vs poison vs wild).
- [ ] Faulting instruction + register identified and mapped to source.
- [ ] Poison signatures checked (UAF/uninit?).
- [ ] Stack integrity verified (canary? overwritten return?).
- [ ] Reproduced under ASan/Valgrind for an exact allocation/free stack.
- [ ] Watchpoint used to catch the corrupting write.

## Related
- Post-mortem loading → [core-dumps.md](./core-dumps.md)
- Reverse execution to the write → [live-debugging.md](./live-debugging.md#reverse-debugging)
