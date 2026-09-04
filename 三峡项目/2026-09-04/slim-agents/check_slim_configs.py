# -*- coding: utf-8 -*-
"""精简运行版硬门禁自检：16 项通用门禁 + 角色专属门禁 + 行数目标 + 版本钉。"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

COMMON_GATES = [
    ("版本钉+blocked", [r"runtime-contract-v3", r"blocked"]),
    ("身份与禁止事项", [r"禁止"]),
    ("taskMode 边界", [r"taskMode"]),
    ("任务身份三件套", [r"taskId", r"attemptId", r"sessionId"]),
    ("expectedAgentId/reuseSession", [r"expectedAgentId", r"reuseSession"]),
    ("五状态", [r"inconclusive"]),
    ("completed 硬门禁", [r"completed"]),
    ("401 判定", [r"401"]),
    ("Fixture cleanup 责任", [r"cleanup"]),
    ("runStatus=2 不等于通过", [r"runStatus"]),
    ("waiting_for_human", [r"waiting_for_human"]),
    ("事件驱动等待", [r"事件驱动|禁止轮询|轮询"]),
    ("超时与晚到结果", [r"晚到|超时"]),
    ("Manifest/指纹/去重", [r"指纹", r"去重|duplicate"]),
    ("Worker 完成即退出", [r"立即结束|立即退出|完成即退出"]),
    ("安全与凭据限制", [r"TIANCE_DB_PASS"]),
]

ROLE_GATES = {
    "总控": [
        ("Assignment 含五状态计数与覆盖率路径", [r"Assignment", r"passed", r"覆盖率"]),
        ("迭代上限单轮=1", [r"max_iterations"]),
        ("GoalSpec 禁重发/只读查询", [r"loop_set_goalspec|GoalSpec"]),
    ],
    "用例": [
        ("generatedCaseCount 为准", [r"generatedCaseCount"]),
        ("四模块覆盖", [r"四模块|byModule"]),
        ("excluded 显式列原因", [r"excluded"]),
        ("不生成 Mock 异常用例", [r"异常用例|错误码"]),
    ],
    "执行": [
        ("每10条分段", [r"10\s*条|分段"]),
        ("fixtureRunId 每轮新建", [r"fixtureRunId"]),
        ("resume 限制", [r"resume"]),
        ("submitted=有效UUID", [r"UUID"]),
    ],
    "审计": [
        ("securityViolations", [r"securityViolations"]),
        ("convergeReady 判定", [r"convergeReady"]),
        ("计数等式复核", [r"counting_inconsistent|五状态之和"]),
    ],
}

LINE_RANGES = {"总控": (300, 450), "用例": (200, 300), "执行": (400, 600), "审计": (200, 300)}

FILES = {
    "总控": "天策策略测试总控_AGENTS_V4_slim.md",
    "用例": "天策测试用例助手_AGENTS_V3_slim.md",
    "执行": "天策策略执行助手_AGENTS_V3_slim.md",
    "审计": "天策测试报告审计助手_AGENTS_V3_slim.md",
}


def main():
    failures = []
    for role, name in FILES.items():
        path = HERE / name
        if not path.exists():
            failures.append(f"{role}: 文件缺失 {name}")
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        lo, hi = LINE_RANGES[role]
        if not (lo <= len(lines) <= hi):
            failures.append(f"{role}: 行数 {len(lines)} 超出目标 {lo}-{hi}")
        for gate, patterns in COMMON_GATES + ROLE_GATES[role]:
            missing = [p for p in patterns if not re.search(p, text)]
            if missing:
                failures.append(f"{role}: 门禁[{gate}] 缺 {missing}")
        # verify_commands 不得作为可用字段出现：出现即必须伴随省略/禁止语义
        for i, ln in enumerate(lines, 1):
            if "verify_commands" in ln and not re.search(r"省略|禁止|不得", ln):
                failures.append(f"{role}: L{i} verify_commands 未伴随省略语义")
        print(f"[OK] {role}: {len(lines)} 行, 通用{len(COMMON_GATES)}+专属{len(ROLE_GATES[role])}门禁全中"
              if not any(f.startswith(role + ':') for f in failures) else f"[CHECK] {role}: 见失败清单")
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print("\nSELF_CHECK_GREEN: 四份精简版 16 通用门禁+角色门禁+行数+版本钉 全部通过")


if __name__ == "__main__":
    main()
