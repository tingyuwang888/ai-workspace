#!/usr/bin/env python3

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from openpyxl import Workbook


ROOT = Path(__file__).parent
VALIDATOR = ROOT / "validate-test-data.py"
WRAPPER = ROOT / "validate-test-data.js"
ENDPOINT = "http://hlb.example.invalid:8000/riskService/trade/riskDecision/acqAuthorization"


def write_workbook(directory, name, payloads):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "测试用例"
    sheet.append(["规则编码"] + [""] * 12 + ["测试数据"])
    for index, payload in enumerate(payloads, start=1):
        sheet.append([f"RULE_{index}"] + [""] * 12 + [json.dumps(payload, ensure_ascii=False)])
    path = directory / name
    workbook.save(path)
    return path


def run(path, *options):
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *options, str(path)],
        text=True,
        capture_output=True,
        check=False,
    )


def run_wrapper(path, *options):
    return subprocess.run(
        ["node", str(WRAPPER), *options, str(path)],
        text=True,
        capture_output=True,
        check=False,
    )


def main():
    canonical = {
        "当前笔接口": ENDPOINT,
        "当前笔": {"bizid": "CURRENT_1", "biztime": "2026-08-07 14:30:00", "transactionamount": 1000, "merchantid": "M1", "transactiontype": "M"},
        "历史数据(构造事件历史)": [{
            "接口地址": ENDPOINT,
            "请求参数": {"bizid": "HISTORY_1", "biztime": "2026-08-07 12:30:00", "transactionamount": 500, "merchantid": "M1", "transactiontype": "M"},
        }],
    }
    compatible = {
        "接口地址": ENDPOINT,
        "触发交易(当前笔)": {"bizid": "CURRENT_2", "biztime": "2026-08-07 14:30:00", "transactionamount": 1000, "merchantid": "M2", "transactiontype": "R"},
        "历史数据(构造事件历史)": [{
            "接口地址": ENDPOINT,
            "批量生成数量": 3,
            "分散天数": 3,
            "请求参数模板": {"bizid": "HISTORY_STATIC", "biztime": "2026-08-06 12:30:00", "transactionamount": 500, "merchantid": "M2", "transactiontype": "R"},
        }],
    }
    ready = json.loads(json.dumps(canonical))
    ready["执行元数据"] = {
        "目标规则": "RULE_1",
        "目标规则集": "target_set",
        "策略编码": "Acq_Authorization",
        "案例类型": "正案例",
        "当前笔计入方式": "excluded",
        "预期当前笔字段": {"transactionamount": 1000},
    }
    with tempfile.TemporaryDirectory(prefix="risk-rule-validator-") as temp:
        directory = Path(temp)
        result = run(write_workbook(directory, "compatible.xlsx", [canonical, compatible]))
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Valid: 2" in result.stdout
        assert "Expanded historical transactions: 4" in result.stdout
        assert "Warnings (2)" in result.stdout

        ready_path = write_workbook(directory, "ready.xlsx", [ready])
        result = run(ready_path, "--execution-ready")
        assert result.returncode == 0, result.stdout + result.stderr
        result = run_wrapper(ready_path, "--execution-ready")
        assert result.returncode == 0, result.stdout + result.stderr

        result = run(write_workbook(directory, "missing.xlsx", [canonical]), "--execution-ready")
        assert result.returncode == 1
        assert "Missing 执行元数据" in result.stdout

        mismatch = json.loads(json.dumps(ready))
        mismatch["执行元数据"]["预期当前笔字段"]["transactionamount"] = 1499
        result = run(write_workbook(directory, "mismatch.xlsx", [mismatch]), "--execution-ready")
        assert result.returncode == 1
        assert "Current field mismatch transactionamount" in result.stdout

        invalid = json.loads(json.dumps(compatible))
        invalid["触发交易(当前笔)"]["transactiontype"] = "INVALID"
        result = run(write_workbook(directory, "invalid.xlsx", [invalid]))
        assert result.returncode == 1
        assert "Invalid enum value INVALID" in result.stdout

    print("validate-test-data compatibility tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
