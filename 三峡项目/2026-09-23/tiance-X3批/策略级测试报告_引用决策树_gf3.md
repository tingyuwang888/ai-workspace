## 策略级测试报告：引用决策树（D_TREE gf3）

- 被测策略：决策树引用测试策略（标识 `dt_tree_ref_test`，policyUuid `34a6ea266cd4437f8114829cf881be56`，orgCode=sxdb，渠道=初始应用，事件=申购事件，流模式，V1，已上线）
- 被测决策工具：决策树测试gf3（D_TREE，code `TREE2609231662259291`，decisionToolUuid `fd5f5f1bbf1d487fac3f8c40fa163e1e`，version 1，已发布）
- 环境：天策 Noah POC（决策中心 · 决策工具 · 策略管理 · 策略实验室）
- 执行方式：策略画布以 UI 自动化搭建并上线；单笔测试经 `lab/policytest/create` 真实执行 → `policy/report/test/baseInfo` 预热 → `policy/report/getAllCompontlog` 读取 `contextFields`（最终出参）与 `fieldMap`（逐节点证据），全程无手工点选
- 时间：2026-09-23 17:2x–17:4x

### 目的与链路

X1 验证了"单节点引用决策矩阵"，X2 验证了"多节点链式引用决策表"。本批补齐三类决策工具的最后一类——决策树（D_TREE），并完成两项此前未落地的能力：一是把决策树从"仅导出态"推进到"编辑器保存态"的字节级 schema 采集；二是由 agent 直接在策略画布上（拖拽决策工具节点、连线、配置引用、保存、上线）端到端搭出引用决策树的策略并跑通分支测试。

策略结构：开始 → 决策工具（决策树测试gf3，读入参 `C_F_SALARY909`，写出 `C_F_SALARY908`）→ 结束。

决策树 gf3 业务逻辑（编辑器保存态，见下节 schema）：以 `C_F_SALARY909`（个人月收入909）为根判定字段，两条分支边 `≤100 → 赋值 908=1`、`>100 → 赋值 908=2`，默认决策（else 兜底）`908=0`。

### 决策树编辑器保存态 schema（本批新采集，nodes + edges 图）

决策树在编辑器"保存态"下以 `{nodes:[], edges:[]}` 图结构存储，条件挂在边上、赋值挂在叶子上，与导出态（root→childNodes 嵌套）是不同表示：

节点（3 个）：

- 根节点 `shape:"flow-capsule"`，`isRoot:true`，`nodeName:"C_F_SALARY909"`（判定字段）
- 叶子1 `shape:"flow-policy"`，`decisions:[{operatorType:"operationType", fieldType:"SYSTEM_FIELD", fieldName:"C_F_SALARY908", value:"1", valueType:"constant"}]`，`decisionsLabel:["赋值:[系统]个人月收入908=1"]`
- 叶子2 `shape:"flow-policy"`，同上但 `value:"2"`，label `赋值:[系统]个人月收入908=2`

边（2 条，条件在边上）：

- `(≤ 100)`：source=根，target=叶子1，`conditionsGroup:[{connector:"all",type:"context",conditions:[{leftKey:"C_F_SALARY909",compareKey:"<=",compareValue:"100",rightValueType:"context",priority:2}],priority:1}]`
- `(> 100)`：source=根，target=叶子2，conditions 中 `compareKey:">"`

默认决策（顶层 `defaultDecisions`）：`[{operatorType:"operationType",fieldType:"SYSTEM_FIELD",fieldName:"C_F_SALARY908",value:"0",valueType:"constant"}]`。

入参 `inputData=[C_F_SALARY909(double,系统字段)]`，出参 `outputData=[C_F_SALARY908(double,系统字段)]`。

### 画布搭建与节点身份（逐节点证据）

策略画布由 UI 自动化搭建：从左侧 stencil 拖入"决策工具"节点 → 双击打开"决策工具配置"抽屉 → 决策工具类型选"决策树"、工具名称选"决策树测试gf3"（输入/输出字段自动带出 909→908）→ 确定；再从"开始"右端口、"gf3"左右端口分别拖线到"gf3"左端口、"结束"左端口，形成 开始→gf3→结束。保存后 V1 上线，`getDetail` 回读确认发布态图含 3 节点 2 连线、决策节点 code=`TREE2609231662259291`、入 `C_F_SALARY909`、出 `C_F_SALARY908`。

单笔测试 `fieldMap` 中，`C_F_SALARY909`（读入）与 `C_F_SALARY908`（写出）的 `nodeIdList` 均标注同一决策工具节点 uuid `33aabbde-7dbf-4dbd-9a5d-53d7cda1698f`，证明每个用例都真实经过了 gf3 决策树节点执行。

### 用例与执行结果（五态）

| 用例 | 入参 C_F_SALARY909 | 命中分支 | 期望 C_F_SALARY908 | 实测 | 逐节点证据 | 五态 |
|---|---|---|---|---|---|---|
| TC1 | 50 | ≤100 | 1 | 1 | 908 nodeIdList=gf3节点 | 通过 |
| TC2 | 200 | >100 | 2 | 2 | 908 nodeIdList=gf3节点 | 通过 |
| TC3 | 省略（空） | 默认 else | 0 | 0（context 0.0） | 908 nodeIdList=gf3节点 | 通过 |
| TC4 | 100 | ≤100（边界） | 1 | 1 | 908 nodeIdList=gf3节点 | 通过 |
| TC5 | 101 | >100（边界） | 2 | 2 | 908 nodeIdList=gf3节点 | 通过 |

5 个用例全部通过：两条分支边（≤100→1、>100→2）在边界值 100/101 处切分正确，默认 else 分支（908=0）通过"省略入参"真实触发并生效——这一点与 X2 中"默认分支不可达=无效用例"相反，说明决策树的默认决策在策略层是可测的（根判定字段为空时两条件边均不命中，落到 defaultDecisions）。

### 测试流水号（可回溯）

- TC1 909=50 → `179015801100050A32A69VOFAOHNMAESXQR`（out=1）
- TC2 909=200 → `179015801300050A32A69LJ4NEDIEYVMJRQ`（out=2）
- TC3 909=省略 → `179015801500050A32A69DVLN6LEBJROPMM`（out=0）
- TC4 909=100 → `179015801700050A32A69ZQKXVLBDYXGSOR`（out=1）
- TC5 909=101 → `179015801900050A32A69KGGERY1P0ERNLS`（out=2）

报告页路由：`/noah/policyTest/report?token=<流水号>&type=1`。

### 排障记录（供复用）

1. 策略画布入口：编辑区版本行的 profile/form/debug 图标分别对应查看/改基本信息/调试，均不进入流程画布；真正进入画布是路由 `/noah/policyManage/policyEditor/{versionUuid}/{policyUuid}`（直接 location 跳转即可）。
2. 草稿态图无法用 `getDetail` 验证：`getDetail` 仅对已发布版本回吐 `graphJson`，草稿（已暂存）返回体无该字段。
3. 草稿保存接口是 `POST /noahApi/policyVersion/update?orgCode=sxdb`（form-urlencoded），而非 `policyVersion/save`；且 `update` 需带"保存类型(暂存or保存)"字段，手工拼 body 会报"保存类型不能为空"。因此本批改走 UI：画布内改模型后点"保存/暂存"由前端自动带全字段，最稳。
4. X6 画布自动化配方（本批验证有效）：
   - 拖入节点：对 stencil 项（如"决策工具"）依次派发 `pointerdown/mousedown/dragstart`，沿路径向 document 派发多步 `pointermove/mousemove/dragover`，在画布 svg 上派发 `drop/pointerup/mouseup`，节点即落位。
   - 连线：从源节点右端口的 hover 元素 `pointerdown`，向 document 逐步 `pointermove`，在目标节点 `pointerup`，即生成一条边（`left_click_drag` 太快不生效，需带中间 move 步）。
   - 配置节点：双击节点打开"决策工具配置"抽屉，antd select 用真实点击展开、再对 `li.ant-select-dropdown-menu-item` 派发完整事件序列选中。
   - 使画布变脏：选中节点后按方向键移动（`key: ArrowRight`）即可触发 暂存 生效。
5. 单笔 create 需补齐标准事件字段（S_S_BIZID/S_S_CUSTNO/S_S_ORGCODE/S_S_PRODUCTCODE/S_E_CUSTTYPE/S_S_IDNO），否则报"参数S_S_IDNO不存在…"；double 字段以字符串传值，空值用例直接省略该键。

### 结论

三类决策工具（决策矩阵 X1、决策表 X2、决策树 X3）的"策略引用 + 端到端单笔测试"能力全部打通。本批额外确立两点：一是 agent 可全程用 UI 自动化在策略画布上完成"拖节点—配置引用—连线—保存—上线"，无需人工搭建；二是决策树编辑器保存态的 nodes+edges 字节 schema 已采集并与策略级测试结果双向印证（分支边、叶子赋值、默认决策均可从 `fieldMap` 逐节点证据复现）。至此"引用决策工具的策略测试"覆盖矩阵/表/树三种类型闭环完成。

### 遗留与处置（清理交接，由使用者在天策平台手工执行，顺序：运行区下线 → 编辑区删除）

- 本批一次性策略：`dt_tree_ref_test`（policyUuid `34a6ea266cd4437f8114829cf881be56`，V1 已上线 versionUuid `f8df4682c86244afb50c6ea31b215a5e`，另有上线自动生成的 V2 草稿 `b916a9264eb2407babc2492f988e6e6a`）。
- 本批一次性决策树：决策树测试gf3（code `TREE2609231662259291`，decisionToolUuid `fd5f5f1bbf1d487fac3f8c40fa163e1e`，已发布）。
- 同系列遗留待清理的一次性策略（X1/X2/更早）：`dt_chain_gf2_test`（5d07db3e31b349c8a59daad3cafb7d08）、`dt_matrix_ref_ebcp`（9e23c378014943899236b49dc992a887）、`dt_matrix_ref_test`（9229fdcb4f0c49cca2c6a7627500ef80）、`dt_ref_test`（d0bbc36548a14881886f44c3de4b9bc0）。
