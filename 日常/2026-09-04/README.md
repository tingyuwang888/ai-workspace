# 天策策略测试三技能包 使用说明

打包日期：2026-09-04

## 一、包内容与三个 skill 的分工

| 目录 | 角色 | 输入 → 输出 |
|---|---|---|
| `tiance-testcase-generator` | 用例生成 | 策略部署落地方案 Excel → 测试用例 JSON + Excel（规则级 / 函数级 / 决策流分支 / 预警等级四模块） |
| `tiance-policy-test` | 执行引擎 | 用例 JSON → 平台门禁 → 语义预检 → MySQL Fixture 隔离 → API 单笔执行 → 证据比对 → 15 列 Excel 报告（浏览器 UI 仅备用） |
| `tiance-report-checker` | 报告质检 | 测试报告 Excel → 四维质检（判定矛盾 / 数据缺失 / 语义重复 / 实际结果异常），原表新增"质量检查"Sheet |

三个 skill 可独立使用，也可按 generator → policy-test → checker 顺序串联成完整测试链。自动化编排器 `tiance-agent-loop`（触发检测、Subagent 分治、收敛循环）**不在本包内**，需要者单独向技能维护者索取。

## 二、安装步骤

1. 解压：`unzip tiance-test-skills-2026-09-04.zip`
2. 将解压出的三个目录**整体复制**到 QoderWork 的 skills 目录：
   - macOS / Linux：`~/.qoderwork/skills/`
   - Windows：`%USERPROFILE%\.qoderwork\skills\`
   - 若已存在同名目录，先备份旧目录再覆盖，不要合并半成品。
3. 重启 QoderWork（或刷新技能列表），对话里说"列出策略测试相关技能"验证是否被识别。

## 三、环境依赖

- Python 3.9+；依赖安装：`pip3 install -r tiance-policy-test/requirements.txt`（requests、openpyxl 等，另两个 skill 的脚本共用同一套依赖）。
- 需要 MySQL 结果验证时设置环境变量：`export TIANCE_DB_PASS='<天策库密码>'`。**密码只放环境变量，不得写入 config.json 或任何文件。**
- 需要已登录天策平台的浏览器会话。skill 会自动取 Cookie/CSRF 并处理 401 重试，但不会替你登录；会话过期时重新登录平台再跑。
- `tiance-policy-test/config.json` 默认指向三峡 POC 环境（平台 10.57.80.231、DB 10.57.80.232）。测其他环境请改 `platform.host` 与 `db.host`，或脚本传 `--host`。

## 四、各 skill 快速上手

### 1. tiance-testcase-generator（生成用例）

对话触发："用这份落地方案 Excel 生成测试用例"，附上文件即可。命令行等价：

```bash
python3 ~/.qoderwork/skills/tiance-testcase-generator/scripts/parse_strategy_excel.py "<落地方案.xlsx>" -o parsed_strategy.json
python3 ~/.qoderwork/skills/tiance-testcase-generator/scripts/generate_testcases.py parsed_strategy.json testcases.json
```

### 2. tiance-policy-test（执行测试）

对话触发："跑策略测试 bhjcpostMainBefore" / "跑用例，策略码 XXX"。命令行等价（在 skill 目录内执行）：

```bash
python3 scripts/execute_tests.py \
  --host http://<平台地址> --cookie "<登录Cookie>" \
  --strategy-config strategies/bhjcpostMainBefore.json \
  --testcases testcases.json --output results.json
# 中断续跑加 --resume；单条诊断加 --case-id TC_005 --fast
```

`strategies/` 已带 6 份策略配置：bhjcpostMainBefore（保后检查贷前主策略）、DF_PRE_CONC_001、DF_POST_SH_002、DF_POST_AREA_003、Group_Warning_Level_Strategy、automated_5_tier_rating_strategy。新策略无配置时先自动发现：

```bash
python3 scripts/discover_strategy.py discover --policy-code <code> --host <host> --csrf <token> --output strategies/<code>.json
```

**强制规则**：每次执行前平台门禁会自动核对 policyVersion / businessType，与平台不一致会阻断并要求确认；不要手改本地配置绕过门禁，否则测试结果无效。

### 3. tiance-report-checker（报告质检）

对话触发："检查一下这个测试报告"，附 Excel。命令行等价：

```bash
python3 ~/.qoderwork/skills/tiance-report-checker/scripts/check_report.py "<报告.xlsx>" -o "<输出.xlsx>"
```

## 五、注意事项与 FAQ

- **401 / 签名验证不存在**：会话过期，浏览器重新登录天策后重试；不要把 Cookie 粘贴进任何文件。
- **元数据接口不可用**：从已登录浏览器导出完整 API JSON 响应，用 `python3 scripts/platform_guard.py --config strategies/<code>.json --raw-payload browser_response.json --output platform_snapshot.json` 生成快照后加 `--platform-snapshot` 执行；快照 10 分钟内有效。
- **报告规范**：15 列、表头 #4472C4 蓝底白字雅黑 9 号；`scripts/update_report.py` 可回写执行结果并校验格式（`--validate-report`）。
- **Fixture 清理**：正常结束自动清理；中断后手动 `python3 scripts/fixture_manager.py cleanup --config strategies/<code>.json`，避免隔离数据残留污染后续用例。
- **本包已剔除**：loop_workspace 迭代产物（93MB）、backups 历史版本、__pycache__。需要完整迭代示例或 agent-loop 编排器，联系技能维护者。
- **更新机制**：三个 skill 仍在迭代，以维护者发布的最新版本为准；发现脚本 bug 或门禁误阻断请反馈，不要各自改分支。
