# 保留部署 skill 内容

- Chat ID: `mr09hcfyp5tl0sto`
- 分类：部署技能维护
- 起始日期：2026-06-30
- 会话文件数：1

---


## 会话 1/1 · `01c2cc82`

### 🧑 用户 · 2026-06-30T06:24:24.072Z

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
MEMORY (your personal notes) [99% — 10,226/10,240 bytes]
Managed exclusively by the `memory` tool (target="memory"). Do NOT use Edit/Write/create_file on any MEMORY.md or USER.md file, anywhere — those edits will not be persisted to the real memory store and will create stray files in your workspace.
══════════════════════════════════════════════
mock部署与三峡环境：本地改mock_server_py2.py→ftp.tongdun.net(user/user)→jrun.sh(~/.qoderwork/skills/jumpserver-tiance-deploy/scripts/，密码Wtyww5566@) <ip> '<cmd>' <wait_sec>远程下载+kill+重启；上传后HTTP校验非404。堡垒机fort-d.tongdun.cn→10.57.80.163(tdops,account_id=1)，不可直SSH。三峡TDS 1.4.3-mc与Nacos同机10.57.83.71:8848，7.6GB内存，启动-Xms2g -Xmx2g；bin/datamanager.properties覆盖conf，改配改bin。三峡Nginx(10.57.80.231) tiangongAdminApi upstream须指向10.57.80.161:8503，前端pending优先排查。
§
保后检查/qyzxbg基础(bizType=1贷前)：企业searchKey=C_S_QCCSEARCHKEY(2003实际key)，个人=S_affiliatedUscc，关联=S_relatedUscc；SUPPLEMENTARY为V10共用key。企业负面=757欠税/756税收违法/751股权出质/865行政处罚/739经营异常；司法=740失信/742限高/741被执行/761破产；个人=752股权冻结/751股权出质/740失信/741被执行/758终本；变更=法人/股权/经营范围/注册资本。干净基线USCC=91500000MA60W015(风险全0)，蓝色预警仅配低风险mock；征信S_S_IDNO全局共享会污染，须用独立IDNO(如500102199006290014)。红色预警3条件：HIGH≥1(纳税D级)、MED≥3(欠税+经营异常+股权出质)、极高风险≥1(征信逾期)。S000002：V27预警4级并新增极高风险命中条数，V7只在主策略层统计；输入为子策略规则命中结果，mock触发规则时按实际计数更新预期，不可强制置空。
§
天策API：create用form-urlencoded，传policyName/code/version(纯数字)/bizType/orgCode/params(扁平JSON)，返回token(35字符，前13位毫秒时间戳)+uuid(32位hex)。认证：sessionStorage._csrf_同时作_csrf_和X-Cf-Random header，runData需带。提交前GET /noahApi/policy/list取publishConfig.ordinaryConfig.version。命中解析getAllCompontlog=/noahApi/policy/report/getAllCompontlog?id=<token>&reportAuth=false&tokenId=<token>&type=1；子策略token在ChildFlowNode.extension.tokenIds；规则命中在RuleSetServiceNode.extension.executeDetail.hitRules；函数真实输出在FunctionServiceNode。旧uuid baseInfo无数据时，从tiangong_policy_test按uuid查token再采集。
§
技术片段：①Python3 \b在数字与CJK间不匹配，CJK金额替换用(?!\d)作边界。②浏览器MCP调用javascript_tool：action='javascript_exec'+text，tabId为number；异步fetch先写window._r=null再通过then写入JSON.stringify结果。③openpyxl保存xlsx会丢drawing，需从原zip复制xl/drawings/、rels并补xmlns:r。④浏览器大JSON(>50KB)绕过MCP截断：本地Python HTTP POST server接收fetch并写文件。⑤MySQL test_details JSON含转义引号\\"，须s.replace('\\"','"')后json.loads。
§
Excel报告规范：Sheet按策略名命名、15列、无汇总/未通过Sheet；表头4472C4蓝底白字/微软雅黑9号/thin/wrap/top。Col2仅填：规则/函数/决策流分支覆盖/策略预警等级覆盖。Col13/14填uuid，通过用例清空未通过原因。命中格式“编号(中文名)[风险等级]”，未命中“未命中编号(中文名)”。分支用例仅验证路径。C_O_*INFO截断后从tiangong_policy_test.test_details LIKE '%S_S_BIZID%'取完整params重建，并追加【关键入参】【数据源返回】。V6→V9流程：模板提交→list取uuid/token/decision→getAllCompontlog取hits→openpyxl生成，Col7/8填policyVersion。删除行后重编号会撞号：保留带批注行(正确函数测试)，对无批注行重编号，全表顺序TC_001~TC_NNN。
§
策略规则与评分速查：RULE_*→yellow/可能国企，RED_ALERT_*→red/民营；EBGP需RED_ALERT_+民营，EBGS09/10/11限国企，EBNP08非融民营。mock资本：RegistCapi/RealCapi数字元，PaidCapRatio小数；EBGS10实缴<10%独立KYC，EBGS11/EBGP11注册资本虚高按元判定(regCap≤50000000可能触发)。DF_PRE_CONC_001(V2+1)：dealType=singleconc，入参=S_S_IDNO+S_S_BIZID+区域码+合并额度*6，9城超限须三维同时超限。DF_POST_AREA_003(V3+4)：重庆/四川+成都→R004，其余→R003。评分：FUNC_003代偿率<1%得0分每增0.1%加16；FUNC_007拨备覆盖率变动-10%~10%得0分超出每1%加5；五级分类FUNC_001-004按异常数评分；expected含评分/待验证/待探索时API返回有效风险等级即通过。集团预警：C_F_TOTALSCORE≥90高/75-90中高/60-75中低/<60低。
§
887司法涉诉mock/ETL：mock须逐searchKey独立粘贴。信封：Paging、Result{VerifyResult,Data[CaseNo/Amount/IsProsecutor/IsDefendant/JudgeDate/PublishDate/CaseType/PartyList{Name,RoleType}]}、Status、Message、OrderNumber。IsProsecutor=true→原告/自诉，selfprosecution=1；均须PartyList.Name==searchKey且90天内。ELLP06存在于bhjcEntLawsuitNonfinancingPriv。
§
255资质证书：quallevel→C_S_QUALLEVEL（特级4/一级3/二级2/三级1，从Name提取），qualstatus→C_S_QUALSTATUS，qualexpdays→C_N_QUALEXPDAYS，statusCode255zzzs→C_N_255ZZZSSTATUSCODE；ETL不输出C_N_DROPLEVEL。Status=吊销/撤销→极高风险(D0F4C00D)，注销→高风险(EBNP07)；TC_317/318极高，TC_200/201高。DropLevel比较基线C_S_DBZRQUALLEVEL与C_S_QUALLEVEL差值，=1高风险，基线空则DropLevel=-999极高；实测C_S_QUALLEVEL常因ETL输出数字与函数期望字符串不兼容而为空，导致降级阻塞。平台mock用官方信封，163 mock扩展字段含Department/Scope/Level；isQualRelated关键词：建设/工程/资质/监理/勘察/设计。
§
天策mock配置与空数组处理：平台数据源管理页“模拟调用”Mock开关须置“是”，否则S_S_THIRDRESCODE=10000。平台内置mock与163外部mock(http://10.57.80.163:8899)独立；163只读，返回完整信封{Status,Message,Paging,OrderNumber,Result:[...]}；163未配searchKey会返回默认空响应。平台mock测试页ETL输出正确≠策略执行有值，须验证执行上下文字段实际值；ETL输出会覆盖params中手动传入的C_N_*字段，边界测试须通过mock提供数据。C_O_PERSONINFO=[]或C_O_RELATEDCOMPANYINFO=[]时平台优雅跳过对应子策略，S000011/S000012不执行，整体决策不受影响。
§
766限制高消费核查(董监高)：入参searchKey(企业uscc)+personName，返回Data含CaseNo/LimitObject/PublishDate等，PublishDate须近3个月内。平台mock用官方信封；163 mock只读并返回完整信封{Status,Message,Paging,OrderNumber,Result:[...]}。
§
规则部署、网关路由与ETL限制：未部署规则包括ARGP01/02/03、ENDX13、ARMP01/02、EBNP06，在tiangong_rule表不存在。排查未命中先查DB：SELECT name FROM tiangong_rule WHERE name LIKE '%关键词%' AND is_deleted=0，空=未部署→删用例；再确认规则在目标规则集：SELECT r.name FROM tiangong_rule r JOIN tiangong_rule_set rs ON r.biz_uuid=rs.uuid WHERE rs.rule_set_code='X'。C_S_BIZSCENARIO须在params显式传入（如“借款类”），决定网关走向与规则集组合；缺失时gateway输入为空，EBGS/EBGP类无法评估。2003后置ETL硬编码relatedent3mcancelrevokecountqcc=0，ARGP07永远不可命中；ETL还会覆盖TEMP字段=0导致跨迭代累加不可验证（TC_226）。排查规则不可命中时须检查ETL源码确认字段映射。
§
预警通数据源：SYNC直连DB(SEARCH_MYSQL) jdbc:mysql://10.57.80.232:3306/tiance（用户tongdun）。dsCode yjtxwyq（新闻舆情→x_news_tcrnw0003_all_v2）、yjtqyjjyddq（区域经济月度大全→TQ_CIBD_REGIFIN_QUAR），仅后置ETL。模拟调用statusCode=1但策略执行inputList为空→10907，因params未传数据源节点入参；新闻舆情须显式传C_S_QYUNIFSOCLCRCOD。DB插入需联动x_news_tcrnwitcode(ITCode2)、x_news_tcrnw0003_all_v2(CRNW0003_006=-1)、x_news_tcrnw0001，ID无默认值须显式提供。.ds导出文件加密(magic fcd75776)不可解析。
§
函数用例修复与循环/合并函数mock：重提交获新token；从ChildFlowNode子策略取FunctionServiceNode真实输出（非S000002预警等级）更新Col10/11/13。循环函数S000004/05读取2003 ETL输出C_S_MAJORSHAREHOLDERKEYNOS/MAJORINVESTEDCOMPANYKEYNOS（源自PubPartnerList/InvestmentList，非入参），mock须在C_S_QCCSEARCHKEY的2003中配置：PubPartnerList股东StockPercent>20%→C_S_MAJORSHAREHOLDERKEYNOS，InvestmentList投资FundedRatio>20%→C_S_MAJORINVESTEDCOMPANYKEYNOS。合并函数S000007/08同理且需失信数据；实际searchKey由企业信息对象脚本取值，查getAllCompontlog确认。
§
Excel/Col15中文乱码修复：mojibake是UTF-8字节被Latin-1解码，先解\\uXXXX再encode('latin-1').decode('utf-8')；检测时搜literal \\u00xx模式。Col15用substring(0,60)截断UTF-8会产生碎片(如'税收è¿...')，用re.sub(r'([\u4e00-\u9fff])[è¿å¡±æçé]{1,5}\.{2,3}', r'\1...', text)清理。
§
决策流分支覆盖用例(TC_247-250)测试特定子策略路径，Col15三方数据须从对应子策略采集(TC_247/248→个人子策略的764-768/771董监高系列；TC_249/250→关联企业子策略的2003/887/740/741/742)，不能统一从企业子策略采集。采集路径为getAllCompontlog→ChildFlowNode→FeatureServiceNode→nodeOutputList，分批5-10行；>50KB用本地Python HTTP server接收。
§
天策报告policyVersion：用例可能混用V9/V10，须从tiangong_policy_test按uuid查policy_version确定实际版本，不能批量改。本次报告121条V9+118条V10。
§
天策验证API：/noahApi/lab/policytest/list?uuid=UUID查列表；getAllCompontlog?id=TOKEN查日志。旧UUID从DB查token。预期"/"分隔=OR非AND。审查须核对测试数据字段值。
§
测试报告审查不能只看预期/实际文字是否对齐，必须核对测试数据是否真正设置了业务描述声称的字段值。字段缺失导致的"未命中"≠边界值验证的"未命中"。
§
天策报告policyVersion：每条用例测试时用的版本不同（V9/V10混合），不能批量改。从tiangong_policy_test按uuid查policy_version字段确定每条用例的实际版本，Col7/Col8统一写该版本。
§
ARGP07和S000005跨迭代累加因ETL硬编码/覆盖无法验证，测试用例不可修复。ARGP07的relatedent3mcancelrevokecountqcc被ETL硬编码为0。

══════════════════════════════════════════════
USER PROFILE (who the user is) [37% — 1,520/4,096 bytes]
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
§
天策策略测试验证标准：单条规则测试用例只要目标规则本身命中即算通过，不要求整体预警等级匹配。其他规则伴随命中导致整体等级拉高不影响该用例判定。
RECENT ACTIVITY (auto-loaded, read-only)
══════════════════════════════════════════════
Each entry is tagged with a chat ID (in <!-- memory-chat:{chatId} --> anchors).
If you need full conversation context from a past session, use the qoder_get_task_detail tool with that chat ID.
Only load full context when truly necessary to avoid wasting tokens.

Short-term memory beyond what is loaded above lives in dated journal files at memory/YYYY-MM-DD.md (one file per day, under the awareness directory).
To recall older daily memory, use the memory_search tool — it indexes those files. Use memory_get with a path like memory/YYYY-MM-DD.md to read a specific day in full when needed.
══════════════════════════════════════════════
## 2026-06-30

<!-- memory-chat:mr01rou7he7yhe2b -->
## Session: 检查测试报告问题
关键纠正：测试报告规则描述中"/"表示或关系(任一满足即可)，非且关系。如"规则未命中：ELLP05/ARGP05"意为两者有一个未命中即通过。用户纠正了我将其理解为"两者都须未命中"的错误。
<!-- /memory-chat:mr01rou7he7yhe2b -->

## 2026-06-29

<!-- memory-chat:mqyk0bhl71eismtj -->
## Session: 设计天策系统部署场景表
- 生成skill业务场景覆盖表格(skill_business_coverage.xlsx)，汇总4个skill的部署方式与业务场景覆盖
- 堡垒机部署覆盖信贷/交易/账户，K8s和蓝鲸CICD仅覆盖信贷，策略测试覆盖信贷贷前和贷中
- 用户提供的场景信息直接转Excel，使用openpyxl生成带格式的表格（蓝底白字表头、微软雅黑字体）
<!-- /memory-chat:mqyk0bhl71eismtj -->

Available MCP servers:
- builtin_browser: Browser automation via Chrome Extension V2

Use qw_mcp_list to see all tools, qw_mcp_get to get tool schema (ALWAYS call this before qw_mcp_call to get correct arguments), qw_mcp_call to execute.

Available tools:
mcp__builtin_browser__computer, mcp__builtin_browser__read_page, mcp__builtin_browser__find, mcp__builtin_browser__form_input, mcp__builtin_browser__navigate, mcp__builtin_browser__javascript_tool, mcp__builtin_browser__get_page_text, mcp__builtin_browser__file_upload, mcp__builtin_browser__resize_window, mcp__builtin_browser__read_console_messages, mcp__builtin_browser__read_network_requests, mcp__builtin_browser__tabs_context, mcp__builtin_browser__tabs_create, mcp__builtin_browser__tabs_context_mcp, mcp__builtin_browser__tabs_create_mcp, mcp__builtin_browser__tabs_close_mcp
</system-reminder>
这个只保留后面部署skill的内容 /Users/td/Desktop/6.10号直播分享/AI_Agent技能分享（新）.html

### 🤖 助手 · 2026-06-30T06:24:39.843Z

文件比较大，让我先了解结构，然后找到部署skill相关的内容。

### 🤖 助手 · 2026-06-30T06:26:07.264Z

文件结构清楚了：Slides 1-5 是"项目文档专家"部分，Slides 6-16 是"天策部署 Skill"部分。现在开始编辑。

### 🤖 助手 · 2026-06-30T06:28:37.724Z

已完成修改。具体改动如下：

**删除了"项目文档专家"部分**（原 Slides 1-5，共 5 张幻灯片 + 对应的 CSS 样式块约 440 行），**保留了"天策部署 Skill"的全部内容**，共 11 张幻灯片：封面、Why、jumpserver/k8s/bkci 三个 skill 详解、CI/CD 实战演示、对比与协作、怎么用、感悟上下、总结。

同时更新了标题（改为"天策部署 Skill 实战"）、幻灯片编号（1-11）和总数（11）。原文件备份在我的工作目录中。
