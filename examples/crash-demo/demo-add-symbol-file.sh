#!/usr/bin/env bash
# Demo: manually loading symbols into a stripped binary with add-symbol-file.
# Short exe name 'cnp' avoids the 15-char truncation of %e in core filenames.
set -e
cd "$(dirname "$0")"

echo "=== build non-PIE with debug info ==="
gcc -no-pie -Og -g3 -fno-omit-frame-pointer -o cnp crash.c

echo "=== split out debug info, then fully strip the binary ==="
objcopy --only-keep-debug cnp cnp.debug
objcopy --strip-all cnp cnp.stripped

echo "=== regenerate a core from the (stripped) binary run as 'cnp' ==="
ulimit -c unlimited
rm -f /mnt/wslg/dumps/core.cnp* 2>/dev/null || true
cp cnp.stripped cnp
./cnp || true
CORE=$(ls -t /mnt/wslg/dumps/core.cnp* 2>/dev/null | head -1)
echo "CORE=$CORE"

# .text virtual address is column 4 of `readelf -WS`
TEXT_ADDR=$(readelf -WS cnp.stripped | awk '/ \.text /{print "0x"$4}')
echo "TEXT_ADDR=$TEXT_ADDR"

echo
echo "########## BEFORE: stripped binary, no symbols ##########"
gdb --batch -nx -iex 'set debuginfod enabled off' -ex 'bt' \
    cnp.stripped "$CORE" 2>&1 | grep -vE 'New LWP|Thread deb|libthread'

echo
echo "########## AFTER: add-symbol-file restores names + source lines ##########"
gdb --batch -nx -iex 'set debuginfod enabled off' \
    -ex "add-symbol-file cnp.debug $TEXT_ADDR" \
    -ex 'bt full' \
    cnp.stripped "$CORE" 2>&1 | grep -vE 'New LWP|Thread deb|libthread'
