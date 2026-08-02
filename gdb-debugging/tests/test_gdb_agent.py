import importlib.util
import pathlib
import subprocess
import sys
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "gdb_agent.py"
SPEC = importlib.util.spec_from_file_location("gdb_agent", MODULE_PATH)
assert SPEC and SPEC.loader
gdb_agent = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gdb_agent
SPEC.loader.exec_module(gdb_agent)


class ParseTriageTests(unittest.TestCase):
    def test_extracts_crash_summary(self):
        raw = """Program terminated with signal SIGSEGV, Segmentation fault.
$_siginfo = {si_addr = 0x0}
#0  compute_stats (ds=0x1234) at crash.c:16
* 1 Thread 0x1 (LWP 10)
  2 Thread 0x2 (LWP 11)
"""
        finding = gdb_agent.parse_triage(raw)
        self.assertEqual(finding["signal"], "SIGSEGV")
        self.assertEqual(finding["fault_address"], "0x0")
        self.assertIn("compute_stats", finding["top_frame"])
        self.assertEqual(finding["thread_count"], 2)

    def test_warns_about_unsymbolized_frames(self):
        finding = gdb_agent.parse_triage("#0  0x0000000000401168 in ?? ()\n")
        self.assertIn("unsymbolized", finding["warnings"][0])


class VerifyTests(unittest.TestCase):
    @mock.patch.object(gdb_agent, "run_command")
    def test_classifies_expected_crash(self, run_command):
        run_command.return_value = subprocess.CompletedProcess(
            ["gdb"], 0, "Program received signal SIGABRT, Aborted.\n#0 abort ()", ""
        )
        result = gdb_agent.verify(pathlib.Path("app"), [], "crash", "gdb", 10)
        self.assertTrue(result["ok"])
        self.assertEqual(result["outcome"], "crash")
        self.assertEqual(result["signal"], "SIGABRT")

    @mock.patch.object(gdb_agent, "run_command")
    def test_classifies_clean_exit(self, run_command):
        run_command.return_value = subprocess.CompletedProcess(
            ["gdb"], 0, "[Inferior 1 exited normally]\nNo stack.", ""
        )
        result = gdb_agent.verify(pathlib.Path("app"), [], "clean", "gdb", 10)
        self.assertTrue(result["ok"])
        self.assertEqual(result["outcome"], "clean")


class ControllerContractTests(unittest.TestCase):
    def test_builds_mi_process_command_with_one_executable(self):
        command = gdb_agent.mi_process_command("gdb", pathlib.Path("app"), ["bad-input"])
        self.assertEqual(command, ["gdb", "--quiet", "--nx", "--interpreter=mi2", "--args", "app", "bad-input"])

    def test_maps_resume_operations_to_stop_aware_commands(self):
        command, waits = gdb_agent.operation_to_mi({"operation": "next"})
        self.assertEqual(command, "-exec-next")
        self.assertTrue(waits)

    def test_quotes_breakpoint_location_and_condition(self):
        command, waits = gdb_agent.operation_to_mi(
            {"operation": "breakpoint", "location": "worker.c:42", "condition": "count > 3"}
        )
        self.assertEqual(command, '-break-insert -c "count > 3" "worker.c:42"')
        self.assertFalse(waits)

    def test_rejects_arbitrary_commands(self):
        with self.assertRaisesRegex(ValueError, "Unsupported operation"):
            gdb_agent.operation_to_mi({"operation": "console", "command": "call system(\"sh\")"})

    def test_bounds_large_debugger_output(self):
        text, truncated = gdb_agent.bounded("x" * (gdb_agent.MAX_OUTPUT_BYTES + 1))
        self.assertTrue(truncated)
        self.assertLessEqual(len(text.encode()), gdb_agent.MAX_OUTPUT_BYTES)


class GuideTests(unittest.TestCase):
    def test_all_guides_require_approval_for_mutation(self):
        for symptom in gdb_agent.GUIDES:
            result = gdb_agent.guide(symptom)
            self.assertIn("call", result["approval_required"])
            self.assertGreaterEqual(len(result["steps"]), 5)


if __name__ == "__main__":
    unittest.main()