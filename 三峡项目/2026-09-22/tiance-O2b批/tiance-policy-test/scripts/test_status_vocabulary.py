#!/usr/bin/env python3
"""Five-state vocabulary drift guard.

Asserts the governance contract vocabulary has one machine-readable source
(references/governance.schema.json) and that every consumer agrees with it:
governance.py STATUSES, the js classifier literals, the runner fallback and
diagnosis codes, plus byte-identity of the shared js classifier copy that also
lives in the generic risk-rule-testcase-execute family.
"""

import json
import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import governance  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
SCHEMA = HERE.parent / "references" / "governance.schema.json"
JS = HERE / "classify-execution-result.js"
GENERIC_JS = (pathlib.Path.home() /
              ".agents/skills/risk-rule-testcase-execute/scripts/classify-execution-result.js")


class TestFiveStateVocabulary(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    def test_governance_statuses_match_schema(self):
        self.assertEqual(governance.STATUSES, tuple(self.schema["fiveState"]["enum"]))

    def test_js_classifier_contains_all_statuses(self):
        src = JS.read_text(encoding="utf-8")
        for status in governance.STATUSES:
            self.assertIn(f"'{status}'", src, f"js classifier missing literal {status}")

    def test_governance_reason_codes_registered(self):
        src = (HERE / "governance.py").read_text(encoding="utf-8")
        codes = set(re.findall(r'verdict\("[^"]+", "([a-z_]+)"', src))
        registered = set(self.schema["reasonCodes"]["platform"])
        self.assertTrue(codes <= registered, f"unregistered reason codes: {codes - registered}")

    def test_acquiring_reason_codes_registered(self):
        src = (HERE / "acquiring_runner.py").read_text(encoding="utf-8")
        registered = set(self.schema["reasonCodes"]["acquiring"])
        for code in ("metric_null_env", "suspected_ingest_lag", "environment_regression",
                     "preflight_failed", "runner_error", "classifier_error",
                     "checkpoint_design_mismatch"):
            self.assertIn(code, src, f"runner lost diagnosis code {code}")
            self.assertIn(code, registered, f"unregistered acquiring code {code}")

    def test_runner_fallback_status_in_vocabulary(self):
        src = (HERE / "acquiring_runner.py").read_text(encoding="utf-8")
        self.assertIn('"status": "执行阻塞"', src)
        self.assertIn("执行阻塞", governance.STATUSES)

    def test_generic_family_js_copy_identical(self):
        if not GENERIC_JS.exists():
            self.skipTest("generic family not installed here")
        self.assertEqual(JS.read_bytes(), GENERIC_JS.read_bytes(),
                         "tiance and generic-family classifier copies diverged")


if __name__ == "__main__":
    unittest.main()
