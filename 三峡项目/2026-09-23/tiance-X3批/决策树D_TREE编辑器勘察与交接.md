## X3 决策树（D_TREE）编辑器勘察与交接

- 环境：天策 Noah POC（orgCode=sxdb，三峡担保），决策中心 · 决策工具
- 时间：2026-09-23 14:39–14:55
- 结论：D_TREE 从零搭建的画布配置环节（节点条件抽屉 + 级联字段选择器）对合成事件与坐标点击不稳定，无法由自动化可靠驱动；该环节属共享平台上的重手工操作，按既定分工交由使用者在平台手工完成。本批不产出半棵假树，避免污染平台与给出失真结论。已确认无残留草稿（决策工具列表仍仅 g4、gf2 两条）。

### 已核实的平台事实（证据来自接口与页面）

1. 现状：平台无任何决策树。`decisiontool/page/run`（type=run / type=edit）均只返回 2 条：`METRIC26061715321945626`（g4，D_MATRIX，已发布）、`TABLE26062310321945640`（还款能力测算gf2，D_TABLE，已发布）。

2. 新建入口与路由：编辑区 → 新增 → 弹出"新增决策工具"三卡（决策树 / 决策表 / 决策矩阵）→ 点"决策树"跳转 `/noah/bodyguard/modelTool/decisionTree?currentTab=2`。

3. 标识自动生成：进入即调 `GET decisiontool/loadDecisionToolCode?decisionToolType=D_TREE`，本例得到 `TREE2609231462259248`（D_TREE 前缀为 `TREE`，区别于矩阵 `METRIC`、表 `TABLE`）。

4. 基础信息表单结构：所属机构（三峡担保，锁定）、所属渠道（下拉：初始应用/个人网银/企业网银/…共 17 项）、名称、标识、描述、默认决策。
   - 默认决策 = 决策方式（处置方式 / 字段赋值）+ 目标字段 + 运算符（=）+ 值类型（常量 / 变量）+ 值。
   - 目标字段用同盾自研 `tntd-cascader` 级联选择器，一级"字段"，二级分类"系统字段 / 动态字段 / 对象字段"，三级为具体字段。系统字段样例含"个人月收入908""个人月收入909""指标结果"等 9 项（即 g4 用到的 C_F_SALARY908/909）。
   - 常量值输入框会自动格式化为两位小数（如输入 0 → "0.00"）。

5. 决策树设计画布：进入"决策树设计"页时已预置一棵起步树——根"节点"（配置节点）→"配置条件"→"+"（加分支）→"决策"叶子（配置决策）。右上角有"N 项不完善"校验指示（本例 3 项：节点、条件、决策各待配置），不完善时保存/上线被拦。

6. D_TREE 的 content schema 采集方式（重要，免导出）：`decisiontool/page/run` 列表响应体里每条工具都内联携带完整 `content` JSON（已在 gf2 上验证：root→childNodes→conditionsGroup/conditions→decision 结构）。因此只要决策树被成功保存（哪怕最小一棵），即可直接 `GET decisiontool/page/run?type=edit` 读出其 D_TREE content 字节结构，无需再走组件导出文件。

### 未能自动完成的原因（不编造）

- 根节点"配置节点"抽屉：单击/双击节点仅触发选中高亮，点"配置节点 >"链接位不弹配置面板；合成 click/mousedown 与坐标点击均未打开该抽屉，无法继续配置切分字段与分支条件。
- 级联字段选择器（tntd-cascader）需真实 hover 逐级展开，脚本 hover 与 trusted hover 均未能稳定展开到目标字段并回填。
- 这些属编辑器交互层限制，非接口限制；保存接口本身可用（X1/X2 已证同类策略保存/上线可程序化）。

### 交还给使用者的手工步骤（完成后我接手其余自动化）

1. 在 `/noah/bodyguard/modelTool/decisionTree` 新建决策树，基础信息：渠道=初始应用，名称如"决策树测试gf3"，标识沿用自动生成的 `TREE…`。
2. 默认决策：决策方式=字段赋值，目标字段选一个 double 输出字段（如"个人月收入908"），常量填 0。
3. 决策树设计：根节点配置切分字段（如"个人月收入909"，double），加两条分支（如 ≤100 与 >100），每条分支末端"决策"分别赋值输出字段常量（如 =1、=2）。
4. 保存 → 上线（上线抽屉选版本 V1 → 确定）。

使用者完成第 1–4 步并保存/上线后，我将自动接手：
- 用 `decisiontool/page/run?type=edit` 读取并固化 D_TREE 的 content 字节 schema；
- 建一条引用该决策树的流模式策略、连线、保存、上线（X1/X2 已验证的画布与发布通路）；
- 用 `lab/policytest/create` → `baseInfo` 预热 → `getAllCompontlog.contextFields/fieldMap` 跑分支用例并交叉核对；
- 产出 X3 五态报告并归档、更新清理交接。

### 清理交接（累计，由使用者平台手工执行：运行区下线 → 编辑区删除）

- X2：`dt_chain_gf2_test`（uuid 5d07db3e31b349c8a59daad3cafb7d08，versionUuid e4fc6fae77db4b9781f4e57f2ed1d7c6，已发布）
- X1/更早：`dt_matrix_ref_ebcp`（9e23c378014943899236b49dc992a887）、`dt_matrix_ref_test`（9229fdcb4f0c49cca2c6a7627500ef80）、`dt_ref_test`（d0bbc36548a14881886f44c3de4b9bc0）
- X3 决策树草稿：本次未保存，平台无残留，无需清理。
