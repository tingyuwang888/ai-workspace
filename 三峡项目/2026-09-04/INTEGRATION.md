# 保后检查三方响应回放服务 v3-merged

V2 架构 + V46 已验证业务响应的合并版本：保留 V2 的严格场景隔离、鉴权与
V27 双路径；V46 的显式规则映射与响应构造函数以"兼容数据源"
（legacy_v46 provider）迁入，全部由显式 `BHJC_...__runId____caseId` 场景键
驱动，不继承 V46 的全局状态。

## 当前能力

- 27 个企查查 HTTP 接口 + 企业征信 SOAP 接口（兼容 V27 新旧路径）；
- 619 份已有响应文件（mock-files）；
- 284 个注册场景：3 个 V2 原生（ELLS01 HIT/MISS/BOUNDARY）+ 280 个 legacy
  兼容场景（141 条规则 × HIT/MISS）+ 1 个 RED 全量回归场景；
- KYC 信封含整数 `StatusCode=200`（对齐 2003 ETL 的
  C_N_2003KHSFSBSTATUSCODE，修复字符串被解析为 0 的问题）；
- 迁移清单 `migration_manifest.json`：147 条规则合同四态分类
  （native 1 / legacy 141 / excluded_inconclusive 2 / pending 3）；
- ISO 日期运行时平移、精确边界偏移；
- 未声明 BHJC 场景明确拒绝（Status 201）；非目标接口安全基线；
- QCC Token/Timespan 鉴权、SOAP 测试 Token、`/health` 就绪检查。

## 明确不迁移（V46 遗留行为）

- 全局 sticky_mode 与调用次数判断（跨用例状态污染来源）；
- 未知接口安全回退掩盖错误的行为；
- ENLX11 / ENDX13（739 冒充预警通）：保持 inconclusive，见清单
  excluded_inconclusive；预警通新闻舆情与区域经济接口仍禁止切换；
- EBNP09 / EBNP10 / EBNP11：已迁移 legacy provider（09 吊销 / 10 注销 /
  11 中标展示），清单 pending 归零；qualStatus 枚举字面值待平台核对；
- EBNP05 合同重复定义：已按 legacy 显式映射去重迁移，平台实际编码仍需复核。

## V46 路由缺陷（v3 已修复，差异回归登记为 expected_v46_defect）

- 758 / 771：V46 只认旧路径 EndExecuteCaseCheck / PersonEndExCaseCheck，
  V27 新路径 TerminatedCaseCheck / PersonTerminatedCaseCheck 返回空；
  v3 双路径均路由到同一处理器；
- 766：/PersonSumptuaryCheck/GetList 被 LIST_RISK_MAP 中 SumptuaryCheck(742)
  子串先匹配，PLEP01 / PLDX01 的个人限高数据在 V46 永远送不到；
  v3 独立 Flask 路由修复，test_legacy_person_sumptuary_route_not_hijacked 固化；
- EBNP07 合同纠偏：合同为"距到期≤30天"日期系，V46 与旧 v3 曾实现为状态系
  （Status=注销）；现改为 EndDate=今日+20天、Status=正常。**历史以"注销"数据
  跑出的 EBNP07 结论作废，须新轮次重验**；
- 伴随命中清单（不得按单规则隔离验收）：EBNP07→[EBNP06]、
  EBNP08→[EBNP06,EBNP07]；EBNP09/10 用未来日期实现单规则隔离。

差异回归：`python3 diff_regression.py`（需同时启动 legacy 8899 与 v3 8923，
跑前确认两端口无残留监听），输出 diff_report.json / diff_report.md；472 组
比对（144 规则 × HIT/MISS × 声明接口），归一化 OrderNumber / 企业名占位 /
searchKey 回声后逐字段比对；6 组登记为预期差异（766 子串缺陷 ×2、EBNP07
纠偏、EBNP09/10/11 新增覆盖）。

## legacy provider 机制

场景合同（scenarios/registry.json）的响应声明支持：

```json
"741": {"provider": "legacy_v46", "mode": "yellow", "ruleCode": "ELLP03"}
```

- mode 取值：yellow（按 ruleCode 走 V46 显式映射）/ red / blue /
  yellow_full / safe；
- 响应由 legacy_v46_adapter 调用 legacy_v46_source 的响应构造函数生成，
  不读取任何全局状态；场景未声明的接口自动回安全基线；
- SOAP 征信由 SOAP 体内 `<searchKey>`（或 BHJC 格式 entName）显式驱动，
  仅 ECGX 场景返回非零明细，其余保持全 0 安全基线；
- legacy_v46_source.py 已打 Python3 兼容补丁（http.server / unicode 别名 /
  urllib.unquote / bytes 判定），py2 与 py3 均可导入。

再生成命令（幂等）：

```bash
python3 build_legacy_scenarios.py     # 从合同+legacy映射重建 BHJC_LG_ 场景
python3 build_migration_manifest.py   # 重建 migration_manifest.json
```

## 本地验证

```bash
cd /Users/td/Desktop/AI提效/三峡项目策略测试文件夹/qcc-mock-service-v3-merged
python3 -m unittest test_service_v3_merged -v   # 19 项合并验证
python3 -m unittest test_service_v2 -v          # 14 项 V2 回归
python3 -m unittest test_platform_switch_plan -v
```

## 启动

先按 `.env.example` 设置测试环境变量。不要把密钥写入仓库或对话。

```bash
export QCC_MOCK_AUTH_ENABLED=true
export QCC_MOCK_APP_KEY='<test-key>'
export QCC_MOCK_SECRET_KEY='<test-secret>'
export QCC_MOCK_SOAP_TOKEN='<test-soap-token>'
./run.sh
curl http://127.0.0.1:8899/health
```

## 场景键与注册表

```text
BHJC_<SCENARIO>__<runId>__<caseId>
```

`BHJC_LG_ELLP03_HIT` 决定响应模板；`runId/caseId` 只用于隔离与追踪。
原生场景声明 `sourceSearchKey + dateOffsets`；legacy 场景声明
`provider/mode/ruleCode`。规则场景加入注册表前必须人工确认：响应只触发
目标规则、伴随规则列入允许清单、日期边界符合规则语义、ETL 字段与
expectedEvidence 一致、不含真实客户敏感数据。

## 生成测试合同

```bash
python3 build_test_contracts.py \
  --parsed-strategy '<parsed_strategy.json>' \
  --strategy-code bhjcpostMainBefore \
  --mock-index mock-files/index.json \
  --output-dir contracts
```

`scenario_payload_required` 只表示协议已有适配，不表示规则响应已完成；
v3 中该状态的规则由 legacy provider 提供响应并在清单中标记 legacy。

## 天策测试环境接入

该步骤需要平台管理员执行，Loop 不得自动修改。

1. 备份当前数据源配置和 URL；
2. 仅在隔离测试环境部署本服务；
3. 将 27 个企查查服务 URL 的 host 替换为本服务地址，path 保持 V27 原值；
4. 企业征信 URL 指向 `/services/enterpriseCreditQueryTwoCode`；
5. 配置测试 AppKey/SecretKey 或对应签名；
6. 禁止生产机构或生产渠道访问 Mock 地址；
7. 运行 `/health` 和代表性场景探针；
8. 执行一条规则用例，确认组件日志标记了目标三方节点；
9. 测试结束后恢复原始数据源配置并复核。

## 切换前缺口与回滚

- 平台侧差异回归（27 接口 × 146 规则）尚未执行，本地套件不覆盖平台链路；
- pending 三条规则（EBNP09/10/11）需先人工决策；
- 10 个函数精确输入输出场景、红黄蓝绿组合驱动仍待补；
- 切换步骤见 platform-switch-checklist.md 与 platform-switch-plan.json，
  回滚见 platform-rollback-plan.json；
- V2 目录保持不动，作为回滚基线；本服务当前未部署、未改天策配置。
