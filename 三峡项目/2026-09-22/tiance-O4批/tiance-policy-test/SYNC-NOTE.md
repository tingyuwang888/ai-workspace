# O1+O3 + O2 + O4 + desensitization sync staging (2026-09-22)

Four hardened batches, verified byte-identical between QW and Codex installs,
tree scan clean of POC IPs / customer tags (guarded by test_desensitized.py).

O1+O3 (five-state vocabulary single-source + node preflight):
- references/governance.schema.json  (+fiveState enum, +reasonCodes registry)
- scripts/governance.py              (STATUSES now schema-driven)
- scripts/acquiring_runner.py        (+preflight_node, +--allow-missing-node)
- scripts/classify-execution-result.js (unchanged; dependency of runner/tests)
- scripts/test_acquiring_runner.py   (+TestNodePreflight)
- scripts/test_status_vocabulary.py  (new drift guard)

O2 (acquiring-chain aggregate scoring; translation only, never re-judgement):
- scripts/governance.py              (+aggregate_acquiring, +aggregate-acquiring CLI,
                                      +reasonCode merge preflight_failed>runner_error>
                                      classifier_error>diagnosis head>status default)
- scripts/acquiring_runner.py        (STATUSES now schema-driven, +make_case_key
                                      acq-{row:03d}-{rule}, runner_summary.json contract)
- references/governance.schema.json  (reasonCodes.acquiring += preflight_failed)
- references/governance-cli.md       (+section 3b Acquiring-Chain Aggregate Scoring)
- SKILL.md                           (dual-chain governed-results note)
- scripts/test_governance_aggregate.py (new, 18 tests incl. validate-rerun front door)
- scripts/test_acquiring_runner.py   (+TestMakeCaseKey, +TestSummaryArtifact)
- scripts/test_status_vocabulary.py  (guard tuple += preflight_failed)
- ../tiance-agent-loop/SKILL.md      (routing: classify=platform chain,
                                      aggregate-acquiring=acquiring chain)
- coverageGaps stays [] until O2b freezes acquiring checkpoint design contracts.

O4 (per-contract metric-window settle; replaces the global fixed dead-wait):
- scripts/acquiring_runner.py        (+load_settle_config / parse_metric_window_seconds
                                      / resolve_settle_seconds; --settle default now auto
                                      + --settle-config; settle threaded through
                                      run_checkpoint result.json + planned_requests.json;
                                      sleep only when settle["seconds"] > 0)
- config.json                        (+acquiring.settle: defaultSeconds30 factor1.5
                                      floorSeconds5 capSeconds120 naturalDaySeconds60)
- config.example.json                (mirror acquiring.settle + English settleNote)
- references/acquiring-hlb-profile.md (+Metric-Window Settle section)
                                      [NOTE: this is a customer-identified doc kept
                                       only in the live skill + private archive; NOT
                                       shipped in this generic publish subset]
- scripts/test_acquiring_runner.py   (+TestSettlePerContract, 10 tests: window parse,
                                      clamp bounds, natural-day, multi-metric max,
                                      no-suffix fallback, --settle override, config
                                      merge/fail-loud, dry-run archives settle)
- Settle priority: explicit --settle <sec> > auto (derive from indicator window suffix
  _5m/_2h/_1d, take slowest, clamp) > defaultSeconds fallback. All params externalized;
  no hardcoded seconds. Existing runner behavior unchanged when a window can't be
  inferred (falls back to 30s == old default).

Desensitization (env externalization; local values live only in ~/.zshrc):
- config.json                        (platform.host/db.host now $ENV: placeholders)
- SKILL.md                           (prerequisite #4 documents 3 env exports)
- scripts/discover_strategy.py       (+_resolve_env, --host > TIANCE_PLATFORM_HOST > config)
- scripts/fixture_manager.py         (fail-loud hint when $ENV: var unset)
- scripts/verify_result.py           (doc example host de-identified)
- scripts/execute_tests.py           (doc/help hosts de-identified)
- scripts/test_desensitized.py       (new sensitive-literal + $ENV: config guard)

Tests: 259/259 pass on both sides (baseline 222 + 2 desensitization guards
+ 25 O2 + 10 O4 settle tests).

Target repo: gitlab.tongdun.cn agent-OS/TD_AI-testing (empty as of 2026-09-22).

Remaining publish gate: strategies/*.json are customer policy profiles — must be
replaced by strategies/_example.json (or excluded) before full-package push.
config.json itself is now publishable (placeholders only); real values are in
~/.zshrc (TIANCE_PLATFORM_HOST / TIANCE_DB_HOST / TIANCE_DB_PASS) and must never
be committed. Repo-topology decisions (repo name / generic-family repo / naming)
still pending sign-off.

Push these files once topology is decided, e.g.:
  git clone https://gitlab.tongdun.cn/agent-OS/TD_AI-testing.git && cd TD_AI-testing
  mkdir -p packages/tiance-policy-test/skills/tiance-policy-test/{scripts,references}
  cp <staging>/scripts/* packages/.../scripts/ && cp <staging>/references/* packages/.../references/
  git add -A && git commit -m "[2026-09-22] tiance-policy-test O1+O3 hardening + desensitization" && git push
