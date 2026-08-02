set pagination off
set confirm off
set print pretty on
set print frame-arguments all
handle SIGSEGV stop print nopass
handle SIGBUS stop print nopass
handle SIGABRT stop print nopass
run
printf "\n===== CRASH EVIDENCE =====\n"
print $_siginfo
info registers
x/i $pc
bt full
thread apply all bt