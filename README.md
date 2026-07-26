# gdb-debugging skill

An on-demand **agent skill** that turns your coding agent (VS Code Copilot, GitHub Copilot CLI, and
other SKILL.md-compatible agents) into a **GDB expert** for triaging and root-causing native crashes:
core dumps, kernel oops/panics, segfaults, memory corruption, deadlocks/hangs, and remote/embedded
targets. Works for **C, C++, Rust, Go, and mixed** binaries.

The skill lives at [.github/skills/gdb-debugging/](.github/skills/gdb-debugging/) — see its
[README](.github/skills/gdb-debugging/README.md) for full docs, install steps, and a real end-to-end
example.

## Quick start

Copy the skill into a location your agent scans, then just describe a crash:

```powershell
# Personal (available in every workspace):
Copy-Item -Recurse .github/skills/gdb-debugging "$HOME/.copilot/skills/gdb-debugging"
```

Or run the bundled scripts directly:

```bash
gdb --batch --nx -x .github/skills/gdb-debugging/scripts/triage.gdb ./app ./core
```

On Windows, Linux cores need Linux GDB — prefix with `wsl` (see the skill README).

## What's inside

- `.github/skills/gdb-debugging/` — the skill (SKILL.md + references + scripts).
- `examples/crash-demo/` — a deliberately buggy program and a demo of `add-symbol-file`.

## License

[MIT](LICENSE).
