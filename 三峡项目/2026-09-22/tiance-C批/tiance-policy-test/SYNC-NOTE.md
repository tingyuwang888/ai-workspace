# O1+O3 + O2 + O2b + O4 + O5 + desensitization sync staging (2026-09-22)

Six hardened batches, verified byte-identical between QW and Codex installs,
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

O2b (acquiring-chain checkpoint design gate; un-freezes coverageGaps; fully generic):
- references/governance.schema.json  (+$defs acqDesign/acqCase/acqCheckpoint;
                                      reasonCodes.acquiring += checkpoint_design_mismatch)
- scripts/acquiring_runner.py        (JSONSchema $defs wrapper validator;
                                      +validate_acq_design / load_acq_design /
                                      checkpoint_design_issues; +--design opt-in gate
                                      that pre-judges unmatched/contradicting checkpoints
                                      as 无效用例 with reasonCode checkpoint_design_mismatch
                                      before any namespace token is allocated)
- scripts/governance.py              (aggregate_acquiring gains design=None param;
                                      coverageGaps now computed from design coveragePlan
                                      (branch with no 通过/失败 case == gap) and gates
                                      fullSuccess; +--design CLI option; lazy import of
                                      validate_acq_design to avoid a cycle)
- references/governance-cli.md       (3b += "Acquiring-chain checkpoint design gate (O2b)"
                                      with acqDesign example + opt-in semantics)
- SKILL.md (live skill)              (dual-chain note += optional --design gate sentence)
- references/metric-execute.md (live) (Bundled Acquiring Executor guarantees += --design bullet)
- scripts/test_governance_aggregate.py (+TestCoverageGaps, 5 tests: no-design [],
                                      all-covered, failed counts as executed, uncovered
                                      branch gap, invalid design rejected)
- scripts/test_acquiring_runner.py   (+TestCheckpointDesignGate, 4 tests: matching design
                                      runs, ruleCode override blocked, absent checkpoint
                                      blocked, no-design unchanged)
- scripts/test_status_vocabulary.py  (guard tuple += checkpoint_design_mismatch)
- Gate is strictly OPT-IN: without --design both runner and aggregate behave
  byte-identically to the pre-O2b baseline, protecting the existing test suite.
  Schema + identity binding only — the agent still establishes semantics/readiness.

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

O5 (HLB acquiring profile made machine-readable / single source of truth):
- references/hlb_acquiring_profile.json  (NEW canonical profile: fixed fields, endpoints
  [AcqAuthorization/AcqDecline/AcqModify/AcqDisputes] with path+encoding+required groups,
  enums, time windows, isolation, field-mapping notes, known issues)
- scripts/validate-test-data.py          (ENDPOINTS/ENUMS no longer hardcoded; now derived
  at import from the JSON via _load_profile(); proven byte-equal to the pre-refactor literals)
- references/acquiring-hlb-profile.md    (reconciled: source-of-truth banner, v2.0.0,
  +AcqDecline endpoint row & field table, aligned encoding)
- scripts/test_hlb_profile.py            (NEW drift guard, 10 tests: validator ENDPOINTS/ENUMS
  == frozen canonical, JSON structural invariants, Markdown covers every endpoint path + enum code)
- SKILL.md                               (live-skill-only pointer to the JSON single source;
  NOT propagated to staging SKILL.md so the published copy carries no dangling links)
  [NOTE: O5 is entirely customer-identified (HLB). It ships ONLY in the live skill and the
   private ai-workspace archive — NONE of these files are added to this generic publish subset.
   validate-test-data.py is itself HLB-coupled, so it and its guard test stay out of staging too.
   If validate-test-data.py is ever generalized for publish, the profile must first become a
   non-customer template.]

Desensitization (env externalization; local values live only in ~/.zshrc):
- config.json                        (platform.host/db.host now $ENV: placeholders)
- SKILL.md                           (prerequisite #4 documents 3 env exports)
- scripts/discover_strategy.py       (+_resolve_env, --host > TIANCE_PLATFORM_HOST > config)
- scripts/fixture_manager.py         (fail-loud hint when $ENV: var unset)
- scripts/verify_result.py           (doc example host de-identified)
- scripts/execute_tests.py           (doc/help hosts de-identified)
- scripts/test_desensitized.py       (new sensitive-literal + $ENV: config guard)

Tests: live skill full suite is 279 (baseline 278 after O2b + 1 new customer-name
guard added in B4). The 10 O5 guards run only in the live skill (they import the
customer-identified validator/profile); the generic publish staging subset itself
stays customer-free (re-verified with test_desensitized.py against the refreshed
staging copy after O2b sync and again after B4).

B4 (publish-subset de-customerization — neutralize residual client name in generic
files that actually ship; approved "连 live 一起中性化"):
- SKILL.md L39                 ("HLB 端点/枚举" → "外部收单端点/枚举", live + staging)
- references/governance-cli.md L154 ("acquiring_runner.py, HLB direct HTTP"
                                 → "acquiring_runner.py, direct acquiring HTTP", live + staging)
- scripts/acquiring_runner.py L4 ("Executes HLB-style checkpoint contracts"
                                 → "Executes project-profile checkpoint contracts", live + staging)
- scripts/test_desensitized.py (NEW guard test_generic_files_free_of_customer_name:
                                 forbids the client name in every generic file except a
                                 documented allowlist of the deliberate customer assets;
                                 the guard's own regex/allowlist paths are assembled from
                                 string fragments so the shipped file carries no contiguous
                                 client token — same convention as the ccqt split. Kept
                                 byte-identical live↔staging.)
  KEEP unchanged (deliberately client-identified, live+private-archive only, never publish):
    references/hlb_acquiring_profile.json, references/acquiring-hlb-profile.md,
    scripts/validate-test-data.py, scripts/test_hlb_profile.py, scripts/test_validate_test_data.py,
    the live-only SKILL.md L40-44 single-source pointer, and live-only docs that reference the
    profile by name (risk-governance.md, metric-execute.md, metric-pipeline.md,
    test-data-contract.md). staging SYNC-NOTE.md retains the client name as the worklog that
    records the exclusion (allowlisted).
  Residual audit: after B4 the ONLY client-name occurrence in the staging subset is
  SYNC-NOTE.md; SKILL.md / governance-cli.md / acquiring_runner.py are clean and the
  standalone desensitized guard passes 3/3 there.

Two findings surfaced during B4 verification:
1. [FIXED by C] Publish-subset completeness: the staging scripts/ folder omitted
   result_evaluator.py, which governance.py imported at module scope, so the
   governance-dependent tests (test_governance_aggregate, test_status_vocabulary)
   errored at collection with ModuleNotFoundError; SKILL.md also referenced several
   scripts not shipped in staging, and discover_strategy.py was present but
   un-importable (missing http_client + config_generator). Fixed in C.
2. Codex install drift: ~/.codex/skills/tiance-policy-test still carries the three
   pre-B4 prose lines (SKILL.md L39, governance-cli.md L154, acquiring_runner.py L4)
   and its test_desensitized.py is the pre-B4 version. Propagating B4 to Codex overlaps
   the pending A-class whole-tree reverse-sync (Codex metric-* docs renamed internally,
   different script inventory), so it was deliberately left out of this live+staging batch.

C (publish-subset completeness — make the generic staging copy self-testable and
internally consistent; approved "执行" 2026-09-22):
- scripts/governance.py   (T1: the module-scope `from result_evaluator import
    complete_hit_evidence, select_rule_nodes, validate_evidence_contract` moved to a
    lazy import as the first statement of classify_case — its only consumer. This
    breaks governance's eager dependency on result_evaluator → comparison_engine
    (comparison_engine carries the customer post-guarantee policy codes and must NOT
    ship in the generic subset). The aggregate + status-vocabulary tests never execute
    classify_case, so they now collect and pass without those modules. Applied to BOTH
    live + staging; byte-identical. Runtime behavior unchanged — classify_case still
    loads result_evaluator when actually invoked.)
- scripts/{http_client,config_generator,mock_probe,platform_guard,prepare_testcases,
    submit_batch,decode_pls}.{py,js}
                          (T2: copied live→staging byte-identical. These are the
    platform-chain scripts SKILL.md already documents but staging was missing; copying
    them also makes discover_strategy.py importable again (it needs http_client +
    config_generator). All seven verified customer-free by test_desensitized.py's
    sensitive-literal + client-name guard.)
  NOT shipped to staging (deliberately): result_evaluator.py, comparison_engine.py —
  no longer needed after T1, and comparison_engine.py carries the post-guarantee
  project's policy-code map, so it stays live+private-archive only.
  Verification: staging full pytest 73 passed (was 40 collected + 2 collection errors);
  staging test_desensitized.py 3/3 (client-name guard green across the refreshed set);
  every shipped .py imports cleanly incl. discover_strategy; live full suite still
  279 passed and classify_case smoke-tested OK after the lazy-import edit; all copied
  files cmp-identical to live.

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
