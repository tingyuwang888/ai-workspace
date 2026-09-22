#!/usr/bin/env node

const fs = require('fs');

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function responseData(response) {
  if (!isObject(response)) return {};
  return isObject(response.data) ? response.data : response;
}

function ruleCode(rule) {
  if (typeof rule === 'string') return rule;
  if (!isObject(rule)) return null;
  return rule.ruleCode ?? rule.rule_code ?? rule.code ?? rule.ruleId ?? rule.id ?? null;
}

function collectHitRules(value, output = new Set(), seen = new Set()) {
  if (!value || typeof value !== 'object' || seen.has(value)) return output;
  seen.add(value);
  if (Array.isArray(value)) {
    value.forEach((item) => collectHitRules(item, output, seen));
    return output;
  }
  if (Array.isArray(value.hitRules)) {
    value.hitRules.forEach((rule) => {
      const code = ruleCode(rule);
      if (code) output.add(String(code));
    });
  }
  Object.values(value).forEach((item) => collectHitRules(item, output, seen));
  return output;
}

function nodeResult(node) {
  if (!isObject(node)) return {};
  return isObject(node.result) ? node.result : node;
}

function nodeRuleSetCode(node) {
  const result = nodeResult(node);
  return result.ruleSetCode ?? result.rule_set_code ?? result.code ?? node.ruleSetCode ?? null;
}

function ruleSetNodes(response) {
  const data = responseData(response);
  const nodes = Array.isArray(data.nodeResults) ? data.nodeResults : [];
  return nodes.filter((node) => {
    const type = String(node?.nodeType ?? node?.type ?? '');
    return type === 'RuleSetServiceNode' || Boolean(nodeRuleSetCode(node));
  });
}

function hasExecutionFailure(archive) {
  if (archive.request_error || archive.transport_error || archive.timeout) return true;
  const response = archive.current_response;
  if (!isObject(response)) return true;
  if (response.success === false) return true;
  const status = Number(response.http_status ?? response.statusCode ?? 200);
  return Number.isFinite(status) && status >= 400;
}

function consistencyErrors(archive) {
  const errors = archive.request_consistency_errors
    ?? archive.consistency_errors
    ?? archive.validation_errors
    ?? [];
  if (Array.isArray(errors)) return errors.filter(Boolean).map(String);
  return errors ? [String(errors)] : [];
}

function classifyExecutionResult(archive) {
  const targetRule = archive.rule_code ?? archive.target_rule_code;
  const targetRuleSet = archive.target_rule_set_code ?? archive.rule_set_code;
  const caseType = archive.case_type;
  const evidence = [];

  if (!targetRule || !targetRuleSet || !['正案例', '反案例'].includes(caseType)) {
    return {
      status: '无效用例',
      target_rule_hit: null,
      target_rule_set_executed: null,
      executed_rule_sets: [],
      evidence: ['Missing target rule, target rule set, or valid case type'],
    };
  }

  const mismatch = consistencyErrors(archive);
  if (mismatch.length > 0) {
    return {
      status: '无效用例',
      target_rule_hit: null,
      target_rule_set_executed: null,
      executed_rule_sets: [],
      evidence: mismatch,
    };
  }

  if (hasExecutionFailure(archive)) {
    return {
      status: '执行阻塞',
      target_rule_hit: null,
      target_rule_set_executed: false,
      executed_rule_sets: [],
      evidence: ['Current request did not complete with a successful platform response'],
    };
  }

  const nodes = ruleSetNodes(archive.current_response);
  const executedRuleSets = nodes.map(nodeRuleSetCode).filter(Boolean).map(String);
  const targetNode = nodes.find((node) => String(nodeRuleSetCode(node)) === String(targetRuleSet));

  if (!targetNode) {
    const allHits = [...collectHitRules(responseData(archive.current_response))];
    if (allHits.length > 0) evidence.push(`Rules hit before target: ${allHits.join(', ')}`);
    evidence.push(`Target rule set not executed: ${targetRuleSet}`);
    return {
      status: '编排阻塞',
      target_rule_hit: false,
      target_rule_set_executed: false,
      executed_rule_sets: executedRuleSets,
      evidence,
    };
  }

  const targetHits = collectHitRules(nodeResult(targetNode));
  const targetRuleHit = targetHits.has(String(targetRule));
  const passed = caseType === '正案例' ? targetRuleHit : !targetRuleHit;
  evidence.push(`Target rule set executed: ${targetRuleSet}`);
  evidence.push(`Target rule ${targetRule} hit: ${targetRuleHit}`);

  return {
    status: passed ? '通过' : '失败',
    target_rule_hit: targetRuleHit,
    target_rule_set_executed: true,
    executed_rule_sets: executedRuleSets,
    evidence,
  };
}

function main() {
  const file = process.argv[2];
  if (!file) {
    console.error('Usage: node classify-execution-result.js <execution-archive.json>');
    process.exit(1);
  }
  if (!fs.existsSync(file)) {
    console.error(`File not found: ${file}`);
    process.exit(1);
  }
  let archive;
  try {
    archive = JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (error) {
    console.error(`Invalid JSON: ${error.message}`);
    process.exit(1);
  }
  console.log(JSON.stringify(classifyExecutionResult(archive), null, 2));
}

if (require.main === module) main();

module.exports = { classifyExecutionResult };
