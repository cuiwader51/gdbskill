set pagination off
set confirm off
set print pretty on
watch -l *(unsigned char *)$probe_address
commands
silent
printf "\n===== WATCHED ADDRESS CHANGED =====\n"
x/16bx $probe_address
x/i $pc
bt
end