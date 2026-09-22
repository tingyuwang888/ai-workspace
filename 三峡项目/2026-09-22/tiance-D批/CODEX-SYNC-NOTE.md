# tiance-policy-test — D 批 Codex 反向同步日志 (2026-09-22)

将 QW live (`~/.qoderwork/skills/tiance-policy-test`) 的通用加固 + 文档族，
单向复制回 Codex 安装 (`~/.codex/skills/tiance-policy-test`)，恢复两树对
这些文件的字节一致。纯安装对齐，不进发布 staging。

## 同步项（全部 live→Codex 覆盖/新增，cmp 一致）

- D1 scripts/governance.py         — C 批惰性导入（去掉 result_evaluator 模块级依赖）
- D2 scripts/acquiring_runner.py   — B4 docstring 去客户名 (project-profile)
- D3 SKILL.md                       — B4 L39 prose 去客户名 (外部收单端点)
- D4 references/governance-cli.md   — B4 L154 prose 去客户名 (direct acquiring HTTP)
- D5 scripts/test_desensitized.py   — B4 客户名守卫（3 方法）
- D6 requirements.txt               — 补 jsonschema + PyYAML 两行依赖
- D7 scripts/decode_pls.py          — 新增（消除 Codex SKILL.md 悬空引用）
- D8 references/risk-governance.md  — 交叉引用从外部 risk-rule-testcase-* 改指包内 metric-*
- D9 references/{metric-design,metric-analyze,metric-pipeline,metric-design-examples,
     metric-pipeline-examples,metric-design-expected-result-template,
     metric-pipeline-expected-result-template,test-data-contract}.md
     — 文档族 8 篇新增，把 Codex 从"半迁移"推到包内自洽

## 清理

- D10 references/"hlb_acquiring_profile.json references/" 坏损目录（一次未加引号
  cp 的产物）→ 移入 ~/.Trash/tiance-codex-stray-references-<ts>，不永久删除。

## 验证

- Codex pytest: 278 → 279 passed（D5 新增守卫方法），0 失败
- Codex test_desensitized.py: 3/3（复制文件对 POC-IP/ccqtgb/客户名 clean 或在白名单）
- governance 惰性导入 + decode_pls 均可 import
- SKILL.md + risk-governance.md 相对链接 0 悬空

## 本批刻意不动（留待裁决 / 另一类）

- strategies/bhjcpostMainBefore.json — 真双向分歧：字段码 S_S_BIZSCENARIO(live) vs
  C_S_BIZSCENARIO(Codex) 不一致，且 Codex 独有整段 testExecution 块。需人工裁定字段码
  + 决定 testExecution 是否回流 live。属"合并"非"同步"。
- strategies/DF_PRE_CONC_001.json — 仅 policyName 显示名差异（低优先）。
- validate-test-data.js / test-classify-execution-result.js / test_validate_test_data.py
  — 仅 live 有、Codex SKILL 不引用、含 HLB 耦合测试，会改动 Codex 测试面，另批再议。

同步后 live↔Codex 残留差异仅剩上述三组 deferred 项。
