# tiance-policy-test O2b — 收单链 checkpoint 设计门禁 (2026-09-22)

给收单执行链（acquiring_runner.py）补一道与平台链 validate_design/design-manifest/
coveragePlan 对等的“设计门禁”，并把此前在 governance.aggregate_acquiring 里被硬编码
为 [] 的 coverageGaps 解冻为“按声明的覆盖计划计算”。内容完全通用（无客户标识），
属于可发布子集。

## 改了什么

- references/governance.schema.json
  - reasonCodes.acquiring += `checkpoint_design_mismatch`
  - 新增 $defs：acqDesign / acqCase / acqCheckpoint（与 rerun 同套路，供 runner 与
    governance 共用同一 schema 单一来源校验）
- scripts/acquiring_runner.py
  - 新增 $defs 包装校验器 `_schema_def_errors`，以及 `validate_acq_design` /
    `load_acq_design` / `checkpoint_design_issues`
  - 新增 `--design <acq-design.json>`（严格 opt-in）：跑某 checkpoint 前先按
    acqCheckpoint 校验并按 caseKey 匹配已批准设计用例；缺席或合同矛盾者在分配隔离
    命名空间 token 之前即判 `无效用例`，reasonCode = checkpoint_design_mismatch
- scripts/governance.py
  - `aggregate_acquiring(results, run_id, design=None)`：传 design 时按
    coveragePlan 计算 coverageGaps（某分支的 caseKeys 无一命中 通过/失败 即为缺口），
    并纳入 fullSuccess（全通过 AND 无缺口）；不传 design 时 coverageGaps 仍为 []
  - 新增 `--design` CLI 选项；对 validate_acq_design 采用惰性导入避免循环依赖
- references/governance-cli.md：3b 增“收单链 checkpoint 设计门禁 (O2b)”小节 + 示例
- references/metric-execute.md：Bundled Acquiring Executor 行为保证增 --design 条目
- SKILL.md：双链 governed-results 说明增可选 --design 门禁一句
- 测试：
  - test_governance_aggregate.py += TestCoverageGaps（5）
  - test_acquiring_runner.py += TestCheckpointDesignGate（4）
  - test_status_vocabulary.py 守卫元组 += checkpoint_design_mismatch

## 关键边界

- 门禁严格 opt-in：不传 --design 时 runner 与 aggregate 行为与既有基线逐字节一致，
  保护测试基线。
- caseKey 单一公式与 aggregate 一致：`acq-{row:03d}-{rule_code}`（缺 row/rule 时
  `acq-misc{idx:03d}`），设计用例据此一对一绑定执行归档。
- 仅证明 schema 与身份绑定，不替 Agent 判定规则语义/历史就绪/评审证据。

## 校验结果

- 全量套件：live 与 Codex 两侧均 `Ran 278 tests / OK`（基线 269 + O2b 9）。
- 发布子集（staging）同步 O2b 文件后 test_desensitized 复跑通过，客户标识仍为 0。
- Codex 逐字节 cmp：9 个共享 O2b 文件全部 OK；顺带补齐 Codex 缺失的
  references/metric-execute.md、references/scorecard-pls-testing.md，消除 SKILL.md
  悬空链接（属既有快照落后的补齐，非本批逻辑改动）。

## 归档文件（本目录）

references/governance.schema.json, references/governance-cli.md,
references/metric-execute.md, scripts/governance.py, scripts/acquiring_runner.py,
scripts/test_governance_aggregate.py, scripts/test_acquiring_runner.py,
scripts/test_status_vocabulary.py, SKILL.md
