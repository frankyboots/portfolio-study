"""Fixture: upward subprocess -- series spawning a higher layer's script."""

import subprocess

from subprocess import check_call

# Spawning a higher layer's path (rank 1 from rank 0: upward).
CMD = ["python", "analysis/metrics/report.py"]  # noqa: F841


def run_report() -> None:
    subprocess.run(CMD, check=True)


def run_report_inline() -> None:
    # The literal form the checker must catch in the call arguments.
    subprocess.run(["python", "analysis/metrics/report.py"], check=True)


def run_report_from_import() -> None:
    # The `from subprocess import ...` style must trigger the rule too.
    check_call(["python", "analysis/metrics/report.py"])
