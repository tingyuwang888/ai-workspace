#!/usr/bin/env python3
"""Drift guard for the HLB acquiring profile single source of truth (O5).

references/hlb_acquiring_profile.json is the canonical machine-readable profile.
scripts/validate-test-data.py derives its ENDPOINTS/ENUMS from that JSON at import
time, and references/acquiring-hlb-profile.md is the human-facing view. This test
pins three invariants so the three artifacts cannot silently diverge:

  1. The values validate-test-data.py actually uses still equal the frozen
     canonical literals (a JSON edit that changes behaviour breaks here loudly).
  2. The JSON keeps the structural contract the loader depends on.
  3. Every endpoint path and enum system-code in the JSON is documented in the
     Markdown, so the prose view stays in sync with the source of truth.
"""

import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
SCRIPTS = ROOT
REFERENCES = ROOT.parent / "references"
PROFILE_JSON = REFERENCES / "hlb_acquiring_profile.json"
PROFILE_MD = REFERENCES / "acquiring-hlb-profile.md"


def _load_validator():
    """Load validate-test-data.py (hyphenated filename) as a module."""
    path = SCRIPTS / "validate-test-data.py"
    spec = importlib.util.spec_from_file_location("validate_test_data_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_profile_json():
    return json.loads(PROFILE_JSON.read_text(encoding="utf-8"))


# Frozen canonical view: the ENDPOINTS/ENUMS validate-test-data.py must keep
# producing after the O5 refactor. If the JSON profile is edited to change
# runtime behaviour, update these deliberately (with a matching Markdown edit).
CANONICAL_ENDPOINTS = {
    "AcqAuthorization": {
        "path": "/riskService/trade/riskDecision/acqAuthorization",
        "required": [
            ("bizid", "S_S_BIZID"),
            ("biztime", "S_D_BIZTIME"),
            ("transactionamount", "C_F_TRANSACTIONAMOUNT"),
            ("merchantid", "C_S_MERCHANTID"),
        ],
    },
    "AcqDecline": {
        "path": "/riskService/trade/riskDecision/acqDecline",
        "required": [
            ("bizid", "S_S_BIZID"),
            ("biztime", "S_D_BIZTIME"),
            ("customeracctnumber", "C_S_CUSTOMERACCTNUMBER"),
        ],
    },
    "AcqModify": {
        "path": "/indexApi/salaxyService/acqModify/metric",
        "required": [
            ("bizid", "S_S_BIZID"),
            ("biztime", "S_D_BIZTIME"),
            ("merchantid", "customeracctnumber", "C_S_MERCHANTID"),
        ],
    },
    "AcqDisputes": {
        "path": "/indexApi/salaxyService/acqDisputes/metric",
        "required": [
            ("bizid", "S_S_BIZID"),
            ("biztime", "S_D_BIZTIME"),
            ("merchantid", "customeracctnumber", "C_S_MERCHANTID"),
        ],
    },
}

CANONICAL_ENUMS = (
    (("userdata02", "C_E_CARDSCHEME"), ("V", "M")),
    (("userdata03", "C_E_TXNSTATUSCODE"), ("1", "2")),
    (("posentrymode", "C_E_POSENTRYMODE"), ("C", "K", "E")),
    (("transactiontype", "C_E_TRANSACTIONTYPE"), ("M", "B", "U", "P", "R", "X")),
)


class TestValidatorLoadsProfile(unittest.TestCase):
    def test_endpoints_match_canonical(self):
        v = _load_validator()
        self.assertEqual(list(v.ENDPOINTS.keys()), list(CANONICAL_ENDPOINTS.keys()))
        self.assertEqual(v.ENDPOINTS, CANONICAL_ENDPOINTS)

    def test_enums_match_canonical(self):
        v = _load_validator()
        self.assertEqual(v.ENUMS, CANONICAL_ENUMS)


class TestProfileJsonInvariants(unittest.TestCase):
    def setUp(self):
        self.data = _load_profile_json()

    def test_top_level_keys(self):
        for key in ("schemaVersion", "endpoints", "enums"):
            self.assertIn(key, self.data)

    def test_endpoints_shape(self):
        self.assertTrue(self.data["endpoints"], "endpoints must not be empty")
        for name, spec in self.data["endpoints"].items():
            self.assertTrue(spec.get("path"), f"{name} missing path")
            self.assertIn("encoding", spec, f"{name} missing encoding")
            self.assertTrue(spec.get("required"), f"{name} missing required groups")
            for group in spec["required"]:
                self.assertTrue(group, f"{name} has an empty required group")

    def test_endpoint_order_matches_canonical(self):
        self.assertEqual(list(self.data["endpoints"].keys()), list(CANONICAL_ENDPOINTS.keys()))

    def test_enums_shape(self):
        self.assertTrue(self.data["enums"], "enums must not be empty")
        for entry in self.data["enums"]:
            self.assertTrue(entry.get("aliases"), "enum missing aliases")
            self.assertTrue(entry.get("valid"), "enum missing valid values")

    def test_loader_output_equals_canonical(self):
        v = _load_validator()
        # The loader is the only bridge from JSON to runtime; assert both agree.
        self.assertEqual(v.ENDPOINTS, CANONICAL_ENDPOINTS)
        self.assertEqual(v.ENUMS, CANONICAL_ENUMS)


class TestMarkdownCoversProfile(unittest.TestCase):
    def setUp(self):
        self.data = _load_profile_json()
        self.md = PROFILE_MD.read_text(encoding="utf-8")

    def test_document_is_marked_as_human_view(self):
        self.assertIn("hlb_acquiring_profile.json", self.md)
        self.assertIn("source of truth", self.md.lower())

    def test_every_endpoint_path_documented(self):
        for name, spec in self.data["endpoints"].items():
            self.assertIn(spec["path"], self.md, f"endpoint path for {name} missing in Markdown")
            self.assertIn(name, self.md, f"endpoint name {name} missing in Markdown")

    def test_every_enum_system_code_documented(self):
        for entry in self.data["enums"]:
            for code in entry["aliases"]:
                if code.startswith("C_E_"):  # system field codes appear in the mapping table
                    self.assertIn(code, self.md, f"enum code {code} missing in Markdown")


if __name__ == "__main__":
    unittest.main()
