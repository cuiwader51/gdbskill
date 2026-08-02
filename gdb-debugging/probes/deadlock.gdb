set pagination off
set confirm off
set print pretty on
set print frame-arguments all
printf "\n===== THREAD AND LOCK EVIDENCE =====\n"
info threads
thread apply all bt full