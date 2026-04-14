from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "tests" / "TEST_REPORT.md"
TEST_CASES_PATH = ROOT / "tests" / "fixtures" / "test_cases.yaml"


def build_command() -> list[str]:
    repo = str(ROOT)
    return [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{repo}:/app",
        "-w",
        "/app",
        "deploy-orion-agent",
        "python",
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-p",
        "test_*.py",
    ]


def run_all_tests() -> tuple[int, str]:
    proc = subprocess.run(build_command(), capture_output=True, text=False)
    stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
    stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
    output = stdout + ("\n" + stderr if stderr else "")
    return proc.returncode, output


def parse_stats(output: str) -> tuple[int, int, int]:
    total = 0
    failures = 0
    errors = 0

    ran_match = re.search(r"Ran\s+(\d+)\s+tests?", output)
    if ran_match:
        total = int(ran_match.group(1))

    failed_match = re.search(r"FAILED\s+\((.*?)\)", output)
    if failed_match:
        detail = failed_match.group(1)
        for part in [item.strip() for item in detail.split(",")]:
            if part.startswith("failures="):
                failures = int(part.split("=", 1)[1])
            if part.startswith("errors="):
                errors = int(part.split("=", 1)[1])

    return total, failures, errors


def compute_scope_coverage() -> tuple[int, int, float]:
    expected_files = [
        ROOT / "tests" / "unit" / "test_parser_runtime_agent.py",
        ROOT / "tests" / "unit" / "test_planner.py",
        ROOT / "tests" / "unit" / "test_tool_registry.py",
        ROOT / "tests" / "unit" / "test_execution_engine_tool_calls.py",
        ROOT / "tests" / "unit" / "test_state_machine.py",
        ROOT / "tests" / "integration" / "test_pipeline_fixture.py",
        ROOT / "tests" / "integration" / "test_pipeline_ddt.py",
        ROOT / "tests" / "test_api_v1.py",
        ROOT / "tests" / "test_agent_service_v3.py",
        ROOT / "tests" / "test_minimax_provider.py",
    ]
    existing = sum(1 for item in expected_files if item.exists())
    rate = (existing / len(expected_files) * 100.0) if expected_files else 0.0
    return existing, len(expected_files), rate


def compute_scenario_coverage() -> tuple[int, int, float]:
    payload = json.loads(TEST_CASES_PATH.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    covered = len(cases)
    target = 20
    rate = (covered / target * 100.0) if target else 0.0
    return covered, target, rate


def write_report(return_code: int, output: str) -> Path:
    total, failures, errors = parse_stats(output)
    passed = max(total - failures - errors, 0)
    pass_rate = (passed / total * 100.0) if total else 0.0
    covered_files, total_files, file_cov_rate = compute_scope_coverage()
    covered_cases, target_cases, case_cov_rate = compute_scenario_coverage()

    report = "\n".join(
        [
            "# AI Agent MVP 测试报告",
            "",
            "## 执行信息",
            "",
            f"- 执行时间：`{dt.datetime.now().isoformat(timespec='seconds')}`",
            f"- 执行方式：`{' '.join(build_command())}`",
            f"- 当前目录：`{ROOT}`",
            f"- 退出码：`{return_code}`",
            "",
            "## 通过率统计",
            "",
            f"- 测试总数：`{total}`",
            f"- 通过数：`{passed}`",
            f"- 失败数：`{failures}`",
            f"- 错误数：`{errors}`",
            f"- 通过率：`{pass_rate:.2f}%`",
            "",
            "## 覆盖率统计",
            "",
            f"- 核心测试文件覆盖率：`{covered_files}/{total_files}` (`{file_cov_rate:.2f}%`)",
            f"- 黑盒业务场景覆盖率：`{covered_cases}/{target_cases}` (`{case_cov_rate:.2f}%`)",
            "",
            "## 说明",
            "",
            "- 这里的“覆盖率”表示当前测试体系对目标测试文件与 20 个业务场景数据集的覆盖情况。",
            "- 当前脚本尚未集成 `coverage.py`，因此没有输出 Python 行覆盖率。",
            "- 如果后续需要行覆盖率，可以在 Docker 镜像中安装 `coverage` 后继续扩展本脚本。",
            "",
            "## 原始测试输出（末尾节选）",
            "",
            "```text",
            output[-5000:] if len(output) > 5000 else output,
            "```",
            "",
        ]
    )
    REPORT_PATH.write_text(report, encoding="utf-8")
    return REPORT_PATH


def main() -> int:
    if os.name == "nt":
        print("Running tests through Docker for Python 3.11 compatibility...")
    code, output = run_all_tests()
    report = write_report(code, output)
    print(f"Report generated: {report}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
