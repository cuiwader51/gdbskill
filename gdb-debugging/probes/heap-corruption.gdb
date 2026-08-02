set pagination off
set confirm off
set print pretty on
set environment MALLOC_CHECK_ 3
set environment MALLOC_PERTURB_ 165
handle SIGSEGV stop print nopass
handle SIGABRT stop print nopass
run
printf "\n===== HEAP FAILURE EVIDENCE =====\n"
print $_siginfo
bt full
thread apply all bt