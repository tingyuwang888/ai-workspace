# tiance-M批（2026-09-22）：strategies 反向同步 + 文档字段码纠错

批次方向特殊：本批为 **Codex → live**（以往批次均为 live → Codex/staging），因为证据核对判定 Codex 侧 strategies 才是权威。

## M1  strategies/bhjcpostMainBefore.json（Codex→live）
- 字段码纠错：`S_S_BIZSCENARIO` → `C_S_BIZSCENARIO`（平台权威字段码，源自 metadata_sxdb service_config：eleType=systemField, serviceParam=bizScene；`S_S_BIZSCENARIO` 在平台元数据中不存在）
- 补齐 live 缺失的 `testExecution` 块（semanticValidation / requiredParams[S_S_IDNO,C_F_RANDOMNUM] / defaults / ruleCatalog / ruleDependencies / thirdPartyCapabilities{live_uncontrolled} / riskLevelCapability{derived_uncontrolled} / note）——该块是 live 自有工具链（prepare_testcases/execute_tests/mock_probe/config_generator/comparison_engine）消费的契约键
- 合并后 `_validate_config_structure` 返回 errors=[] warnings=[]

## M2  strategies/DF_PRE_CONC_001.json（Codex→live）
- policyName 纠错：`保前集中度判断策略` → `保前集中度判断_单户关联户区域`（与平台真实策略名一致）

## M3  docs/examples.md（live+Codex 同步纠错）
- 5 处 `S_S_BIZSCENARIO` → `C_S_BIZSCENARIO`（行 97/249/278/306/335），纯字段码纠错
- live↔Codex 保持字节一致；staging 发布子集不含 examples.md，故本批与发布无关

## 验证
- live pytest：279 passed, 4 subtests
- Codex pytest：279 passed, 4 subtests
- 两 strategies 文件 live↔Codex cmp 字节一致
- examples.md 无残留 `S_S_BIZSCENARIO`，`C_S_BIZSCENARIO` 计数 = 5

## 备份
改前 live 原始文件已备份至 workspace `M-batch-backup-2026-09-22/`
