# tiance-N批（2026-09-22）：三个 JS/校验器文件同步到 Codex

批次方向：**live → Codex**（正向），补齐 Codex 缺失的三个"收单链 + 测试数据校验"辅助文件。staging 发布子集不涉及本批（`validate-test-data.py` 家族因 HLB 耦合按 SYNC-NOTE #95 有意排除，`test-classify-execution-result.js` 同理不入发布子集）。

## N1  同步文件（live→Codex，全部 cp 后 cmp 字节一致）

| 文件 | 作用 |
|---|---|
| scripts/validate-test-data.js | Node.js **薄包装/启动器**，`spawnSync` 调用同目录 `validate-test-data.py`；先试 `RISK_RULE_PYTHON` 环境变量再退回 `python3`。让 CLI 端可用 `node` 拉起校验器 |
| scripts/test-classify-execution-result.js | 收单链分类器 `classify-execution-result.js` 的 **JS 单元测试**（`assert` 驱动），构造 rule_code/target_rule_set_code/case_type/current_response(nodeResults/hitRules) 等 fixture 断言五态分类结果 |
| scripts/test_validate_test_data.py | `validate-test-data.py` 的 **Python 集成测试**，同时覆盖 JS 包装器（`WRAPPER` 变量走 `node`）；用 openpyxl 造 workbook fixture；顶层为 `main()`（非 pytest 收集对象，独立脚本运行） |

依赖侧（`classify-execution-result.js`、`validate-test-data.py`）此前已存在于 Codex 且与 live 字节一致，故复制零风险。

## N2  验证

- Codex 端 `node scripts/test-classify-execution-result.js` → `classify-execution-result tests passed` (exit 0)
- Codex 端 `python3 scripts/test_validate_test_data.py` → `validate-test-data compatibility tests passed` (exit 0)
- Codex 全量 pytest 保持 **279 passed, 4 subtests**（这三个文件不被 pytest 收集，count 预期不变）
- 复制后 live↔Codex `scripts/` 目录文件名差异清零

## 备注

- `test_validate_test_data.py` 中 ENDPOINT fixture 使用 `http://hlb.example.invalid:8000/...acqAuthorization` —— 该 .invalid TLD 与 `hlb` 片段属测试专用命名，已在 B4 守卫的 `CUSTOMER_NAME_ALLOWLIST` 白名单中，不触发发布扫描。
- 三文件均不入 staging（发布子集）：`test_validate_test_data.py` 依赖客户耦合的 `validate-test-data.py`，`test-classify-execution-result.js` 未随收单链分类器进入发布清单，`validate-test-data.js` 仅是前者包装器。
