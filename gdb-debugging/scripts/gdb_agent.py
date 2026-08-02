#!/usr/bin/env python3
"""Safe, structured GDB automation for coding agents and CI."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence


DEFAULT_TIMEOUT = 30.0
MAX_OUTPUT_BYTES = 4 * 1024 * 1024


@dataclass
class Check:
    name: str
    status: str
    detail: str
    remediation: str = ""


def run_command(command: Sequence[str], timeout: float = DEFAULT_TIMEOUT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
        check=False,
    )


def file_description(path: pathlib.Path) -> str:
    file_tool = shutil.which("file")
    if not file_tool:
        return "file utility unavailable"
    result = run_command([file_tool, "-b", str(path)])
    return result.stdout.strip() or result.stderr.strip()


def build_id(path: pathlib.Path) -> str:
    readelf = shutil.which("readelf")
    if not readelf:
        return ""
    result = run_command([readelf, "-n", str(path)])
    match = re.search(r"Build ID:\s*([0-9a-fA-F]+)", result.stdout)
    return match.group(1) if match else ""


def doctor(binary: pathlib.Path, core: pathlib.Path | None, gdb_command: str) -> dict[str, Any]:
    checks: list[Check] = []
    gdb_path = shutil.which(gdb_command)
    checks.append(
        Check(
            "gdb",
            "pass" if gdb_path else "fail",
            gdb_path or f"{gdb_command} not found in PATH",
            "Install GDB or pass --gdb with its executable path." if not gdb_path else "",
        )
    )
    checks.append(
        Check(
            "binary",
            "pass" if binary.is_file() else "fail",
            file_description(binary) if binary.is_file() else f"Not found: {binary}",
            "Provide the exact executable that produced the failure." if not binary.is_file() else "",
        )
    )
    if core:
        checks.append(
            Check(
                "core",
                "pass" if core.is_file() else "fail",
                file_description(core) if core.is_file() else f"Not found: {core}",
                "Provide an existing core file." if not core.is_file() else "",
            )
        )

    if binary.is_file() and gdb_path:
        probe = run_command(
            [gdb_path, "--batch", "--nx", "-ex", "info files", str(binary)] + ([str(core)] if core and core.is_file() else []),
            timeout=DEFAULT_TIMEOUT,
        )
        combined = probe.stdout + probe.stderr
        mismatch = "core file may not match specified executable file" in combined.lower()
        symbols_missing = "no debugging symbols found" in combined.lower()
        checks.append(
            Check(
                "binary-core-match",
                "fail" if mismatch else "pass",
                "GDB reported a binary/core mismatch." if mismatch else "GDB accepted the target files.",
                "Locate the executable from the same build as the core." if mismatch else "",
            )
        )
        checks.append(
            Check(
                "debug-symbols",
                "warn" if symbols_missing else "pass",
                "No embedded debug symbols detected." if symbols_missing else "Debug symbols were not reported missing.",
                "Install matching debuginfo or load a split .debug file." if symbols_missing else "",
            )
        )

    statuses = [check.status for check in checks]
    overall = "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass"
    return {
        "schema_version": 1,
        "overall": overall,
        "host": {"platform": platform.platform(), "python": platform.python_version()},
        "target": {"binary": str(binary), "core": str(core) if core else None, "build_id": build_id(binary) if binary.is_file() else ""},
        "checks": [asdict(check) for check in checks],
    }


TRIAGE_COMMANDS = [
    "set pagination off",
    "set confirm off",
    "set print pretty on",
    "set print frame-arguments all",
    "info program",
    "info sharedlibrary",
    "p $_siginfo",
    "info registers",
    "x/i $pc",
    "bt full",
    "info threads",
    "thread apply all bt",
]


def bounded(text: str) -> tuple[str, bool]:
    encoded = text.encode("utf-8", "replace")
    if len(encoded) <= MAX_OUTPUT_BYTES:
        return text, False
    return encoded[:MAX_OUTPUT_BYTES].decode("utf-8", "replace"), True


def parse_triage(raw: str) -> dict[str, Any]:
    signal_match = re.search(r"Program terminated with signal ([^,\n]+)(?:,\s*([^\n]+))?", raw)
    frame_match = re.search(r"^#0\s+(.+)$", raw, re.MULTILINE)
    fault_match = re.search(r"si_addr\s*=\s*(0x[0-9a-fA-F]+)", raw)
    thread_count = len(re.findall(r"^\s*\*?\s*\d+\s+Thread\s", raw, re.MULTILINE))
    warnings = []
    if "No debugging symbols found" in raw:
        warnings.append("No debugging symbols found; source-level conclusions may be incomplete.")
    if re.search(r"^#\d+\s+0x[0-9a-f]+ in \?\?", raw, re.MULTILINE):
        warnings.append("One or more frames are unsymbolized.")
    return {
        "signal": signal_match.group(1).strip() if signal_match else None,
        "signal_description": signal_match.group(2).strip() if signal_match and signal_match.group(2) else None,
        "fault_address": fault_match.group(1) if fault_match else None,
        "top_frame": frame_match.group(1).strip() if frame_match else None,
        "thread_count": thread_count or None,
        "warnings": warnings,
    }


def markdown_report(report: dict[str, Any]) -> str:
    finding = report["finding"]
    doctor_result = report["doctor"]
    lines = [
        "# GDB Investigation Report",
        "",
        f"Generated: {report['generated_at']}",
        f"Binary: `{report['target']['binary']}`",
        f"Core: `{report['target']['core']}`",
        f"Build ID: `{report['target']['build_id'] or 'unavailable'}`",
        "",
        "## Finding",
        "",
        f"- Signal: `{finding['signal'] or 'unknown'}`",
        f"- Fault address: `{finding['fault_address'] or 'unknown'}`",
        f"- Top frame: `{finding['top_frame'] or 'unknown'}`",
        f"- Threads observed: `{finding['thread_count'] or 'unknown'}`",
        "",
        "## Evidence Quality",
        "",
        f"Environment status: **{doctor_result['overall']}**",
    ]
    lines.extend(f"- {warning}" for warning in finding["warnings"])
    if not finding["warnings"]:
        lines.append("- No symbol-quality warning was detected.")
    lines.extend(
        [
            "",
            "## Next Steps",
            "",
            "1. Inspect the top frame and its arguments in `gdb.txt`.",
            "2. Form one hypothesis tied to an observed value or address.",
            "3. Reproduce under the JSON-lines session and stop at the relevant function.",
            "4. Apply the smallest source fix, rebuild with symbols, and repeat the same scenario.",
            "5. Run the affected tests and compare the before/after stop reason.",
            "",
            "Raw debugger evidence is in `gdb.txt`; machine-readable data is in `report.json`.",
        ]
    )
    return "\n".join(lines) + "\n"


def collect(binary: pathlib.Path, core: pathlib.Path, output: pathlib.Path, gdb_command: str) -> dict[str, Any]:
    health = doctor(binary, core, gdb_command)
    if any(check["status"] == "fail" for check in health["checks"][:3]):
        raise RuntimeError("Environment checks failed; run doctor for details.")
    output.mkdir(parents=True, exist_ok=True)
    command = [gdb_command, "--batch", "--nx"]
    for expression in TRIAGE_COMMANDS:
        command.extend(["-ex", expression])
    command.extend([str(binary), str(core)])
    result = run_command(command, timeout=120.0)
    raw, truncated = bounded(result.stdout + result.stderr)
    (output / "gdb.txt").write_text(raw, encoding="utf-8")
    report = {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target": health["target"],
        "doctor": health,
        "finding": parse_triage(raw),
        "gdb": {"exit_code": result.returncode, "output_truncated": truncated, "commands": TRIAGE_COMMANDS},
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output / "report.md").write_text(markdown_report(report), encoding="utf-8")
    return report


def verify(binary: pathlib.Path, arguments: list[str], expected: str, gdb_command: str, timeout: float) -> dict[str, Any]:
    command = [
        gdb_command,
        "--batch",
        "--nx",
        "-ex",
        "set pagination off",
        "-ex",
        "set confirm off",
        "-ex",
        "run",
        "-ex",
        "bt",
        "--args",
        str(binary),
        *arguments,
    ]
    result = run_command(command, timeout=timeout)
    raw, truncated = bounded(result.stdout + result.stderr)
    signal_match = re.search(r"Program received signal ([^,\n]+)(?:,\s*([^\n]+))?", raw)
    clean_exit = "exited normally" in raw or bool(re.search(r"exited with code 0*\.?$", raw, re.MULTILINE))
    if signal_match:
        outcome = "crash"
    elif clean_exit:
        outcome = "clean"
    else:
        outcome = "incomplete"
    return {
        "schema_version": 1,
        "ok": outcome == expected,
        "expected": expected,
        "outcome": outcome,
        "signal": signal_match.group(1) if signal_match else None,
        "signal_description": signal_match.group(2).strip() if signal_match and signal_match.group(2) else None,
        "gdb_exit_code": result.returncode,
        "output_truncated": truncated,
        "evidence": raw,
    }


GUIDES = {
    "crash": ["Run doctor", "Collect a baseline report", "Inspect frame 0 and its callers", "Break before the fault and reproduce", "Verify the fix with the same input"],
    "hang": ["Attach or snapshot with gcore", "Collect all thread stacks", "Classify blocked versus spinning threads", "Inspect lock owners and waiters", "Verify progress after the fix"],
    "memory": ["Rebuild with ASan when possible", "Stop at the first invalid access", "Watch the corrupted location", "Continue to the writing instruction", "Verify with ASan and regression tests"],
    "remote": ["Verify architecture and connection", "Load matching symbols locally", "Connect without resetting the target", "Set a hardware breakpoint", "Capture target and host evidence"],
}


def guide(symptom: str) -> dict[str, Any]:
    return {"schema_version": 1, "symptom": symptom, "steps": GUIDES[symptom], "approval_required": ["attach", "call", "set variable", "production resume"]}


def mi_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def mi_process_command(gdb_command: str, binary: pathlib.Path, arguments: Iterable[str]) -> list[str]:
    return [gdb_command, "--quiet", "--nx", "--interpreter=mi2", "--args", str(binary), *arguments]


class GdbMiController:
    """Tokenized GDB/MI controller with bounded, stop-aware operations."""

    def __init__(self, gdb_command: str, binary: pathlib.Path, arguments: Iterable[str], timeout: float):
        command = mi_process_command(gdb_command, binary, arguments)
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1)
        self.timeout = timeout
        self.records: queue.Queue[str] = queue.Queue()
        self.token = 0
        self.reader = threading.Thread(target=self._read_output, daemon=True)
        self.reader.start()
        self._drain_until_prompt()
        self.execute("-gdb-set pagination off")
        self.execute("-gdb-set confirm off")

    def _read_output(self) -> None:
        assert self.process.stdout
        for line in self.process.stdout:
            self.records.put(line.rstrip("\r\n"))
        self.records.put("(eof)")

    def _next(self, deadline: float) -> str:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Timed out waiting for GDB/MI output")
        return self.records.get(timeout=remaining)

    def _drain_until_prompt(self) -> None:
        deadline = time.monotonic() + self.timeout
        while True:
            record = self._next(deadline)
            if record == "(gdb)" or record == "(eof)":
                return

    def execute(self, command: str, wait_for_stop: bool = False) -> dict[str, Any]:
        if not self.process.stdin or self.process.poll() is not None:
            raise RuntimeError("GDB process is not running")
        self.token += 1
        token = self.token
        self.process.stdin.write(f"{token}{command}\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + self.timeout
        records: list[str] = []
        result_seen = False
        stopped = False
        while True:
            record = self._next(deadline)
            records.append(record)
            if record.startswith(f"{token}^"):
                result_seen = True
                if "^error" in record:
                    break
            if record.startswith("*stopped"):
                stopped = True
            if result_seen and (not wait_for_stop or stopped):
                break
            if record == "(eof)":
                break
        text, truncated = bounded("\n".join(records))
        stop_record = next((line for line in reversed(records) if line.startswith("*stopped")), None)
        reason_match = re.search(r'reason="([^"]+)"', stop_record or "")
        return {"ok": not any("^error" in line for line in records), "command": command, "stop_reason": reason_match.group(1) if reason_match else None, "records": text.splitlines(), "truncated": truncated}

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                self.execute("-gdb-exit")
            except (RuntimeError, TimeoutError):
                self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()


def operation_to_mi(request: dict[str, Any]) -> tuple[str, bool]:
    operation = request.get("operation")
    mappings = {
        "run": ("-exec-run", True),
        "continue": ("-exec-continue", True),
        "next": ("-exec-next", True),
        "step": ("-exec-step", True),
        "finish": ("-exec-finish", True),
        "frames": ("-stack-list-frames", False),
        "locals": ("-stack-list-variables --all-values", False),
        "threads": ("-thread-info", False),
        "registers": ("-data-list-register-values x", False),
    }
    if operation in mappings:
        return mappings[operation]
    if operation == "breakpoint":
        location = str(request.get("location", ""))
        if not location:
            raise ValueError("breakpoint requires location")
        condition = request.get("condition")
        return f"-break-insert {'-c ' + mi_quote(str(condition)) + ' ' if condition else ''}{mi_quote(location)}", False
    if operation == "watch":
        expression = str(request.get("expression", ""))
        if not expression:
            raise ValueError("watch requires expression")
        return f"-break-watch {mi_quote(expression)}", False
    if operation == "evaluate":
        expression = str(request.get("expression", ""))
        if not expression:
            raise ValueError("evaluate requires expression")
        return f"-data-evaluate-expression {mi_quote(expression)}", False
    raise ValueError(f"Unsupported operation: {operation}")


def session(binary: pathlib.Path, arguments: list[str], gdb_command: str, timeout: float) -> int:
    controller = GdbMiController(gdb_command, binary, arguments, timeout)
    print(json.dumps({"event": "ready", "binary": str(binary)}), flush=True)
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                if request.get("operation") == "quit":
                    print(json.dumps({"ok": True, "event": "exiting"}), flush=True)
                    break
                command, wait_for_stop = operation_to_mi(request)
                print(json.dumps(controller.execute(command, wait_for_stop)), flush=True)
            except (ValueError, json.JSONDecodeError, RuntimeError, TimeoutError) as error:
                print(json.dumps({"ok": False, "error": str(error)}), flush=True)
    finally:
        controller.close()
    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gdb", default=os.environ.get("GDB", "gdb"), help="GDB executable (default: gdb or $GDB)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="Check GDB, target files, symbols, and compatibility")
    doctor_parser.add_argument("binary", type=pathlib.Path)
    doctor_parser.add_argument("--core", type=pathlib.Path)

    collect_parser = subparsers.add_parser("collect", help="Create a structured crash investigation bundle")
    collect_parser.add_argument("binary", type=pathlib.Path)
    collect_parser.add_argument("core", type=pathlib.Path)
    collect_parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("debug-bundle"))

    verify_parser = subparsers.add_parser("verify", help="Run a debuggee and verify a clean exit or reproduced crash")
    verify_parser.add_argument("--expect", choices=("clean", "crash"), default="clean")
    verify_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    verify_parser.add_argument("--output", type=pathlib.Path)
    verify_parser.add_argument("binary", type=pathlib.Path)
    verify_parser.add_argument("arguments", nargs=argparse.REMAINDER)

    guide_parser = subparsers.add_parser("guide", help="Return a symptom-specific investigation workflow")
    guide_parser.add_argument("symptom", choices=sorted(GUIDES))

    session_parser = subparsers.add_parser("session", help="Drive a live debuggee using JSON-lines over GDB/MI")
    session_parser.add_argument("binary", type=pathlib.Path)
    session_parser.add_argument("arguments", nargs=argparse.REMAINDER)
    session_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            result = doctor(args.binary.resolve(), args.core.resolve() if args.core else None, args.gdb)
            print(json.dumps(result, indent=2))
            return 0 if result["overall"] != "fail" else 1
        if args.command == "collect":
            report = collect(args.binary.resolve(), args.core.resolve(), args.output.resolve(), args.gdb)
            print(json.dumps({"ok": True, "output": str(args.output.resolve()), "finding": report["finding"]}, indent=2))
            return 0
        if args.command == "verify":
            result = verify(args.binary.resolve(), args.arguments, args.expect, args.gdb, args.timeout)
            rendered = json.dumps(result, indent=2) + "\n"
            if args.output:
                args.output.write_text(rendered, encoding="utf-8")
            print(rendered, end="")
            return 0 if result["ok"] else 1
        if args.command == "guide":
            print(json.dumps(guide(args.symptom), indent=2))
            return 0
        if args.command == "session":
            return session(args.binary.resolve(), args.arguments, args.gdb, args.timeout)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())