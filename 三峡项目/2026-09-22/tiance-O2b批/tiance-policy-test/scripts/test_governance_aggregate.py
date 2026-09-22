#!/usr/bin/env python3
"""O2: acquiring-chain aggregate scoring -> governed-results isomorphism.

Covers the five-state vocabulary single source across both modules, counts and
rates isomorphic to the platform-chain classify output, caseKey assignment and
clash guards, the merged single-reasonCode priority, environment-regression
passthrough, and the aggregate report feeding the existing validate-rerun
front door (both chains stay mutually exclusive; this path never re-judges).
"""

import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import acquiring_runner as ar  # noqa: E402
import governance as gv  # noqa: E402

SCHEMA = json.loads((HERE.parent / "references" / "governance.schema.json").read_text(encoding="utf-8"))


def record(row, rule, status, codes=(), evidence=(), null_metrics=()):
    return {"row": row, "rule_code": rule, "case_type": "正案例",
            "target_rule_set": "rs_acq_unauthorized", "namespace": "QW_0922",
            "classification": {"status": status, "evidence": list(evidence),
                               "target_rule_hit": status == "通过",
                               "target_rule_set_executed": True},
            "metric_evidence": [],
            "diagnosis": {"reason_codes": list(codes),
                          "null_metrics": list(null_metrics),
                          "below_plan_metrics": []}}


class TestVocabularySingleSource(unittest.TestCase):
    def test_runner_governance_and_schema_agree(self):
        enum = tuple(SCHEMA["fiveState"]["enum"])
        self.assertEqual(gv.STATUSES, enum)
        self.assertEqual(ar.STATUSES, enum)

    def test_preflight_failed_registered(self):
        self.assertIn("preflight_failed", SCHEMA["reasonCodes"]["acquiring"])


class TestCountsAndRates(unittest.TestCase):
    def setUp(self):
        self.report = gv.aggregate_acquiring([
            record(1, "R1", "通过"),
            record(2, "R2", "通过"),
            record(3, "R3", "失败", codes=["suspected_ingest_lag"]),
            record(4, "R4", "执行阻塞", codes=["metric_null_env"]),
        ], "acq-runA")

    def test_isomorphic_fields(self):
        for field in ("schemaVersion", "runId", "cases", "counts", "planned",
                      "coverageGaps", "strictCompletionRate", "validExecutionPassRate",
                      "fullSuccess", "environmentRegression"):
            self.assertIn(field, self.report)

    def test_rates(self):
        self.assertEqual(self.report["counts"]["通过"], 2)
        self.assertEqual(self.report["planned"], 4)
        self.assertEqual(self.report["strictCompletionRate"], 0.5)
        self.assertAlmostEqual(self.report["validExecutionPassRate"], 2 / 3)
        self.assertFalse(self.report["fullSuccess"])
        self.assertEqual(self.report["coverageGaps"], [])

    def test_all_pass(self):
        report = gv.aggregate_acquiring([record(1, "R1", "通过")], "acq-runB")
        self.assertTrue(report["fullSuccess"])
        self.assertEqual(report["strictCompletionRate"], 1.0)

    def test_zero_denominator_pass_rate_is_none(self):
        report = gv.aggregate_acquiring(
            [record(1, "R1", "执行阻塞", codes=["metric_null_env"])], "acq-runC")
        self.assertIsNone(report["validExecutionPassRate"])
        self.assertEqual(report["strictCompletionRate"], 0.0)


class TestInputGuards(unittest.TestCase):
    def test_empty_or_non_list(self):
        with self.assertRaises(ValueError):
            gv.aggregate_acquiring([], "acq-x")
        with self.assertRaises(ValueError):
            gv.aggregate_acquiring({"row": 1}, "acq-x")

    def test_missing_run_id(self):
        with self.assertRaises(ValueError):
            gv.aggregate_acquiring([record(1, "R1", "通过")], "")

    def test_unknown_status_rejected(self):
        with self.assertRaises(ValueError):
            gv.aggregate_acquiring([record(1, "R1", "已完成")], "acq-x")

    def test_non_object_record_rejected(self):
        with self.assertRaises(ValueError):
            gv.aggregate_acquiring(["nope"], "acq-x")

    def test_duplicate_case_key_rejected(self):
        with self.assertRaises(ValueError):
            gv.aggregate_acquiring([record(7, "R7", "通过"), record(7, "R7", "失败")], "acq-x")


class TestCaseKeys(unittest.TestCase):
    def test_identity_fields_propagate(self):
        report = gv.aggregate_acquiring([record(47, "ACQ_RS3_000014", "通过")], "acq-runZ")
        case = report["cases"][0]
        self.assertEqual(case["caseKey"], "acq-047-ACQ_RS3_000014")
        self.assertEqual(case["id"], case["caseKey"])
        self.assertEqual(case["runId"], "acq-runZ")
        self.assertEqual(case["assertionKind"], "acquiring")


class TestReasonMerge(unittest.TestCase):
    def merged(self, rec):
        return gv.aggregate_acquiring([rec], "acq-r")["cases"][0]["reasonCode"]

    def test_preflight_beats_all(self):
        self.assertEqual(self.merged(record(
            1, "R1", "无效用例", codes=["metric_null_env", "preflight_failed"])),
            "preflight_failed")

    def test_runner_error_beats_diagnosis_head(self):
        self.assertEqual(self.merged(record(
            1, "R1", "执行阻塞", codes=["runner_error", "metric_null_env"])),
            "runner_error")

    def test_classifier_error_hidden_in_evidence(self):
        self.assertEqual(self.merged(record(
            1, "R1", "执行阻塞", codes=["metric_null_env"],
            evidence=["classifier_error: node not found"])),
            "classifier_error")

    def test_diagnosis_head_otherwise(self):
        self.assertEqual(self.merged(record(
            1, "R1", "失败", codes=["suspected_ingest_lag", "metric_null_env"])),
            "suspected_ingest_lag")

    def test_status_defaults(self):
        self.assertEqual(self.merged(record(1, "R1", "通过")), "assertion_satisfied")
        self.assertEqual(self.merged(record(1, "R1", "失败")), "assertion_mismatch")
        self.assertEqual(self.merged(record(1, "R1", "编排阻塞")), "target_skipped")
        self.assertEqual(self.merged(record(1, "R1", "执行阻塞")), "execution_not_confirmed")
        self.assertEqual(self.merged(record(1, "R1", "无效用例")), "preflight_failed")

    def test_all_merged_codes_registered(self):
        registered = set(SCHEMA["reasonCodes"]["acquiring"]) | set(SCHEMA["reasonCodes"]["platform"])
        for status in gv.STATUSES:
            self.assertIn(gv._ACQ_STATUS_REASON[status], registered)
        for code in gv._ACQ_SINGLE_REASONS:
            self.assertIn(code, registered)


class TestEnvironmentRegression(unittest.TestCase):
    def test_family_passthrough(self):
        report = gv.aggregate_acquiring([
            record(1, "R1", "失败", codes=["metric_null_env"],
                   null_metrics=["salaxyzb_m_amt_5m"]),
            record(2, "R2", "失败", codes=["metric_null_env"],
                   null_metrics=["salaxyzb_m_other_sum_1d"]),
            record(3, "R3", "失败", codes=["metric_null_env"],
                   null_metrics=["salaxyzb_m_cnt_5m"]),
        ], "acq-runE")
        self.assertEqual(report["environmentRegression"], {"amount": [1, 2]})

    def test_missing_diagnosis_tolerated(self):
        rec = record(1, "R1", "通过")
        del rec["diagnosis"]
        report = gv.aggregate_acquiring([rec], "acq-runE2")
        self.assertEqual(report["environmentRegression"], {})
        self.assertEqual(report["cases"][0]["diagnosis"], {})


class TestRerunFrontDoor(unittest.TestCase):
    def test_aggregate_report_feeds_validate_rerun(self):
        report = gv.aggregate_acquiring([
            record(1, "R1", "通过"),
            record(2, "R2", "失败", codes=["suspected_ingest_lag"]),
        ], "acq-runA")
        plan = {"schemaVersion": "1.0", "previousRunId": "acq-runA", "runId": "acq-runB",
                "actions": [{"caseKey": "acq-002-R2", "approved": True,
                             "reasonKind": "data_fix",
                             "evidenceRefs": ["row002/responses/current.json"],
                             "preservedIntent": "verify amount window on rerun",
                             "newIsolationRefs": ["QW_0923_2"]}]}
        self.assertTrue(gv.validate_rerun(plan, report))

    def test_passed_case_cannot_be_rerun_target(self):
        report = gv.aggregate_acquiring([record(1, "R1", "通过")], "acq-runA")
        plan = {"schemaVersion": "1.0", "previousRunId": "acq-runA", "runId": "acq-runB",
                "actions": [{"caseKey": "acq-001-R1", "approved": True,
                             "reasonKind": "data_fix", "evidenceRefs": ["x"],
                             "preservedIntent": "n/a", "newIsolationRefs": ["QW_0923"]}]}
        with self.assertRaises(ValueError):
            gv.validate_rerun(plan, report)


class TestCoverageGaps(unittest.TestCase):
    def design(self, branches):
        cases, plan = [], []
        for rule, row, keys in branches:
            for key in keys:
                cases.append({"caseKey": key, "row": row, "ruleCode": rule,
                              "targetRuleSet": "rs_acq_unauthorized", "caseType": "正案例",
                              "designReview": {"status": "approved", "evidenceRefs": ["row.md"]}})
            plan.append({"ruleCode": rule, "targetRuleSet": "rs_acq_unauthorized",
                         "branchId": f"b-{rule}", "caseKeys": list(keys)})
        return {"schemaVersion": "1.0", "runId": "acq-designZ", "cases": cases, "coveragePlan": plan}

    def test_no_design_keeps_gap_list_empty_and_ignores_gaps_in_fullsuccess(self):
        report = gv.aggregate_acquiring([record(1, "R1", "通过")], "acq-runG")
        self.assertEqual(report["coverageGaps"], [])
        self.assertTrue(report["fullSuccess"])

    def test_all_branches_covered_no_gap(self):
        d = self.design([("R1", 1, ["acq-001-R1"]), ("R2", 2, ["acq-002-R2"])])
        report = gv.aggregate_acquiring(
            [record(1, "R1", "通过"), record(2, "R2", "通过")], "acq-runG", design=d)
        self.assertEqual(report["coverageGaps"], [])
        self.assertTrue(report["fullSuccess"])

    def test_failed_case_counts_as_executed_no_gap(self):
        d = self.design([("R1", 1, ["acq-001-R1"])])
        report = gv.aggregate_acquiring(
            [record(1, "R1", "失败", codes=["suspected_ingest_lag"])], "acq-runG", design=d)
        self.assertEqual(report["coverageGaps"], [])
        self.assertFalse(report["fullSuccess"])  # 失败 already blocks fullSuccess

    def test_uncovered_branch_becomes_gap_and_blocks_fullsuccess(self):
        d = self.design([("R1", 1, ["acq-001-R1"]), ("R2", 2, ["acq-002-R2"])])
        report = gv.aggregate_acquiring(
            [record(1, "R1", "通过"), record(2, "R2", "执行阻塞", codes=["metric_null_env"])],
            "acq-runG", design=d)
        self.assertEqual(len(report["coverageGaps"]), 1)
        self.assertEqual(report["coverageGaps"][0]["branchId"], "b-R2")
        self.assertFalse(report["fullSuccess"])

    def test_invalid_design_rejected(self):
        d = self.design([("R1", 1, ["acq-001-R1"])])
        d["coveragePlan"][0]["caseKeys"] = ["acq-999-RX"]  # unknown caseKey
        with self.assertRaises(ValueError):
            gv.aggregate_acquiring([record(1, "R1", "通过")], "acq-runG", design=d)


if __name__ == "__main__":
    unittest.main()
