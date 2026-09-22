
# Risk Rule Test Case Execution

Execute only data that has passed structural and semantic preflight. Archive the exact outbound requests and platform responses so another agent can reproduce every decision.

## Required Inputs

- Test case workbook or case manifest
- Interface documentation and project profile
- Target policy, rule-set code, rule code, and case type for every row
- Endpoint, HTTP method, encoding, and authentication information
- Verified list/tag prerequisites when applicable

If credentials, endpoint, or target metadata are missing, mark the affected rows `执行阻塞` or `无效用例` as appropriate; do not guess.

Complete authorized offline normalization and preflight before asking for missing
execution access. Keep unresolved rows separate and continue independent approved
cases only after isolation and all applicable gates pass. Do not turn an analysis
or report-only request into a live test run.

## Workflow

### 1. Normalize Test Data

Accept both supported column-N dialects:

- current endpoint: `当前笔接口` or top-level `接口地址`;
- current request: `当前笔` or `触发交易(当前笔)`;
- history request: `请求参数`, or `请求参数模板` plus `批量生成数量`.

Expand `{序号001-010}`, `字段分布`, `分散商户`, `商户起始`, `账号用商户`, and `分散天数` in memory. Validation and execution must call the same expansion implementation. Read [references/test-data-contract.md](test-data-contract.md) before generating or normalizing column N.

Use interface field names in outbound requests. Resolve system field codes only for validation and evidence comparison.

### 2. Run Preflight Gates

Run the bundled structural validator:

```bash
node ../scripts/validate-test-data.js --execution-ready <excel-file>
```

Then perform semantic consistency checks against `执行元数据` and the step description:

1. target rule, target rule set, strategy, and case type are present;
2. expected current fields equal the normalized current request;
3. expanded history count, amounts, distinct keys, and timestamps reproduce the documented arithmetic;
4. required fields and enums match the endpoint profile;
5. every `bizid` and external transaction ID is unique;
6. all relevant isolation keys are unique across independent cases;
7. list membership and tag prerequisites are verified, not merely stated;
8. current time and derived fields such as event hour or open days match the scenario.

Any mismatch between scenario, generated JSON, and final outbound request is `无效用例`. Do not send it.

### 3. Plan Safe Execution

- Execute history events before the current transaction.
- Keep events within a case sequential.
- Parallelize cases only when all metric grouping keys are isolated.
- Disable parallelism for shared lists, shared merchants, shared cards, shared terminals, dynamic cohort metrics, or tag-generation dependencies.
- Use a fresh execution namespace per run to avoid stale checkpoints and historical contamination.

Merchant-only isolation is insufficient. Isolate every grouping dimension used by relevant indicators: card, account, merchant, terminal, customer/CIF, MIDBIN, MCC cohort, or their combination.

### 4. Load and Verify History

For each history event:

1. send the exact expanded request;
2. archive endpoint, headers excluding secrets, encoding, request, response, timestamp, and token;
3. verify that the event was accepted;
4. when the platform exposes metrics or event history, confirm the event entered the intended indicator filters.

For expensive batches, run a calibration subset first. If a required metric remains zero, null, or below the planned contribution, stop before the current transaction and mark the case `无效用例` with evidence. Do not create a predictable rule failure.

### 5. Send the Current Transaction

Immediately before sending, compare the final serialized outbound request with `预期当前笔字段`. Archive the serialized request, not only the source template. This gate must catch changes such as:

- planned amount `1499` sent as `3500`;
- planned event hour `2` sent as `14`;
- planned open days `90` derived as `999`.

### 6. Verify Strategy Path and Classify

Use the bundled classifier:

First verify that the archive contains the complete target-path and hit-list
evidence required by its schema. Missing or failed evidence retrieval is an
`执行阻塞`, not an empty path or a negative hit. Do not pass an incomplete archive
to the classifier as if it were complete; record the evidence gap separately.

```bash
node ../scripts/classify-execution-result.js <execution-archive.json>
```

Classification order is mandatory:

1. request or transport failed -> `执行阻塞`;
2. planned and actual request differ -> `无效用例`;
3. response succeeded and a complete verified path proves the target rule set did not execute -> `编排阻塞`;
4. target rule set executed -> judge only the target rule code:
   - positive case + target hit -> `通过`;
   - positive case + target not hit -> `失败`;
   - negative case + target not hit -> `通过`;
   - negative case + target hit -> `失败`.

Never use final disposition or “any hit rule” as the result. A different rule hit does not make a positive case pass and does not make a negative case fail.

### 7. Archive and Update Output

For every case archive:

```json
{
  "row": 116,
  "rule_code": "ACQ_RS4_000020",
  "target_rule_set_code": "rs_acq_example",
  "case_type": "正案例",
  "planned_manifest": {},
  "normalized_test_data": {},
  "actual_history_requests": [],
  "history_responses": [],
  "actual_current_request": {},
  "current_response": {},
  "executed_rule_sets": [],
  "target_rule_hit": false,
  "status": "失败",
  "evidence": []
}
```

Use five result states: `通过`, `失败`, `执行阻塞`, `编排阻塞`, `无效用例`. Keep token ID and concise evidence in separate columns or remarks. Preserve workbook formatting, back up before edits, and write a new result file by default.

## Checkpoint Rules

- Key checkpoints by run ID, row, rule code, case type, and payload hash.
- Reuse a checkpoint only when the normalized payload hash and target metadata match.
- Resume only unfinished cases.
- Rerun only failed or inconclusive cases selected by analysis; never automatically rerun all cases.
- An interrupted or timed-out write may already have been accepted. Query its
  receipt before resubmission; a missing checkpoint is not proof of non-execution.
  Reuse a supported idempotency key only according to the endpoint contract.
- Poll pending evidence with bounded backoff and a deadline. At the deadline,
  archive the receipt and blocker; do not resubmit just to obtain a clearer result.
- After the execution gate passes, deliver. Repeat checks only for changed inputs,
  failed checks, or unresolved evidence, not merely for additional reassurance.

## Execution Gate

Execution is complete only when:

- [ ] every sent case passed semantic preflight;
- [ ] exact outbound history and current requests are archived;
- [ ] target rule-set execution was checked;
- [ ] status was determined from target rule and case type;
- [ ] blocked and invalid cases were kept separate from failures;
- [ ] output workbook and archive counts agree.

## Bundled Acquiring Executor

For the acquiring HTTP chain (`acqAuthorization` / `acqDecline` JSON POSTs whose
responses carry `mingFields` metric values), use the bundled executor instead of
hand-rolled replay scripts:

```bash
python3 ../scripts/acquiring_runner.py \
  --checkpoint <case1.json> --checkpoint <case2.json> \
  --output <run-dir> --registry <namespace-registry.json> \
  --namespace-prefix QW --settle 30 --dry-run
```

Behavior guarantees (verified by `test_acquiring_runner.py`):

- Isolation is registry-backed: a fresh run-id token (`PREFIX_MMDD`, then `_2`,
  `_3`, …) and, when `--salt-rows` is enabled, a per-case row-number digit salt
  from an unused 9xx pool are allocated and recorded in the registry so no two
  runs reuse the same namespace. Token remap and digit salt apply to every
  string field, covering IDs that embed the padded row number.
- Time rebasing shifts every event by one uniform offset
  (`now − old_current_biztime`), preserving relative intervals and window
  membership; short windows therefore expire naturally between runs.
- Preflight compares `预期当前笔字段` after applying the same remap to the
  expected values, and checks `bizid` uniqueness across the plan. A mismatch is
  reported as `preflight_failed` before any request is sent.
- History events are sent first, sorted by rebased `biztime`, then a bounded
  settle wait (`--settle`, default 30s) lets metric windows materialize before
  the current transaction.
- Metric readiness is diagnosed, not guessed: `metric_null_env` means the metric
  returned null (environment regression — do not retry; the runner groups cases
  where the same aggregation kind is null across ≥2 rows into
  `environment_regression` in the summary), while `suspected_ingest_lag` means a
  numeric value below plan (a fresh-namespace rerun is safe).
- Five-state classification is delegated to `classify-execution-result.js` via
  the Noah-independent archive shape the emitter produces; never route acquiring
  archives through `governance.py classify`.
- Runs are resumable: a completed case writes `rowNNN/result.json` with a
  complete flag; rerunning the same output directory skips finished cases unless
  `--force` is given.
- `--dry-run` plans and validates the full payload set (namespace allocation,
  remap, rebase, uniqueness) without sending anything. Always dry-run first and
  archive the plan before live execution.
- The checkpoint design gate (`--design <acq-design.json>`, O2b) is opt-in and
  inert when omitted. When supplied, each checkpoint is validated against
  `$defs/acqCheckpoint` and matched to an approved design case by `caseKey`; a
  checkpoint that is absent from the design or contradicts its contract is
  classified `无效用例` with reasonCode `checkpoint_design_mismatch` before any
  namespace token is allocated. The same design file feeds
  `governance.py aggregate-acquiring --design` to compute `coverageGaps`. See
  [references/governance-cli.md](governance-cli.md) §3b for the contract shape.

Read [references/acquiring-hlb-profile.md](acquiring-hlb-profile.md) only for HLB Acquiring work. Do not apply its endpoints or enums to other projects.
