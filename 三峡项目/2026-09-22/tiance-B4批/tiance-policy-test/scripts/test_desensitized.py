# -*- coding: utf-8 -*-
"""脱敏守卫测试：确保技能树内不残留真实 POC 环境信息。

规则：
1) 全树（排除 loop_workspace/backups/__pycache__/.git）不得出现 FORBIDDEN 登记的
   内网环境字面量（真实 POC IP 段、客户标识等）；
2) config.json 的 platform.host / db.host 必须为 $ENV: 占位符（禁止写死真实地址）。

新增敏感标识时在 FORBIDDEN 中登记（用字符串拼接写法，避免本文件被自身扫描命中）。
"""
import json
import os
import re
import unittest

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCLUDE_DIRS = {"loop_workspace", "backups", "__pycache__", ".git"}
SCAN_EXTS = {".py", ".json", ".md", ".js", ".txt"}
SELF_NAME = os.path.basename(__file__)

FORBIDDEN = [
    ("poc-ip-segment", re.compile(r"\b10\.57\.\d{1,3}\.\d{1,3}\b")),
    ("customer-tag", re.compile(re.escape("ccqt" + "gb"), re.IGNORECASE)),
]

# 客户专名（正则见 CUSTOMER_NAME）只允许出现在刻意保留、含客户标识的档案文件里
# （收单 profile 及其人读视图 / 校验器 / 漂移守卫、指向它们的 live 指针段与
# live-only 文档、staging 的 SYNC-NOTE 工作日志）。其余通用/可发布文件命中即
# 视为客户名泄漏。路径均相对 SKILL_ROOT；某目录树不含该文件时不影响扫描，
# 因此 live 与 staging 可共用同一份白名单。新增合法客户档案时在此登记。
# 本文件属于通用发布件，故客户名及其档案文件名片段均以拼接方式构造，避免源码
# 残留连续的客户标识字面量（同 customer-tag 的 "ccqt" + "gb" 处理方式）。
_CN_TOP = "HL" + "B"
_CN_FULL = "Hong" + r"\s*" + "Leong"
_CN_FRAG = "h" + "lb"
CUSTOMER_NAME = re.compile(_CN_TOP + "|" + _CN_FULL, re.IGNORECASE)
CUSTOMER_NAME_ALLOWLIST = {
    "SKILL.md",  # live 版含指向客户收单 profile 的单一来源指针（staging 版此文件已无客户名）
    "SYNC-NOTE.md",  # staging 发布工作日志，记录客户档案被刻意排除在发布外
    "references/%s_acquiring_profile.json" % _CN_FRAG,
    "references/acquiring-%s-profile.md" % _CN_FRAG,
    "references/metric-execute.md",
    "references/metric-pipeline.md",
    "references/test-data-contract.md",
    "references/risk-governance.md",
    "scripts/validate-test-data.py",
    "scripts/test_%s_profile.py" % _CN_FRAG,
    "scripts/test_validate_test_data.py",
}


def iter_scan_files():
    for dirpath, dirnames, filenames in os.walk(SKILL_ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            if name == SELF_NAME:
                continue
            if os.path.splitext(name)[1] in SCAN_EXTS:
                yield os.path.join(dirpath, name)


class TestNoSensitiveContent(unittest.TestCase):
    def test_tree_free_of_sensitive_literals(self):
        hits = []
        for path in iter_scan_files():
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except (UnicodeDecodeError, OSError):
                continue
            for label, pattern in FORBIDDEN:
                if pattern.search(text):
                    hits.append(os.path.relpath(path, SKILL_ROOT) + " -> " + label)
        self.assertEqual([], hits, "技能树中存在敏感字面量，请先脱敏再提交/发布")

    def test_generic_files_free_of_customer_name(self):
        hits = []
        for path in iter_scan_files():
            rel = os.path.relpath(path, SKILL_ROOT)
            if rel in CUSTOMER_NAME_ALLOWLIST:
                continue
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except (UnicodeDecodeError, OSError):
                continue
            if CUSTOMER_NAME.search(text):
                hits.append(rel)
        self.assertEqual(
            [], hits,
            "通用/可发布文件中出现客户专名，请中性化或（若确为客户档案）加入白名单",
        )


class TestConfigExternalized(unittest.TestCase):
    def test_hosts_are_env_placeholders(self):
        cfg_path = os.path.join(SKILL_ROOT, "config.json")
        with open(cfg_path, encoding="utf-8") as fh:
            cfg = json.load(fh)
        self.assertTrue(
            cfg["platform"]["host"].startswith("$ENV:"),
            "platform.host 必须使用 $ENV: 占位符，不得写死真实地址",
        )
        self.assertTrue(
            cfg["db"]["host"].startswith("$ENV:"),
            "db.host 必须使用 $ENV: 占位符，不得写死真实地址",
        )


if __name__ == "__main__":
    unittest.main()
