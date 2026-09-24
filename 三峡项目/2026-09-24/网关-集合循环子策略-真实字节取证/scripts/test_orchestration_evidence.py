# -*- coding: utf-8 -*-
"""复杂编排取证端到端测试（E6）。

与 ``test_result_evaluator.py`` 的分工：那份直接喂**已解析的** evidence 字典测契约校验器；
本份从**原始平台响应形状**（``{"success": true, "data": {...}}`` 恰好五键）出发，串起
``parse_component_evidence`` → ``validate_evidence_contract`` → ``render_component_evidence``
整条链路，验证解析器对真实载荷形状的正确性。

证据可信度分层（与 orchestration-testing.md 一致）：
- 决策工具树 / 矩阵 / 表：**真实字节** —— 逐字来自 2026-09-24 在三峡 ``sxdb`` 实盘重抓的
  只读 ``getAllCompontlog`` 原始响应，存放于 ``fixtures/evidence_{tree,matrix,table}_real.json``，
  测试直接从真实字节加载解析。真实骨架为两支：树 / 表是 ``ROOT→CHILD→DECISION``（CHILD 带命中
  conditionSet），**矩阵只有 ``ROOT→DECISION``、无 CHILD、nodeId 为空串**，矩阵命中仅由 DECISION
  出参体现。
- 网关 / 子策略：**真实字节**（2026-09-24 补抓）—— ExclusiveGateway 逐字来自 ``crossScoreFlow``
  实盘响应（``fixtures/evidence_gateway_real.json``），集合循环子策略逐字来自 ``bhjcpostMainBefore``
  （``fixtures/evidence_subpolicy_collection_real.json``）。真实字节推翻了两处此前的假设：
  子策略运行时节点类型是 ``ChildFlowNode``（**非**文档假设的 ``SubPolicyNode`` /
  ``CollectionSubPolicyNode``），子执行 token 以 ``extension.tokenIds`` **数组**送达；网关的
  ``nodeOutputList`` **恒为空**，真正的分支选择落在 ``extension.conditions``（命中的分支序号数组）。
"""

import json
from pathlib import Path
import unittest

from execute_tests import parse_component_evidence, render_component_evidence
from result_evaluator import validate_evidence_contract

_FIXTURES = Path(__file__).parent / "fixtures"


def _load_real(name):
    """Load a byte-exact captured getAllCompontlog response from fixtures/."""
    with (_FIXTURES / f"evidence_{name}_real.json").open(encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# 原始平台响应 fixture 构造器（data 恰好五键，对齐实测 getAllCompontlog 形状）
# --------------------------------------------------------------------------

def _wrap(flow, field_map=None, diagram_line=None, context_fields=None, token="tok-1"):
    return {
        "success": True,
        "data": {
            "contextFields": context_fields or {},
            "fieldMap": field_map or {},
            "diagramLine": diagram_line or [],
            "flowModelinAndOutputParams": flow,
            "token": token,
        },
    }


def _detail(steps):
    # executeDetail 实测为 JSON 字符串（数组），这里忠实还原该编码形态。
    return json.dumps(steps, ensure_ascii=False)


def _decision_node(node_name, node_id, tool_code, execute_detail,
                   inputs, outputs, version="1"):
    return {
        "nodeType": "DecisionToolServiceNode",
        "nodeName": node_name,
        "nodeId": node_id,
        "extension": {"code": tool_code, "version": version, "executeDetail": execute_detail},
        "nodeInputList": inputs,
        "nodeOutputList": outputs,
    }


def _tree_response():
    """D_TREE 决策树测试gf3 —— 逐字真实字节（fixtures/evidence_tree_real.json，2026-09-24 实盘重抓）。"""
    return _load_real("tree")


def _matrix_response():
    """D_MATRIX g4 —— 逐字真实字节（fixtures/evidence_matrix_real.json）：ROOT→DECISION、无 CHILD。"""
    return _load_real("matrix")


def _table_response():
    """D_TABLE 还款能力测算gf2 —— 逐字真实字节（fixtures/evidence_table_real.json）：≤6 命中→贷款利率=7。"""
    return _load_real("table")


def _chained_reused_response():
    """同一决策工具被复用两次（verified 坑）：nodeName 完全相同，仅 nodeId / ordinal 可区分。"""
    def detail_for(left_value, assign):
        return _detail([
            {"nodeType": "ROOT", "nodeId": None, "nodeDesc": "C_F_SALARY909"},
            {"nodeType": "CHILD", "nodeId": "hash-x", "nodeDesc": "(≤ 100)",
             "conditionSet": {"conditionGroup": [
                 {"connector": "all", "conditions": [
                     {"leftFieldName": "C_F_SALARY909", "leftFieldDesc": "个人月收入909",
                      "operator": "<=", "rightValue": "100", "leftValue": left_value, "isHit": True},
                 ]},
             ]}},
            {"nodeType": "DECISION", "nodeId": None, "nodeDesc": "赋值",
             "decisionResult": {"C_F_SALARY908": assign}},
        ])

    first = _decision_node(
        "决策树测试gf3", "node-tree-A", "TREE2609231662259291", detail_for("90", "1"),
        inputs=[{"fieldName": "C_F_SALARY909", "value": "90"}],
        outputs=[{"fieldName": "C_F_SALARY908", "value": "1"}],
    )
    second = _decision_node(
        "决策树测试gf3", "node-tree-B", "TREE2609231662259291", detail_for("50", "1"),
        inputs=[{"fieldName": "C_F_SALARY909", "value": "50"}],
        outputs=[{"fieldName": "C_F_SALARY908", "value": "1"}],
    )
    flow = [
        {"nodeType": "StartEvent", "nodeName": "开始", "nodeId": "s"},
        first, second,
        {"nodeType": "EndEvent", "nodeName": "结束", "nodeId": "e"},
    ]
    return _wrap(flow, diagram_line=["l0", "l1", "l2"], token="chain-token")


def _gateway_response():
    """ExclusiveGateway —— 逐字真实字节（fixtures/evidence_gateway_real.json，crossScoreFlow）。

    真实形状：nodeInputList 携带判定入参（如 C_F_APPLYSCORE=62），nodeOutputList 恒为空，
    分支选择落在 extension.conditions（命中的分支序号数组）。
    """
    return _load_real("gateway")


def _subpolicy_response():
    """集合循环子策略 —— 逐字真实字节（fixtures/evidence_subpolicy_collection_real.json，bhjcpostMainBefore）。

    真实运行时节点类型为 ChildFlowNode（非文档假设的 SubPolicyNode/CollectionSubPolicyNode），
    子执行 token 以 extension.tokenIds 数组送达，逐元素子策略编码落在 extension.code。
    """
    return _load_real("subpolicy_collection")


# --------------------------------------------------------------------------
# 解析层：decision tool 树 / 矩阵 / 表
# --------------------------------------------------------------------------

class TestDecisionToolParsing(unittest.TestCase):

    def test_tree_builds_root_child_decision_trace_and_path(self):
        ev = parse_component_evidence(_tree_response())
        self.assertEqual(1, len(ev["decisionTools"]))
        tool = ev["decisionTools"][0]
        self.assertEqual("TREE2609231662259291", tool["toolCode"])
        self.assertTrue(tool["available"])
        self.assertFalse(tool["parseError"])
        self.assertEqual({"C_F_SALARY908": "1"}, tool["assigned"])
        self.assertEqual(
            ["ROOT", "CHILD", "DECISION"],
            [step["stepType"] for step in tool["steps"]],
        )
        # CHILD.nodeId 是 hash（树真实字节：e6055a.../0f910b...）—— 定位靠 ordinal，不靠 nodeId
        self.assertEqual("e6055a40a22441b4ae0ffc6010d9b3d1", tool["steps"][1]["platformNodeId"])
        self.assertEqual("0f910b95059041df878a337ec7c94fd8", tool["steps"][2]["platformNodeId"])
        hit = tool["hitConditions"]
        self.assertEqual(1, len(hit))
        self.assertEqual("C_F_SALARY909", hit[0]["field"])
        self.assertEqual("个人月收入909", tool["steps"][1]["desc"])
        self.assertEqual("<=", hit[0]["operator"])
        self.assertEqual("100", hit[0]["expected"])
        # 真实 leftValue 为 float 50.0（右值边界仍是字符串 "100"）
        self.assertEqual(50.0, hit[0]["actual"])
        self.assertTrue(hit[0]["hit"])
        # N 节点 3 → N-1 连线 2（真实画布连线 UUID）
        self.assertEqual(
            ["ffeb2b62-41ee-48a3-85ca-fd764f91d450", "383efa72-941b-4dd8-8cdd-e30961c216a7"],
            ev["pathLines"],
        )
        # 真实流程节点类型/名：StartFlowNode/EndFlowNode，节点名"开始节点/结束节点"
        self.assertEqual(
            ["开始节点", "决策树测试gf3", "结束节点"],
            [item["nodeName"] for item in ev["flowOrder"]],
        )
        self.assertTrue(ev["pathComplete"])

    def test_matrix_has_no_child_step_only_root_decision(self):
        ev = parse_component_evidence(_matrix_response())
        tool = ev["decisionTools"][0]
        self.assertEqual("METRIC26061715321945626", tool["toolCode"])
        self.assertTrue(tool["available"])
        # 真实矩阵只有 ROOT→DECISION，无 CHILD 命中步——命中仅由 DECISION 出参体现
        self.assertEqual(["ROOT", "DECISION"], [step["stepType"] for step in tool["steps"]])
        # 两步 nodeId 均为空串（既非树 hash，也非表 null）
        self.assertEqual(["", ""], [step["platformNodeId"] for step in tool["steps"]])
        self.assertEqual({"C_F_SALARY919": 0.0}, tool["assigned"])
        # 无 CHILD → 无 hitConditions（矩阵命中不能靠条件步证明，只能看出参）
        self.assertEqual([], tool["hitConditions"])

    def test_table_child_nodeid_is_null_and_steps_keyed_by_ordinal(self):
        ev = parse_component_evidence(_table_response())
        tool = ev["decisionTools"][0]
        self.assertEqual("TABLE26062310321945640", tool["toolCode"])
        self.assertTrue(tool["available"])
        # 表 CHILD.nodeId = null → 只能用 ordinal / conditionSet 识别
        self.assertIsNone(tool["steps"][1]["platformNodeId"])
        self.assertEqual([0, 1, 2], [step["ordinal"] for step in tool["steps"]])
        self.assertEqual({"C_F_OUTLENDINGRATE": "7"}, tool["assigned"])

    def test_unparseable_execute_detail_degrades_to_available_false(self):
        bad = _decision_node(
            "坏工具", "node-bad", "TREE??", "this-is-not-json",
            inputs=[], outputs=[{"fieldName": "C_F_OUT", "value": "1"}],
        )
        ev = parse_component_evidence(_wrap([bad]))
        tool = ev["decisionTools"][0]
        self.assertFalse(tool["available"])
        self.assertTrue(tool["parseError"])
        # 出参仍从 nodeOutputList 解出（与 executeDetail 无关）
        self.assertEqual([{"field": "C_F_OUT", "displayName": "", "value": "1"}], tool["outputs"])


# --------------------------------------------------------------------------
# 端到端：parse → validate（契约消费 + 降级不失败）
# --------------------------------------------------------------------------

class TestEndToEndContract(unittest.TestCase):

    def _validate(self, expected, resp):
        ev = parse_component_evidence(resp)
        mismatches = []
        missing = validate_evidence_contract(expected, ev, mismatches=mismatches)
        return missing, mismatches

    def test_tree_contract_clean(self):
        expected = {
            "decisionTools": [{
                "nodeName": "决策树测试gf3",
                "fieldValues": {"C_F_SALARY908": "1"},
                "hitConditions": [
                    # 真实字节：leftValue=50.0(float)、rightValue 边界="100"(str)
                    {"field": "C_F_SALARY909", "operator": "<=", "expected": "100", "actual": 50},
                ],
            }],
            "pathContains": ["开始节点", "决策树测试gf3", "结束节点"],
            "nodeVisited": [{"nodeType": "DecisionToolServiceNode"}],
        }
        missing, mismatches = self._validate(expected, _tree_response())
        self.assertEqual([], missing)
        self.assertEqual([], mismatches)

    def test_tree_output_value_mismatch_is_failed(self):
        expected = {"decisionTools": [{"nodeName": "决策树测试gf3",
                                       "fieldValues": {"C_F_SALARY908": "2"}}]}
        missing, mismatches = self._validate(expected, _tree_response())
        self.assertTrue(any(i.startswith("决策工具出参值:") for i in missing))
        self.assertTrue(any(i.startswith("决策工具出参值:") for i in mismatches))

    def test_matrix_int_vs_float_value_normalizes(self):
        # 真实出参 C_F_SALARY919=0.0(float)，契约写 int 0 —— 归一后应通过
        expected = {"decisionTools": [{"nodeName": "g4",
                                       "fieldValues": {"C_F_SALARY919": 0}}]}
        missing, mismatches = self._validate(expected, _matrix_response())
        self.assertEqual([], missing)
        self.assertEqual([], mismatches)

    def test_reused_tool_by_name_is_ambiguous_not_failed(self):
        expected = {"decisionTools": [{"nodeName": "决策树测试gf3",
                                       "fieldValues": {"C_F_SALARY908": "1"}}]}
        missing, mismatches = self._validate(expected, _chained_reused_response())
        self.assertIn("决策工具身份不唯一:决策树测试gf3（需按 nodeId 定位）", missing)
        self.assertEqual([], mismatches)

    def test_reused_tool_resolved_by_nodeid(self):
        # 复用场景补 nodeId 去掉歧义；两条叶赋值相同，取首条也不影响结论
        expected = {"decisionTools": [{"nodeId": "node-tree-B",
                                       "fieldValues": {"C_F_SALARY908": "1"}}]}
        missing, mismatches = self._validate(expected, _chained_reused_response())
        self.assertNotIn(
            "决策工具身份不唯一:?(未声明决策工具身份)（需按 nodeId 定位）", missing)
        self.assertFalse(any(i.startswith("决策工具身份不唯一") for i in missing))
        self.assertEqual([], mismatches)

    def test_strict_path_order_violation_detected(self):
        expected = {"executionPath": {"pathContains": ["结束节点", "决策树测试gf3"], "order": "strict"}}
        missing, mismatches = self._validate(expected, _tree_response())
        self.assertIn("路径顺序与契约不符", missing)

    def test_unavailable_detail_is_missing_only(self):
        expected = {"decisionTools": [{"nodeName": "坏工具",
                                       "fieldValues": {"C_F_OUT": "1"}}]}
        missing, mismatches = self._validate(expected, _wrap([
            _decision_node("坏工具", "node-bad", "TREE??", "not-json",
                           inputs=[], outputs=[{"fieldName": "C_F_OUT", "value": "1"}]),
        ]))
        self.assertIn("决策工具证据不可用:坏工具", missing)
        self.assertEqual([], mismatches)

    def test_gateway_parsed_and_flow_visible(self):
        # 真实字节纠正：网关证据落在 selectedBranch(extension.conditions)，
        # routeFields 在实盘恒为空（nodeOutputList=[]），不再用合成 routeTarget 断言。
        ev = parse_component_evidence(_gateway_response())
        self.assertEqual(1, len(ev["gateways"]))
        gw = ev["gateways"][0]
        self.assertEqual("ExclusiveGateway", gw["nodeType"])
        self.assertEqual([("C_F_APPLYSCORE", "62")],
                         [(i["field"], i["value"]) for i in gw["inputs"]])
        self.assertEqual([], [(r["field"], r["value"]) for r in gw["routeFields"]])
        self.assertEqual(["2"], gw["selectedBranch"])
        self.assertEqual("start", gw["gatewayType"])
        self.assertRegex(gw["conditionRuleUuid"], r"^[0-9a-f]{32}$")
        # 网关出现在 flowOrder，可被 nodeVisited 按 nodeType 断言
        ev_types = [item["nodeType"] for item in ev["flowOrder"]]
        self.assertIn("ExclusiveGateway", ev_types)
        mismatches = []
        missing = validate_evidence_contract(
            {"nodeVisited": [{"nodeType": "ExclusiveGateway"}]}, ev, mismatches=mismatches)
        self.assertEqual([], missing)
        self.assertEqual([], mismatches)

    def test_subpolicy_child_tokens_extracted_from_both_containers(self):
        # 真实字节纠正：运行时是 3 个 ChildFlowNode，子 token 来自 extension.tokenIds 数组，
        # 逐元素子策略编码落在 extension.code（parser 关联为 policyCode）。
        ev = parse_component_evidence(_subpolicy_response())
        self.assertEqual(3, len(ev["subPolicies"]))
        children = [c for node in ev["subPolicies"] for c in node["children"]]
        self.assertEqual(
            {"bhjcpostSubentBefore", "bhjcpostSubperBefore", "bhjcpostSubrelateentBefore"},
            {c["policyCode"] for c in children})
        for child in children:
            self.assertTrue(child["token"])
            self.assertEqual("tokenIds", child["sourceKey"])

    def test_subpolicy_present_but_unavailable_is_missing_not_mismatch(self):
        # 真实形状：子项无 evidenceStatus → 默认 unavailable → 只缺不失败
        expected = {"subPolicies": [{"policyCode": "bhjcpostSubentBefore"}]}
        ev = parse_component_evidence(_subpolicy_response())
        mismatches = []
        missing = validate_evidence_contract(expected, ev, mismatches=mismatches)
        self.assertTrue(any(i.startswith("子策略证据不可用:") for i in missing))
        self.assertEqual([], mismatches)

    def test_subpolicy_absent_when_no_subnodes_is_missing_only(self):
        # 树响应里根本没有子策略节点 → sub_entries 为空 → 只缺不失败
        expected = {"subPolicies": [{"policyCode": "SUB_POLICY_X"}]}
        ev = parse_component_evidence(_tree_response())
        mismatches = []
        missing = validate_evidence_contract(expected, ev, mismatches=mismatches)
        self.assertTrue(any(i.startswith("子策略:") for i in missing))
        self.assertEqual([], mismatches)

    def test_no_component_log_captured_is_missing_only(self):
        # 非成功响应 / 无 flow → parse 返回 {}；路径断言只缺不失败
        ev = parse_component_evidence({"success": False})
        self.assertEqual({}, ev)
        mismatches = []
        missing = validate_evidence_contract({"pathContains": ["决策树测试gf3"]}, ev,
                                             mismatches=mismatches)
        self.assertIn("路径节点:决策树测试gf3", missing)
        self.assertEqual([], mismatches)


# --------------------------------------------------------------------------
# 端到端：parse → render（人读视图含逐节点证据）
# --------------------------------------------------------------------------

class TestEndToEndRender(unittest.TestCase):

    def test_tree_render_shows_trace_hits_and_path(self):
        text = render_component_evidence(parse_component_evidence(_tree_response()))
        self.assertIn("决策工具: 决策树测试gf3(TREE2609231662259291)", text)
        self.assertIn("[ROOT]", text)
        self.assertIn("[CHILD]", text)
        self.assertIn("[DECISION]", text)
        self.assertIn("命中 C_F_SALARY909", text)
        self.assertIn("赋值 C_F_SALARY908=1", text)
        self.assertIn("开始节点 → 决策树测试gf3 → 结束节点", text)
        self.assertIn("走过连线 2 条", text)

    def test_unavailable_tool_render_states_evidence_gap(self):
        text = render_component_evidence(parse_component_evidence(_wrap([
            _decision_node("坏工具", "node-bad", "T", "not-json", inputs=[], outputs=[]),
        ])))
        self.assertIn("执行详情解析失败(证据不可用)", text)

    def test_gateway_render_shows_route(self):
        text = render_component_evidence(parse_component_evidence(_gateway_response()))
        # Real ExclusiveGateway nodeOutputList is always empty, so the render
        # shows only the evaluated input on the judgement line -- there is no
        # route-target line to assert (unlike the earlier synthetic fixture).
        self.assertIn("网关: 判断开始(ExclusiveGateway)", text)
        self.assertIn("判定 C_F_APPLYSCORE=62", text)
        self.assertNotIn("routeTarget", text)

    def test_subpolicy_render_lists_children_status(self):
        text = render_component_evidence(parse_component_evidence(_subpolicy_response()))
        self.assertIn("子策略: 保后检查贷前企业子策略", text)
        self.assertIn("子项 bhjcpostSubentBefore", text)
        self.assertIn("status=unavailable", text)


if __name__ == "__main__":
    unittest.main()
