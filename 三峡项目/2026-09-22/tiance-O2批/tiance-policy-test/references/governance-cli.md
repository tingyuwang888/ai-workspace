# Executable Governance

The shared risk-governance.md defines domain semantics. The commands below now
enforce schema, prepared-input binding, target-scoped classification, counts and
rerun eligibility. They do not prove an agent's semantic review or invent rule
branches. The agent must establish rule semantics, history/fixture readiness and
review evidence before declaring the design approved.

Requires Python 3.8+ and `jsonschema` (available in this installation), plus the
existing Tiance runtime dependencies. Run the following commands from the
tiance-policy-test skill directory, using absolute paths for task artifacts.

## 1. Reviewed Design

Keep generated candidates unchanged. Each now has a stable `caseKey`, separate
from sequential display `id`. Add `assertionKind`, explicit rule `expectedHit`,
reviewed targets and evidence to the approved prepared subset. Use the existing
prepare_testcases.py first, then review its resolved defaults and final params.
For a rule use explicit branchIds; a scenario hash is NOT a proven logical branch.

The machine-readable contract is [governance.schema.json](governance.schema.json).
This minimal example tests a direct input; attach the complete domain design and
readiness evidence in designReview.evidenceRefs for historical/fixture cases:

```json
{
  "schemaVersion": "1.0",
  "runId": "run-20260907-a",
  "cases": [{
    "id": "TC_001",
    "caseKey": "case-generated-stable-key",
    "assertionKind": "rule",
    "policyCode": "P001",
    "policyVersion": 1,
    "bizType": 1,
    "targetRuleSet": "RS001",
    "targetRule": "R001",
    "expectedHit": true,
    "expectedParams": {"amount": 1499},
    "expectedEvidence": {},
    "branchIds": ["positive"],
    "designReview": {
      "status": "approved",
      "evidenceRefs": ["design-review.json#/TC_001"]
    }
  }],
  "coveragePlan": [{
    "policyCode": "P001",
    "targetRuleSet": "RS001",
    "targetRule": "R001",
    "branchId": "positive",
    "caseKeys": ["case-generated-stable-key"]
  }]
}
```

`expectedParams` is the complete final params object, not just selected fields.
The prepared case must have the same id/caseKey, targets, assertionKind,
expectedHit and expectedEvidence. `designReview.status=approved` is a human/agent
attestation with source references, not an automatic mathematical proof.

Other assertion kinds: function (typed node/field/value contracts), path (a
nonempty array of exact rule-set codes), decision (expectedDecision platform
code), data (thirdPartyNodes contracts). Do not relabel data-value tests as path
tests merely because the legacy report module is decision-flow coverage.

```bash
python3 scripts/governance.py validate-design \
  --manifest /path/design-manifest.json --testcases /path/testcases.prepared.json
```

The coveragePlan is frozen from requested scope, not inferred from surviving
candidates. Empty caseKeys retain an unavailable rule/branch as a coverage gap.
For a selected subset create a reviewed subset manifest: cases exactly match
the selected inputs; retain scope branches, intersect their caseKeys with the
subset, and keep original full-run artifacts for the final coverage ledger.

## 2. Submission and Recovery

```bash
python3 scripts/execute_tests.py \
  --host HOST --cookie COOKIE --strategy-config /path/strategy.json \
  --testcases /path/testcases.prepared.json \
  --design-manifest /path/design-manifest.json \
  --output /path/new-run/results.json --max-retry 0
```

The design manifest is REQUIRED by the CLI. The executor rechecks prepared input
and policy identity before submission. An existing output is not silently
overwritten. No new bypass flag exists; legacy orchestrator.py and raw batch JS
are not governed entrypoints.

Every attempt is atomically saved before POST. Raw responses and returned
UUID/token are saved before evidence queries. A local parsing/storage failure
after submission cannot retry the POST. Timeouts are submission_unknown and are
not automatically retried even with a positive max-retry. Default max-retry is 0;
explicit retries apply only to definite server-error API rejections without a
returned UUID/token.
An exclusive output lock prevents overlapping writers; resume also compares the
supplied snapshot with the latest durable archive. Do not delete a live .lock
file. Failed evidence refresh preserves earlier logs in componentLogHistory and
records the new query in evidenceAttempts instead of erasing the old evidence.

```bash
python3 scripts/execute_tests.py \
  --host HOST --cookie COOKIE --strategy-config /path/strategy.json \
  --testcases /path/testcases.prepared.json \
  --design-manifest /path/design-manifest.json \
  --output /path/existing-run/results.json --resume --run-id run-20260907-a
```

Resume requires the same host, strategy, version, business type, runId and full
case digest (including params, assertion, targets and fixture contract). Completed
checkpoints are reused; accepted requests awaiting evidence only query their
saved token. Uncertain/rejected submissions, corrupt files or legacy checkpoints
without full identity block recovery. Resolve uncertain server-side outcomes
before creating a separately reviewed rerun. Changing external Fixture state
requires a new runId even if the JSON input is identical.

## 3. Five-State Results

```bash
python3 scripts/governance.py classify \
  --manifest /path/design-manifest.json --results /path/results.json \
  --output /path/governed-results.json
```

Classification reads actual form bytes/hash, response identity, raw component
logs, complete target hit details and typed contracts. It does not trust native
pass/assertionStatus. It includes unsubmitted manifest cases, rejects duplicate
or unknown archive identities, and reports counts, both pass-rate denominators,
coverage gaps and fullSuccess. The output file must be new. Zero denominators
are null (display N/A), never 100 percent.
The submission response must contain token and UUID; componentLogToken must
match that receipt. Old evidence without this query binding is blocked until
recaptured. Non-boolean success, non-string rule IDs and absent output values
cannot satisfy an assertion. Unknown contract fields, non-finite numbers and
JSON boolean/number substitutions are rejected rather than silently normalized.

Malformed/missing hit details or incomplete logs cannot prove a negative pass.
A complete wrong route fails a path assertion; a skipped target in a rule test
is an orchestration block. Observed wrong values fail assertions; missing values
needed as evidence remain blocked. Repeated/ambiguous target instances require
additional identity evidence and cannot automatically pass.

Add evidence-based root causes, confidence, owners and next actions separately
in analysis.json. Do not derive platform defects from status alone. Native Excel
formatting follows [report-delivery.md](report-delivery.md); authoritative
governance values use this JSON, not old native pass values. Fixed templates
need not add governance sheets. The report linter remains a separate quality check.

## 3b. Acquiring-Chain Aggregate Scoring

The acquiring chain (acquiring_runner.py, HLB direct HTTP) is a separate
execution path from the platform chain. Its per-case archives are already
classified by the shared five-state classifier; aggregate-acquiring only
translates those archives into a governed-results-isomorphic report. It never
re-judges status and never accepts platform-chain results.json files.

```bash
python3 scripts/governance.py aggregate-acquiring \
  --run-root /path/acq-run --output /path/governed-results.json \
  [--run-id acq-20260922-a]
```

Input is the runner output directory containing `row*/result.json` archives.
The output file must be new. `runId` defaults to `acq-{run-root directory
name}`. Each case is keyed by `caseKey = acq-{row:03d}-{rule_code}` (falls
back to `acq-misc{NNN}` when row/rule identity is missing); duplicates are
rejected. The report carries the same contract fields as the platform-chain
classify output: counts, planned, strictCompletionRate, validExecutionPassRate
(zero denominators are null, never 100 percent), fullSuccess and
environmentRegression (carried through from the runner diagnosis).

The merged `reasonCode` priority is: `preflight_failed` > `runner_error` >
`classifier_error` (detected in diagnosis codes or the classification evidence
text) > first diagnosis code > status default (通过→assertion_satisfied,
失败→assertion_mismatch, 编排阻塞→target_skipped, 无效用例→preflight_failed,
执行阻塞→execution_not_confirmed).

`coverageGaps` is intentionally `[]` until O2b freezes the acquiring
checkpoint design contract; the report is already a valid `--report` input for
validate-rerun (caseKey/runId/counts checks pass).

## 4. Reviewed Minimal Rerun

```json
{
  "schemaVersion": "1.0",
  "previousRunId": "run-20260907-a",
  "runId": "run-20260907-b",
  "actions": [{
    "caseKey": "case-generated-stable-key",
    "approved": true,
    "reasonKind": "data_fix",
    "evidenceRefs": ["analysis.json#/case-generated-stable-key"],
    "preservedIntent": "Keep the original positive boundary assertion",
    "newIsolationRefs": ["fixtures-run-b.json"]
  }]
}
```

```bash
python3 scripts/governance.py validate-rerun \
  --plan /path/rerun-plan.json --report /path/governed-results.json
```

Eligible reasons are data_fix, platform_change and prerequisite_change. The
command rejects passed/unknown/duplicate targets, missing confirmation/evidence,
unchanged runId and missing isolation/intent. It never submits, repairs data or
changes expected values. Generate and review new prepared inputs before rerun.

Generator --feedback must target stable caseKey when regenerating candidates.
The apply_feedback helper also supports exact IDs on an already finalized case
list, but never guesses by rule/scenario text. The whole feedback batch validates
before mutation. adjustExpected/removeCases require approved=true and evidenceRefs.
Preserve original coverage and all attempts; combine reviewed rerun conclusions
by caseKey without replacing unrelated passed cases.
