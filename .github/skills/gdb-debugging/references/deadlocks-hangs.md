# Deadlocks & Hangs

The process is alive but stuck: 100% CPU spin, 0% CPU wait, or a classic lock cycle.

## Step 1: Snapshot Without Killing

```bash
gdb -p <PID>          # attach (pauses it)
# or, non-invasive first look:
cat /proc/<PID>/status
top -H -p <PID>        # per-thread CPU: is any thread burning CPU (spin) or all idle (deadlock)?
```

`0% CPU, all threads blocked` → **deadlock / waiting on lock or I/O**.
`100% CPU on one thread` → **infinite loop / livelock**.

## Step 2: Dump Every Thread's Stack

```gdb
set pagination off
info threads
thread apply all bt          # THE key command for hangs
thread apply all bt full     # add locals to see which lock/handle each waits on
```

Read the output looking for:
- Multiple threads in `__lll_lock_wait`, `pthread_mutex_lock`, `futex`, `pthread_cond_wait`.
- Two threads each holding a lock the other wants (classic AB/BA deadlock).

## Step 3: Identify Lock Ownership

For a pthread mutex, the owner TID is stored in the mutex:

```gdb
frame N                       # a thread stuck in pthread_mutex_lock
p *mutex                      # or: p mutex->__data.__owner   (glibc)
# __owner is the TID currently holding it
info threads                  # map that TID (LWP) back to a gdb thread #
```

Now build the wait-for graph:
- Thread 3 waits on mutex M1, whose `__owner` is thread 5.
- Thread 5 waits on mutex M2, whose `__owner` is thread 3 → **cycle = deadlock**.

## Step 4: Spin / Livelock

If a thread is at 100% CPU:

```gdb
thread <spinning-tid>
bt
# sample a few times to see the hot loop:
where
continue    (Ctrl-C)  bt   # repeat 3-4x; the common frame is the loop
finish / until <line>      # step out to confirm the loop condition never changes
p loop_condition_vars      # why doesn't it exit?
```

## Step 5: Condition-Variable Bugs

Threads stuck in `pthread_cond_wait` forever usually mean:
- The signal/broadcast happened **before** the wait (lost wakeup), or
- The predicate was never rechecked (spurious wakeup mishandled).

```gdb
thread apply all bt          # count how many are in cond_wait
p shared_predicate           # is the condition actually true but no one was signaled?
```

## I/O and Syscall Hangs

Blocked in a syscall (read/recv/poll/epoll_wait/futex)?

```gdb
thread apply all bt
p $rax                       # syscall number if stopped in kernel entry
```
Cross-check with:
```bash
cat /proc/<PID>/task/<TID>/stack     # kernel-side stack (needs perms)
strace -p <PID> -f                    # what syscall is it blocked in, and on what fd?
ls -l /proc/<PID>/fd                  # which file/socket/pipe the fd points to
```

## Watchdog Pattern for Intermittent Hangs

Auto-capture a stack dump when it hangs, without babysitting:

```bash
# Attach, dump all stacks, detach — schedule/trigger when the hang is detected:
gdb -p <PID> --batch -ex 'thread apply all bt full' -ex 'detach' > hang-$(date +%s).txt
# Or non-gdb, cheaper:
eu-stack -p <PID>            # elfutils, quick all-thread stacks
pstack <PID>                 # if available
```

## Deadlock Root-Cause Checklist
- [ ] Determined spin (100% CPU) vs block (0% CPU).
- [ ] `thread apply all bt` captured for all threads.
- [ ] Lock owners resolved via `mutex->__data.__owner`.
- [ ] Wait-for graph built; cycle identified (or ruled out).
- [ ] For cond-vars: predicate vs signal ordering checked.
- [ ] For I/O: fd and syscall identified via strace/`/proc`.

## Prevention Notes (for the fix)
- Establish a global lock ordering; always acquire in the same order.
- Use `pthread_mutex_timedlock`/try-lock to fail fast instead of hang.
- Always re-check the predicate in a `while` around `cond_wait`.
- Consider ThreadSanitizer to catch lock-order inversions early:
  `gcc -fsanitize=thread -g app.c`

## Related
- Attaching safely → [live-debugging.md](./live-debugging.md)
- All-thread commands → [gdb-cheatsheet.md](./gdb-cheatsheet.md#threads)
