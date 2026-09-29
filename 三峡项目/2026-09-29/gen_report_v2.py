#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the five-state Markdown report for Task #76 from et35_classified_v2.json."""
import json, collections
WS="/Users/td/.qoderwork/workspace/mttugl9pu1e3enjz"
cls=json.load(open(f"{WS}/et35_classified_v2.json"))
cnt=collections.Counter(x["verdict"] for x in cls)
group=collections.Counter(x.get("group") for x in cls)

def ids(v): return [x["caseId"] for x in cls if x["verdict"]==v]

# table
lines=[]
lines.append("| 用例 | 业务场景 | 企业类型 | 最终预警 | 五态 | 判定依据（关键） |")
lines.append("|---|---|---|---|---|---|")
for x in cls:
    basis=x["basis"]
    if len(basis)>72: basis=basis[:70]+"…"
    lines.append(f"| {x['caseId']} | {x['bizscene']} | {x['enterprisetype']} | {x['finalDecision']} | {x['verdict']} | {basis} |")
table="\n".join(lines)

# unreached summary for Group A
grpA=[x for x in cls if x["verdict"]=="编排阻塞" and x.get("expectedRuleSets")]
unreach=set()
for x in grpA:
    for c in x.get("unreachedRuleSets",[]):
        unreach.add(c)

now="2026-09-29"
report=f"""## 保后检查贷前策略（bhjcpostMainBefore · v22 语料）接口服务路径 35 条路由用例 · 五态报告

生成时间：{now}　执行环境：test03（保后检查决策服务_副本03，一次性副本）　执行通道：uniteApi / serviceConfigTest/system（接口服务调试器实跑）

### 一、执行概览

本轮将 35 条 v22 路由用例（决策流分支覆盖 19 条 + 跨子策略综合 16 条）全部通过接口服务调试器提交至 test03，逐笔抓取响应体内嵌的 nodeResults 节点级取证。35 条**全部执行成功**：status=1、reasonCode=200、回显业务流水号与提交值逐笔一致。在清空后的企查查数据源 mock（不再返回股权出质 / 经营异常负面记录）下，**35 条最终预警等级全部坍缩为绿色预警（greenwarnbh）**：所有企业 / 个人 / 关联企业的负面与征信规则集均被调用，但一律 hit=false、decision=Accept；仅顶层聚合规则集 alertLevelJudgment 命中，判为绿色（其命中描述明确为“高/中/低风险规则命中条数 = 0”）。

### 二、五态分布

| 五态 | 数量 | 用例 |
|---|---|---|
| 通过 | {cnt['通过']} | {', '.join(ids('通过'))} |
| 失败 | {cnt['失败']} | {', '.join(ids('失败')) or '—'} |
| 编排阻塞 | {cnt['编排阻塞']} | {', '.join(ids('编排阻塞'))} |
| 执行阻塞 | {cnt['执行阻塞']} | {', '.join(ids('执行阻塞')) or '—'} |
| 无效用例 | {cnt['无效用例']} | {', '.join(ids('无效用例')) or '—'} |

### 三、逐条判定

{table}

### 四、判定口径与关键发现

**“清空 mock”是本轮结果的主导变量。** 保后检查的负面信号（股权出质、经营异常等）在策略里并非由入参直接喂给规则，而是由企查查数据源节点产出、再派生成 C_N_* 特征供规则集消费。本轮之前定位到的根因正是两条静态 mock 记录（MOCK_751_011 股权出质/有效、739 经营异常/未移出）使任意查询主体都恒返回负面；将这两条数据源记录清空后，负面特征归零，于是**“无命中→绿色”成为所有用例的统一落点**。这直接重排了五态：

- **16 条“通过”**：其中 10 条“全 SAFE / 无命中→绿色”综合用例（TC_643–652）与 6 条分支可达 / DEFAULT / 不进入 PLEP 的用例（TC_619/621/623/624/625/626），其预期恰为“三子策略均被调用、无规则命中、最终绿色”，与实测完全吻合，判为通过。注意“无命中→绿色”这类用例的可测性完全依赖数据源 mock 处于干净态——这正是本轮把 643–652 从上一版的“失败”翻转为“通过”的原因。

- **19 条“编排阻塞”**：不是用例无效，而是接口服务路径在清空 mock 下**无法触达设计预期的分支**。分三类：
  1. 决策流分支覆盖（TC_606–615）预期按“企业类型×业务场景”路由出一整套规则集（含 Soe 系列与 bhjcEntBasic\* / bhjcEntLawsuit\* / PLEP 等）。实测只有企业征信、单个企业负面（借款→bhjcEntNegativeLoan / 其余→bhjcEntNegativeBelni）、个人负面、关联企业融资风险（Priv 变体）与聚合规则集执行；其余预期规则集从未被执行。
  2. 跨子策略综合的“多规则同时命中→高/中风险等级”用例（TC_637–642）：清空后的 mock 对任意主体都不返回负面数据，该路径无法按用例逐条注入 EBGS/ECGX/ELLS/PLEP 等负面命中信号，命中前提不可达。
  3. 企业子策略 DEFAULT 与国企投资类分支（TC_618/620/622）：实测关联风险网关一律解析到 Priv 变体，国企/Soe 分支从未执行；DEFAULT 由业务场景驱动而非企业类型驱动，外资（借款类）仍进入 bhjcEntNegativeLoan，其预期的“企业子策略 DEFAULT”无法到达。

- **Soe（国企）分支在本路径下整体不可达**是跨多类用例反复出现的阻塞点，与既有取证结论一致：关联风险网关不以顶层企业类型入参为判据，实测国企也走 Priv，Soe 从未执行。清空 mock 后仍未被解锁。

### 五、传输层偶发（已排除，不计阻塞）

最后三条（TC_650/651/652）最初返回 status=0 / reasonCode=405109。405109 是“渠道标识不匹配”的特征码，并非业务结论：调试抽屉重载后，渠道标识回落到未授权的默认值（0208_好客贷）。把渠道标识重新选为“保后检查”后，一个同输入的对照用例（TC_621）与这三条全部恢复为绿色。据此这三条计为“执行成功→通过”，而非执行阻塞；上一版尾部的 405109 亦属并发提交门控造成的传输假象。

### 六、覆盖边界（回应“35 条是否覆盖全面”）

这 35 条是**定向切片，不是全集**，且当前清空 mock 下覆盖面进一步收窄：

- 只验证了“无负面命中”这一条主干；红色/黄色预警、多规则叠加、按企业类型分流的 Soe 分支均未被触达（分别对应 TC_637–642、TC_606–615 的阻塞部分）。
- 每笔仅喂 1 个企业 / 个人 / 关联元素，贷前子策略设计层为集合循环（round=true），但**逐元素迭代语义未在本轮运行时坐实**。
- 场景×企业类型只取了部分组合；外资、未知类、其他类之外的更多组合，以及入参映射缺失的历史阻塞项，未纳入。

要真正覆盖“命中→红/黄”和“多元素循环”，需要在数据源 mock 侧构造**按用例可选注入的负面 fixture**（置空 Data / 改 Status / VerifyResult=0 是唯一的杠杆），而非调试器入参。这属于后续待拍板的固化工作，本报告不展开实施。

### 七、与上一版（v1，修复 mock 前）的差异

v1 分布为 通过 12 / 失败 10 / 编排阻塞 13。清空 mock 后：643–652 十条“无命中绿色”由失败翻转为通过；637–642 六条“多规则命中红色”由通过改为编排阻塞（命中前提不再可得）；决策流分支覆盖整体归入编排阻塞（Soe/Basic/Lawsuit 规则集未执行）。最终通过 16 / 编排阻塞 19 / 失败 0 / 执行阻塞 0 / 无效 0。

---
取证链：policy/page 取 uuid → policyVersion/list 取 status=5 已上线 → serviceConfigTest 调试器实跑 → 响应内嵌 nodeResults 递归解析（ChildFlowNode 的 result 为子策略完整结果 JSON 串，下钻取 RuleSetServiceNode 的 hit/decision/hitRules）。渠道标识须选“保后检查”（默认 0208_好客贷 会致 405109）。
"""
open(f"{WS}/et35_五态报告_v2.md","w").write(report)
print("wrote et35_五态报告_v2.md  (%d chars)"%len(report))
