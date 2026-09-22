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
