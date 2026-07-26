# Remote & Embedded Debugging

Debug across a wire: `gdbserver`, cross toolchains, serial/KGDB, and JTAG (OpenOCD/QEMU).

## gdbserver (Linux userspace, most common)

**On the target:**
```bash
gdbserver :2345 ./app --args              # listen on TCP 2345, launch app
gdbserver :2345 --attach <PID>            # attach to a running process
gdbserver --multi :2345                   # persistent server for multiple sessions
```

**On the host:**
```bash
gdb ./app                                  # SAME binary (with symbols) as on target
(gdb) target remote <target-ip>:2345       # or: target extended-remote (for --multi)
(gdb) set sysroot /path/to/target/rootfs   # so shared libs resolve
(gdb) continue
```

Over serial instead of TCP:
```bash
# target:
gdbserver /dev/ttyS0 ./app
# host:
(gdb) target remote /dev/ttyS0
(gdb) set serial baud 115200
```

## Cross-Architecture Setup

Use the cross gdb that matches the target ISA, and tell it the arch:

```bash
aarch64-linux-gnu-gdb ./app                # cross gdb for ARM64
# or generic gdb with:
(gdb) set architecture aarch64
(gdb) set gnutarget elf64-littleaarch64
```

Resolve libraries and paths for a cross rootfs:
```gdb
set sysroot /opt/target-rootfs
set solib-search-path /opt/target-rootfs/lib:/opt/target-rootfs/usr/lib
set substitute-path /build/host/path /local/src
```

## QEMU Gdbstub

QEMU exposes a gdb stub — great for kernels and bare-metal:
```bash
qemu-system-x86_64 -s -S ...     # -s = gdbstub on :1234, -S = freeze at start
```
```gdb
gdb vmlinux
(gdb) target remote :1234
(gdb) hbreak start_kernel
(gdb) continue
```
Use `hbreak` (hardware breakpoints) when debugging read-only/flash/kernel code where software
breakpoints can't be written.

## KGDB (Linux kernel over serial)

Boot the target kernel with:
```
kgdboc=ttyS0,115200 kgdbwait
```
Then on the host:
```gdb
gdb vmlinux
(gdb) set serial baud 115200
(gdb) target remote /dev/ttyS0
(gdb) continue
# Trigger a break from the target console: echo g > /proc/sysrq-trigger
```
See [kernel-oops.md](./kernel-oops.md) for decoding once you're stopped.

## JTAG / Bare-Metal (OpenOCD)

For MCUs/SoCs with no OS. OpenOCD (or J-Link GDB server) bridges JTAG/SWD to a gdb port.

**Start the bridge:**
```bash
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg     # exposes :3333
```

**Connect and flash:**
```gdb
arm-none-eabi-gdb firmware.elf
(gdb) target extended-remote :3333
(gdb) monitor reset halt        # 'monitor' forwards raw commands to OpenOCD
(gdb) load                      # flash the ELF to the target
(gdb) monitor reset init
(gdb) hbreak main               # hardware breakpoints (flash!)
(gdb) continue
```

Useful bare-metal moves:
```gdb
monitor reset halt
monitor mww 0x40021018 0x10     # memory-write-word to a peripheral register
x/8xw 0xE000ED00                # read a peripheral/register block (e.g. Cortex-M SCB)
info registers                  # core regs
p/x $sp $pc $lr                 # stack/program/link registers
```

## Semihosting (printf without a UART)
```gdb
monitor arm semihosting enable
```
Then target `printf`/`fputc` route through the debugger.

## Symbol Loading for Loaded Modules / Relocated Code
```gdb
add-symbol-file driver.elf 0x20001000     # give the .text load address
# find the address from the target's linker map or /proc/modules for kernel modules
symbol-file firmware.elf                    # replace symbols entirely
```

## Troubleshooting Remote Sessions
- **`Remote 'g' packet reply is too long`** → arch mismatch; `set architecture` correctly.
- **Backtrace wrong past first frame** → missing frame info; build with `-fno-omit-frame-pointer`,
  or provide `set sysroot`.
- **Breakpoints never hit in flash** → use `hbreak`, not `break` (software bp can't write flash).
- **Libraries `??`** → `set sysroot`/`solib-search-path` to the target rootfs.
- **Connection drops** → serial baud mismatch, or watchdog resetting the target (`monitor reset halt`).

## Checklist
- [ ] Host has the *same* binary + symbols as the target.
- [ ] `set sysroot`/`solib-search-path` point at the target rootfs.
- [ ] Correct cross gdb / `set architecture`.
- [ ] Hardware breakpoints (`hbreak`) used for flash/ROM/kernel.
- [ ] `monitor reset halt` before `load` on bare metal.

## Related
- Kernel decode once stopped → [kernel-oops.md](./kernel-oops.md)
- General commands → [gdb-cheatsheet.md](./gdb-cheatsheet.md)
