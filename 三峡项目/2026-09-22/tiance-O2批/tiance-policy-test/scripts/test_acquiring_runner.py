#!/usr/bin/env python3
"""Offline unit tests for acquiring_runner (no network, no platform)."""

import datetime
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import acquiring_runner as ar  # noqa: E402


class TestNamespace(unittest.TestCase):
    def test_allocate_token_increments_same_day(self):
        reg = {"used_tokens": [], "used_salts": []}
        day = datetime.date(2026, 9, 10)
        self.assertEqual(ar.allocate_namespace("QW", reg, day), "QW_0910")
        self.assertEqual(ar.allocate_namespace("QW", reg, day), "QW_0910_2")
        self.assertEqual(ar.allocate_namespace("QW", reg, day), "QW_0910_3")

    def test_allocate_salt_unique_and_recorded(self):
        reg = {"used_tokens": [], "used_salts": []}
        first = ar.allocate_salt(reg)
        second = ar.allocate_salt(reg)
        self.assertEqual((first, second), ("900", "901"))
        self.assertEqual(reg["used_salts"], ["900", "901"])


class TestRemapping(unittest.TestCase):
    def test_token_and_digit_replacement(self):
        got = ar.remap_str("600470000000001", ["SKR2_0820"], "QW_0910", {"047": "907"})
        self.assertEqual(got, "609070000000001")
        got = ar.remap_str("SKR2_0820_R53_MERCHANT", ["SKR4_0821_R53", "SKR2_0820"],
                           "QW_0910", None)
        self.assertEqual(got, "QW_0910_R53_MERCHANT")

    def test_non_string_passthrough(self):
        self.assertEqual(ar.remap_str(1000, [], "x", None), 1000)

    def test_rebase_preserves_relative_intervals(self):
        a = {"biztime": "2026-08-20 12:45:00"}
        b = {"biztime": "2026-08-20 14:30:00"}
        dt_a = datetime.datetime.strptime(a["biztime"], "%Y-%m-%d %H:%M:%S")
        offset = datetime.datetime(2026, 9, 10, 16, 0) - dt_a
        ra, rb = ar.rebase_time(a, offset), ar.rebase_time(b, offset)
        self.assertEqual(ra["biztime"], "2026-09-10 16:00:00")
        gap = (datetime.datetime.strptime(rb["biztime"], "%Y-%m-%d %H:%M:%S")
               - datetime.datetime.strptime(ra["biztime"], "%Y-%m-%d %H:%M:%S"))
        self.assertEqual(gap, datetime.timedelta(hours=1, minutes=45))
        self.assertEqual(rb["transactiondate"], rb["biztime"][:10])
        self.assertEqual(rb["transactiontime"], rb["biztime"][11:])


class TestPreflight(unittest.TestCase):
    def test_bizid_conflict_detected(self):
        hist = [{"bizid": "X1"}, {"bizid": "X1"}]
        check = ar.preflight(hist, {"bizid": "X2"}, {}, [], "N", None)
        self.assertFalse(check["bizid_unique"])

    def test_expected_field_compares_after_remap(self):
        # 预期值携带旧 token，重映射后应与实际值一致（行53场景）
        check = ar.preflight([{"bizid": "B1"}], {"bizid": "B2", "merchantid": "N_MERCHANT"},
                             {"merchantid": "OLD_MERCHANT"}, ["OLD"], "N", None)
        self.assertTrue(check["current_field_match"], check["issues"])

    def test_expected_field_mismatch_reported(self):
        check = ar.preflight([{"bizid": "B1"}], {"mcc": "5999"}, {"mcc": "7011"},
                             ["OLD"], "N", None)
        self.assertFalse(check["current_field_match"])


class TestNodePreflight(unittest.TestCase):
    def test_missing_node_aborts(self):
        with mock.patch.object(ar.shutil, "which", return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                ar.preflight_node("classify-execution-result.js")
        self.assertIn("env-missing", str(ctx.exception))

    def test_allow_missing_node_does_not_abort(self):
        with mock.patch.object(ar.shutil, "which", return_value=None):
            ar.preflight_node("classify-execution-result.js", allow_missing=True)

    def test_broken_node_aborts_unless_allowed(self):
        with mock.patch.object(ar.shutil, "which", return_value="/usr/bin/node"), \
                mock.patch.object(ar.subprocess, "check_output", side_effect=OSError("boom")):
            with self.assertRaises(SystemExit):
                ar.preflight_node("classify-execution-result.js")
            ar.preflight_node("classify-execution-result.js", allow_missing=True)

    def test_healthy_node_passes(self):
        with mock.patch.object(ar.shutil, "which", return_value="/usr/bin/node"), \
                mock.patch.object(ar.subprocess, "check_output", return_value=b"v20.0.0\n"):
            ar.preflight_node("classify-execution-result.js")


class TestMetrics(unittest.TestCase):
    RESP = {"data": {"output": {"mingFields": {
        "salaxyzb_m_consume_cnt_5m": 16, "salaxyzb_m_consume_amt_5m": None}}}}

    def test_find_salaxyzb_metric(self):
        self.assertEqual(ar.find_metric(self.RESP, "salaxyzb_m_consume_cnt_5m"), 16)

    def test_find_null_metric_returns_null_token(self):
        self.assertTrue(ar.is_null(ar.find_metric(self.RESP, "salaxyzb_m_consume_amt_5m")))

    def test_find_system_metric_via_regex(self):
        resp = {"data": {"fields": {"C_N_MEROPENDAYS": 45}}}
        self.assertEqual(ar.find_metric(resp, "C_N_MEROPENDAYS"), 45)

    def test_cmp_operators(self):
        self.assertTrue(ar.cmp_op(16, ">=", 15))
        self.assertFalse(ar.cmp_op(4, ">=", 5))
        self.assertTrue(ar.cmp_op(4, "<", 5))
        self.assertFalse(ar.cmp_op(None, ">=", 0))

    def test_evidence_build(self):
        ev = ar.metric_evidence(
            [{"name": "salaxyzb_m_consume_cnt_5m", "operator": ">=", "value": 15},
             {"name": "salaxyzb_m_consume_amt_5m", "operator": ">=", "value": 4999}],
            self.RESP)
        self.assertTrue(ev[0]["satisfied"])
        self.assertFalse(ev[1]["satisfied"])

    def test_diagnosis_null_vs_lag(self):
        codes_null, det = ar.diagnose_metrics(
            [{"name": "a_amt_5m", "actual": None, "satisfied": False}])
        self.assertEqual(codes_null, ["metric_null_env"])
        self.assertEqual(det["null_metrics"], ["a_amt_5m"])
        codes_lag, det2 = ar.diagnose_metrics(
            [{"name": "b_cnt_2h", "actual": 3, "satisfied": False}])
        self.assertEqual(codes_lag, ["suspected_ingest_lag"])
        self.assertEqual(det2["below_plan_metrics"], ["b_cnt_2h"])

    def test_environment_regression_grouping(self):
        results = [
            {"row": 47, "diagnosis": {"null_metrics": ["salaxyzb_m_preauth_travel_amt_2h"]}},
            {"row": 59, "diagnosis": {"null_metrics": ["salaxyzb_m_card_consume_amt_5m"]}},
            {"row": 93, "diagnosis": {"null_metrics": ["salaxyzb_m_x_sum_1d"]}},
            {"row": 71, "diagnosis": {"null_metrics": ["salaxyzb_m_only_cnt_30m"]}},
        ]
        env = ar.environment_regression_cases(results)
        self.assertEqual(env.get("amount"), [47, 59, 93])
        self.assertNotIn("count", env)


class TestDryRunEndToEnd(unittest.TestCase):
    CK = {
        "row": 47, "rule_code": "ACQ_RS3_000014", "case_type": "正案例",
        "target_rule_set_code": "rs_acq_unauthorized", "runId": "SKR2_0820",
        "planned_manifest": {
            "预期当前笔字段": {"mcc": "7011"},
            "预期指标": [{"name": "salaxyzb_m_x_cnt_2h", "operator": ">=", "value": 5}],
        },
        "actual_history_requests": [
            {"endpoint": "http://example.invalid/acq", "request": {
                "bizid": f"SKR2_0820_047_000{i}", "biztime": f"2026-08-20 12:4{i}:00",
                "mcc": "7011", "paymentinstrumentid": "600470000000001"}}
            for i in (1, 2)],
        "actual_current_request": {
            "bizid": "SKR2_0820_047_9001", "biztime": "2026-08-20 14:30:00",
            "mcc": "7011", "paymentinstrumentid": "600470000000001"},
    }

    def test_dry_run_allocates_namespace_and_plans_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            ck = tmp / "ck.json"
            ck.write_text(json.dumps(self.CK, ensure_ascii=False), encoding="utf-8")
            rc = ar.main(["--checkpoint", str(ck), "--output", str(tmp / "run"),
                          "--registry", str(tmp / "reg.json"), "--dry-run"])
            self.assertEqual(rc, 0)
            reg = json.loads((tmp / "reg.json").read_text(encoding="utf-8"))
            self.assertEqual(reg["used_tokens"], [f"QW_{datetime.date.today():%m%d}"])
            self.assertEqual(reg["used_salts"], ["900"])
            planned = json.loads(
                (tmp / "run" / "row047" / "planned_requests.json").read_text(encoding="utf-8"))
            reqs = planned["requests"]
            self.assertEqual(len(reqs), 3)  # 2 history + current
            self.assertTrue(all("SKR2_0820" not in json.dumps(r) for r in reqs))
            self.assertTrue(all("600470000000001" not in json.dumps(r) for r in reqs))
            self.assertIn(reg["used_tokens"][0], json.dumps(reqs))
            biz_times = [r["biztime"] for r in reqs[:2]]
            self.assertLess(biz_times[0], reqs[2]["biztime"])  # 历史早于当前


class TestMakeCaseKey(unittest.TestCase):
    def test_row_and_rule_format(self):
        self.assertEqual(ar.make_case_key(47, "ACQ_RS3_000014"), "acq-047-ACQ_RS3_000014")

    def test_missing_identity_degrades_to_index(self):
        self.assertEqual(ar.make_case_key(None, None, 3), "acq-misc003")
        self.assertEqual(ar.make_case_key(-1, None), "acq-misc000")
        self.assertEqual(ar.make_case_key(5, None, 7), "acq-misc007")


class TestSummaryArtifact(unittest.TestCase):
    def test_dry_run_summary_carries_governed_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            ck = tmp / "ck.json"
            ck.write_text(json.dumps(TestDryRunEndToEnd.CK, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(
                ar.main(["--checkpoint", str(ck), "--output", str(tmp / "run"),
                         "--registry", str(tmp / "reg.json"), "--dry-run"]), 0)
            summary = json.loads((tmp / "run" / "runner_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["schemaVersion"], "1.0")
            self.assertEqual(summary["runId"], "acq-run")
            self.assertEqual(summary["planned"], 1)
            self.assertEqual(summary["counts"]["通过"], 0)  # dry-run 无 classification
            self.assertEqual(summary["cases"][0]["caseKey"], "acq-047-ACQ_RS3_000014")
            self.assertTrue(summary["cases"][0]["namespace"].startswith("QW_"))


if __name__ == "__main__":
    unittest.main()
