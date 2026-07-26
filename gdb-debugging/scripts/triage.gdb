# One-shot crash triage. Usage:
#   gdb --batch --nx -x triage.gdb ./app ./core
#   gdb --batch --nx -x triage.gdb -p <PID>
#
# Produces a compact but complete crash summary: registers, fault address,
# full backtrace of the crashing thread, and all-thread backtraces.

set pagination off
set print pretty on
set print frame-arguments all
set print object on

echo \n===== BUILD / TARGET =====\n
info inferiors
info sharedlibrary

echo \n===== SIGNAL / FAULT =====\n
# Signal details (safe even if not signalled).
print $_siginfo
# Faulting address for SIGSEGV/SIGBUS (ignore errors if not applicable).
python
try:
    gdb.execute('p/x $_siginfo._sifields._sigfault.si_addr')
except Exception as e:
    print('si_addr unavailable:', e)
end

echo \n===== REGISTERS =====\n
info registers

echo \n===== FAULTING INSTRUCTION =====\n
x/i $pc

echo \n===== CRASHING THREAD BACKTRACE =====\n
bt full

echo \n===== ALL THREADS =====\n
info threads
thread apply all bt

echo \n===== DONE =====\n
