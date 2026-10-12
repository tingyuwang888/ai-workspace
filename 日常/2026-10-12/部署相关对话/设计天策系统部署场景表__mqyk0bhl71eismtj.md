# 设计天策系统部署场景表

- Chat ID: `mqyk0bhl71eismtj`
- 分类：部署技能维护
- 起始日期：2026-06-29
- 会话文件数：1

---


## 会话 1/1 · `87f4a8f7`

### 🧑 用户 · 2026-06-29T01:43:33.964Z

<system-reminder>
User environment — Timezone: Asia/Shanghai (UTC+08:00). Locale: en-US. OS: darwin.
Note: If you need the current date or time, run `date` via Bash to get a fresh, accurate value. Do not assume a fixed time.

You are operating in awareness mode. The following files define your persona,
operating manual, and memory. Follow them as authoritative guidelines.

Contents of /Users/td/.qoderwork/awareness/main/AGENTS.md (operating manual)

# AGENTS.md - 工作手册

<!-- 工作手册：沉淀稳定的项目约定、编码标准、架构规则和工作流偏好，不放临时事实，可随时更新。 -->

IMPORTANT: You are operating in awareness mode. The files above are ALWAYS
relevant to your work. Follow them as authoritative guidelines.
══════════════════════════════════════════════
MEMORY (your personal notes) [80% — 8,285/10,240 bytes]
Managed exclusively by the `memory` tool (target="memory"). Do NOT use Edit/Write/create_file on any MEMORY.md or USER.md file, anywhere — those edits will not be persisted to the real memory store and will create stray files in your workspace.
══════════════════════════════════════════════
mock部署流程：本地改mock_server_py2.py→FTP上传ftp.tongdun.net(user/user)→jrun.sh远程下载+kill+重启。jrun.sh在~/.qoderwork/skills/jumpserver-tiance-deploy/scripts/，密码Wtyww5566@，格式jrun.sh <ip> '<cmd>' <wait_sec>；FTP上传后须验证HTTP下载是否404。堡垒机fort-d.tongdun.cn→10.57.80.163(tdops,account_id=1)；本机无法直接SSH到该IP及fort-d(需密码非密钥)，必要时在堡垒机终端操作。
§
三峡TDS(1.4.3-mc)与Nacos(8848)同机10.57.83.71，内存7.6GB，启动须-Xms2g -Xmx2g；bin/datamanager.properties覆盖conf同名文件，改配应改bin目录。三峡Nginx(10.57.80.231)的tiangongAdminApi upstream须指向10.57.80.161:8503；前端pending/无法加载优先排查该upstream。
§
保后检查规则与数据源映射：①bizType：bhjcpostMainBefore主策略须用bizType=1(贷前)，非4；1=贷前，4=贷中保后。②searchKey映射：S000010/11/12对应S_uscc/S_affiliatedUscc/S_relatedUscc；保后企业/关联企业类型须与S_S_ENTERPRISETYPE一致。③数据源→规则：企业负面=757欠税/756税收违法/751股权出质/865行政处罚/739经营异常；司法涉诉=740失信/742限高消/741被执行/761破产；个人级=752股权冻结/751股权出质/740失信/741被执行/758终本；变更类(qyzxbg企业征信)=法人/股权/经营范围/注册资本。④qyzxbg mock须完整SOAP XML含5部分：basicBorrowingList+loanRepaymentList(逾期ED01)、othLoanSumList(assetquality=2→关注ECGX03)、rrAccountList(担保逾期ED07)、unscGuaranteeList(assetquality=2→担保关注ECGX06)、debitInterestList(balanceinterest>0→欠息ECGX07)；retCode须为1。
§
天策API：create用form-urlencoded，必传policyName/policyCode/policyVersion/bizType/orgCode/params，返回token(35字符，前13位毫秒时间戳)和uuid(32位hex)。认证只需sessionStorage._csrf_同时作为_csrf_和X-Cf-Random header，无需X-Td-Signature；仅cookie会401。runData须带X-Cf-Random+_csrf_。params为扁平JSON {"key":"value"}，非嵌套{name,value}格式，否则报"复杂字段解析异常"。getAllCompontlog路径=/noahApi/policy/report/getAllCompontlog?id=<token>&reportAuth=false&tokenId=<token>&type=1；子策略childToken在主策略flowModelinAndOutputParams的ChildFlowNode.extension.tokenIds中；规则命中在RuleSetServiceNode.extension.executeDetail(JSON字符串).hitRules中。查策略版本：GET /noahApi/policy/list?orgCode=sxdb&appCode=bhjcqd，取publishConfig.ordinaryConfig.version；版本号频繁变更，提交前务必查询最新版本，勿凭记忆填写。
§
技术片段：①Python3 \b在数字与CJK间不匹配，CJK金额替换用(?!\d)作边界。②浏览器MCP调用javascript_tool：action='javascript_exec'+text，tabId为number；异步fetch先写window._r=null再通过then写入JSON.stringify结果。③openpyxl保存xlsx会丢drawing，需从原zip复制xl/drawings/、rels并补xmlns:r。④浏览器大JSON(>50KB)绕过MCP截断：本地Python HTTP POST server接收fetch并写文件。
§
mock/ETL通用规则：①平台mock为STATIC，改2003会影响所有共用用例。②字段名须与QCC API文档一致（/Users/td/Downloads/企查查接口文档说明 3/）；字段须经ETL产出→数据源出参→规则集入参三层全通，以nodeType=1 inputFieldList为准，outputConfig detail字段checked=false会截断。③searchKey路由：企业级C_O_ENTERPRISEINFO.S_uscc、个人级C_O_PERSONINFO.S_affiliatedUscc、关联企业级C_O_RELATEDCOMPANYINFO.S_relatedUscc。④2003 Data资本数字元；ETL：InvestmentList(FundedRatio>20%)→C_S_MAJORINVESTEDCOMPANYKEYNOS，PubPartnerList(StockPercent>20%)→C_S_MAJORSHAREHOLDERKEYNOS，ChangeList按ProjectName分类(法人/股权/经营范围/注册资本)，RevokeInfo(<90天)→C_N_REVOKECNT，TaxCreditList→taxcreditgrade。⑤低风险ChangeList(蓝)：EBGS01法人变更/EBGS02股权变更/EBGS03经营范围/EBGS08注册资本增加，均须90天内+被告输出count+detail。⑥771个人级须传personName，输出pterminatedcnt/detail，PLDX04需count>0且detail非空。⑦排查链路：ETL key→数据源出参→系统字段→规则入参；params中BOUNDARY_*无法到达mock。
§
测试报告规范与决策流分支覆盖(Excel为准，JSON同步)：Sheet以策略名命名、15列、无汇总/未通过Sheet；表头蓝底白字4472C4/微软雅黑9号/thin/wrap_text/top，仅Col11着色。模块(Col2)仅填：规则、函数、决策流分支覆盖、策略预警等级覆盖。Col13填uuid(32位hex)，Col14保存uuid；通过用例清空“未通过原因”。命中/未命中格式为“编号(中文名)[风险等级]”/“未命中编号(中文名)”；用例名引用函数须同时含编号和中文名；Col10只写规则/函数级验证详情。决策流分支用例只验证是否走了对应分支，预期和实际只写分支路径确认，不附带规则命中数或预警等级；路由走对=正向，规则不触发/无命中=反向，例TC_174走DEFAULT=正向、TC_001全SAFE=反向、TC_178不进入PLEP=反向。C_O_*INFO JSON截断后不可用截断参数重提交，须用完整参数重建并追加【关键入参】【数据源返回】。覆盖标注：全量触发、部分触发、端到端执行；借款/债券/委贷/投资等因路由不同需单独用例。验证“通过”≠实际命中，须在平台确认规则集执行结果。V6 pass/fail：正向须命中，反向须未命中/Accept；字符串判定先re.search('未命中')，再用r'(?:规则)?命中[：:]'。跨版本：V6模板→V9提交→list取uuid/token/decision→getAllCompontlog取hits→openpyxl生成，Col7/8换policyVersion。参数截断时从tiangong_policy_test.test_details(LIKE '%S_S_BIZID%')取完整params。
§
策略规则速查：①企业类型/预警色：RULE_*→yellow/可能国企，RED_ALERT_*→red/民营；EBGP需RED_ALERT_+民营，EBGS09/10/11限国企版，EBNP08非融类民营子策略。②mock资本：RegistCapi/RealCapi数字元（文档带"万元"），PaidCapRatio小数；EBGS10实缴占比<10%独立KYC，EBGS11/EBGP11注册资本虚高按元判定(regCap≤50000000可能触发)。③DF_PRE_CONC_001(V2+1)：dealType=singleconc，入参=S_S_IDNO+S_S_BIZID+区域代码+合并额度*6，三方9城全部超限须三维同时超限。④DF_POST_AREA_003(V3+4)：重庆/四川+成都→R004，其余地市→R003，保后已用额度=C_F_AREAGUARANTEEAMOUNTOFF+C_F_AREARESERVEAMOUNTOFF。⑤评分：FUNC_003代偿率<1%得0分，每增0.1%加16；FUNC_007拨备覆盖率变动率-10%~10%得0分，超出每1%加5；五级分类FUNC_001-004按异常数评分，FUNC_005代偿≤90天返回NONE但规则集不参考；expected含"评分=X分/待验证/待探索"时API返回有效风险等级即通过。⑥集团预警：C_F_TOTALSCORE≥90高、75-90中高、60-75中低、<60低。⑦V27：S000002预警4级并新增"极高风险规则命中条数"；V7：S000002只在主策略层统计命中数(不含子策略)，企业子策略路由问题需平台修复。
§
887司法涉诉mock/ETL规则、诊断与子策略路由：①mock配置须逐searchKey独立粘贴，不可合并为大文本块，否则平台原样返回originalData.content导致ETL无法解析，S_S_THIRDRESCODE=10000。②诊断流程：先查887节点nodeOutputList的S_S_THIRDRESCODE，再查contextFields中C_N_PRESERVCNT/C_F_DEFENDAMT等887字段，最后查规则集executeDetail的hitRules；C_N_887CPWSHCSTATUSCODE=200表示mock生效，缺失或S_S_THIRDRESCODE=10000表示未匹配。③CaseReason含"借款"→loandisputecnt>0(触发ELLS07等)；CaseType=bq→preservcnt>0(触发ELLS04)；selfprosecution为原告；均须searchKey==Name且90天内，标志位"1"/"0"。④ELLS05/ELDS05(被告金额≥500万)与ELLS07(借款纠纷被告)必然同时触发：defendamt与loandisputecnt在if(isDefendant&&isLoanDispute)中累计，defendamt须有借款关键词才累积，无法通过CaseReason隔离；验证时只确认目标规则命中即可，允许其他规则伴随命中。⑤子策略路由：个人子策略无887节点，PLEP/PLDX限高用766限制高消费核查董监高；关联企业子策略887的searchKey=S_relatedUscc(91500000MA60REL01)，非主企业USCC；企业级887用S_uscc。

══════════════════════════════════════════════
USER PROFILE (who the user is) [31% — 1,303/4,096 bytes]
Managed exclusively by the `memory` tool (target="user"). Do NOT use Edit/Write/create_file on any MEMORY.md or USER.md file, anywhere — those edits will not be persisted to the real memory store and will create stray files in your workspace.
══════════════════════════════════════════════
用户是同盾AI Agent交付部署试点的执行人，负责堡垒机和K8s部署场景，需向管理层汇报试点进展。测试报告等交付物用通俗易懂的中文描述，不要英文缩写/技术术语(如MAIN03、LOW>=1)，要让非技术人员也能看懂。
§
做Excel/报告更新时优先增量修改(改特定行)，不要全量重建。仅在结构变更时才重建。两次被纠正"不需要重建报告"。
§
天策mock配置由用户自己在平台数据源管理页粘贴完成：我只需生成符合API文档结构的完整mock JSON数据，并给出每个searchKey对应的JSON数据与searchKey列表；不要修改Python mock代码，也不需要生成SQL。
§
验证规则是否命中时，应自己通过API(getAllCompontlog)或打开报告页面读取命中详情，不要让用户手动查看后反馈。用户期望自主完成验证闭环。
§
用户要求仅测试指定的测试用例，不要同时提交多个用例。例如用户说"跑一下TC_109"时，只提交TC_109，不要同时提交TC_099等其他用例。
§
用户要求每次更新完Excel报告后，通过present_files工具输出最新版报告给用户。
§
更新Excel报告前必须先询问用户确认，不要自行决定更新时机。用户明确要求"更新前要先询问我"。
RECENT ACTIVITY (auto-loaded, read-only)
══════════════════════════════════════════════
Each entry is tagged with a chat ID (in <!-- memory-chat:{chatId} --> anchors).
If you need full conversation context from a past session, use the qoder_get_task_detail tool with that chat ID.
Only load full context when truly necessary to avoid wasting tokens.

Short-term memory beyond what is loaded above lives in dated journal files at memory/YYYY-MM-DD.md (one file per day, under the awareness directory).
To recall older daily memory, use the memory_search tool — it indexes those files. Use memory_get with a path like memory/YYYY-MM-DD.md to read a specific day in full when needed.
══════════════════════════════════════════════
## 2026-06-27

<!-- memory-chat:b8659bc8-c4d7-4a05-840b-b77ae389bc32 -->
## Session: 绿色预警验证与Excel修正
## Session: 绿色预警验证与Excel修正
- 重跑TC_001确认绿色预警，发现X-Td-Signature不需要(仅需_csrf_+X-Cf-Random)，之前花了大量时间逆向签名逻辑
- 批量提交11条预期绿色预警用例(TC_001-TC_010+TC_015)到V10主策略，全部返回绿色预警
- 增量更新V9报告Excel：实际结果改为绿色预警，通过率164/84→165/83
- 被纠正Col13应填data.uuid(32位hex)不是data.token(35位)，重新提交并捕获正确UUID修正
- 更新tiance-policy-test skill加入Col13警告说明
<!-- /memory-chat:b8659bc8-c4d7-4a05-840b-b77ae389bc32 -->

## 2026-06-26

<!-- memory-chat:mqu9ggpmhzes2us6 -->
## Session: 三峡担保项目联调风险汇报
- 生成保后检查策略测试周报Word：整合邮件+1.2M行会话导出，249条用例/96%通过率，面向管理层通俗化
- 保后检查测试本周成果：249条用例覆盖20规则集147条规则，数据迭代28版报告51版，通过率96%(239/10)
- 发现关键问题：企业征信mock默认非零值致全部高风险、searchKey字段名不一致(C_S_QCCSEARCHKEY vs LIST)、需路由mock
- 剩余10条未通过用例均为887裁判文书接口mock配置问题，已整理模板待手动配置
- 脱敏处理哈密银行Excel(6/24)：5sheet替换银行名/人名/38字段/81交易码/金额，修复openpyxl丢失drawing
- 部署技能盘点(6/22)：18中间件+14应用+5前端+13DB模块，输出覆盖清单Word文档
- 优化tiance-policy-test skill(6/25)：16列模板+7类模块分组+3实战示例+验证闭环要求
- npm docx包需在workspace本地安装才能运行，全局安装曾失败
<!-- /memory-chat:mqu9ggpmhzes2us6 -->

Available MCP servers:
- builtin_browser: Browser automation via Chrome Extension V2

Use qw_mcp_list to see all tools, qw_mcp_get to get tool schema (ALWAYS call this before qw_mcp_call to get correct arguments), qw_mcp_call to execute.

Available tools:
mcp__builtin_browser__computer, mcp__builtin_browser__read_page, mcp__builtin_browser__find, mcp__builtin_browser__form_input, mcp__builtin_browser__navigate, mcp__builtin_browser__javascript_tool, mcp__builtin_browser__get_page_text, mcp__builtin_browser__file_upload, mcp__builtin_browser__resize_window, mcp__builtin_browser__read_console_messages, mcp__builtin_browser__read_network_requests, mcp__builtin_browser__tabs_context, mcp__builtin_browser__tabs_create, mcp__builtin_browser__tabs_context_mcp, mcp__builtin_browser__tabs_create_mcp, mcp__builtin_browser__tabs_close_mcp
</system-reminder>
通过堡垒机部署天策系统skill覆盖的业务场景：信贷、交易和账户场景
通过K8s部署天策系统skill覆盖的业务场景：信贷
搭建蓝鲸云平台CICD流水线skill覆盖的业务场景：信贷
策略测试skill覆盖的业务场景：信贷的贷前和贷中场景 按照这个内容给我设计一个表格

### 🤖 助手 · 2026-06-29T01:44:19.493Z

表格已经生成好了，包含4个Skill及其对应的业务场景覆盖情况：

### 🤖 助手 · 2026-06-29T01:44:30.920Z

表格之前已经生成好了，我直接呈现给你：

### 🤖 助手 · 2026-06-29T01:44:37.627Z

表格已生成完成，内容如下：

| 序号 | Skill名称 | 部署/工作方式 | 覆盖业务场景 |
|------|-----------|--------------|-------------|
| 1 | 堡垒机部署天策系统 | 通过JumpServer堡垒机SSH远程部署 | 信贷、交易、账户 |
| 2 | K8s部署天策系统 | 通过Kubernetes容器化部署 | 信贷 |
| 3 | 蓝鲸云平台CICD流水线 | 在蓝鲸CI平台搭建构建部署流水线 | 信贷 |
| 4 | 策略测试 | 天策决策平台策略全链路自动化测试 | 信贷（贷前、贷中） |

[查看Excel文件](file:///Users/td/.qoderwork/workspace/mqyk0bhl71eismtj/outputs/skill_business_coverage.xlsx)

需要调整表格内容或格式吗？

### 🧑 用户 · 2026-06-29T01:51:22.510Z

<user-pasted-image file="/Users/td/.qoderwork/workspace/mqyk0bhl71eismtj/uploads/image_1782697881328_6o9vkxx.png" /> 这个策略测试skill我描述的对吗？

### 🤖 助手 · 2026-06-29T01:51:44.217Z

看了你的描述，有两处和实际情况不太一致：

**第一，输入来源不太准确。** 你写的是"通过策略文档生成对应的测试用例"，但实际上策略测试skill是**从Excel读取已有的测试用例**，而不是从策略文档自动生成。它不负责"造用例"，而是负责"跑用例"。

**第二，执行方式不完整。** 你只提到了"通过API接口执行"，但实际支持两种提交方式：API批量提交（通过JS fetch批量提交，适合大量用例）和UI交互提交（通过浏览器操作Ant Design组件逐个提交，适合需要验证界面的场景）。

如果要改得更贴切，可以参考这个方向：

> 从Excel测试用例文件读取用例，通过API批量提交或UI交互方式执行测试，连接数据库验证执行结果，最终汇总生成Excel测试报告

另外你截图里的表头和我之前生成的Excel列名不完全一样，你是自己在文档里重新画了这个表格吗？如果需要我按你截图的格式重新生成一版Excel，告诉我就好。

### 🧑 用户 · 2026-06-30T03:42:52.660Z

<system-reminder>
User environment — Timezone: Asia/Shanghai (UTC+08:00). Locale: en-US. OS: darwin.
Note: If you need the current date or time, run `date` via Bash to get a fresh, accurate value. Do not assume a fixed time.

Available MCP servers:
- builtin_browser: Browser automation via Chrome Extension V2

Use qw_mcp_list to see all tools, qw_mcp_get to get tool schema (ALWAYS call this before qw_mcp_call to get correct arguments), qw_mcp_call to execute.

Available tools:
mcp__builtin_browser__computer, mcp__builtin_browser__read_page, mcp__builtin_browser__find, mcp__builtin_browser__form_input, mcp__builtin_browser__navigate, mcp__builtin_browser__javascript_tool, mcp__builtin_browser__get_page_text, mcp__builtin_browser__file_upload, mcp__builtin_browser__resize_window, mcp__builtin_browser__read_console_messages, mcp__builtin_browser__read_network_requests, mcp__builtin_browser__tabs_context, mcp__builtin_browser__tabs_create, mcp__builtin_browser__tabs_context_mcp, mcp__builtin_browser__tabs_create_mcp, mcp__builtin_browser__tabs_close_mcp
</system-reminder>
现在策略测试skill放在哪里？

### 🤖 助手 · 2026-06-30T03:43:07.087Z

策略测试skill的文件位置在这里：

### 🤖 助手 · 2026-06-30T03:43:21.260Z

策略测试skill存放在 `~/.qoderwork/skills/tiance-policy-test/` 目录下，包含以下文件：

- **SKILL.md** — 主技能文件（36KB），包含完整的测试流程和规则
- **api-reference.md** — 天策API参考文档
- **ant-design-tips.md** — UI交互提交时Ant Design组件操作技巧
- **examples.md** — 测试用例示例
- **result-comparison.md** — 结果比对逻辑说明
- **scripts/** — 辅助脚本目录

上次更新时间是6月27日。你是想调整skill的内容，还是在问别的？
