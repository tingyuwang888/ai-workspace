#!/usr/bin/env node

const assert = require('assert');
const { classifyExecutionResult } = require('./classify-execution-result');

function archive(overrides = {}) {
  return {
    rule_code: 'TARGET_RULE',
    target_rule_set_code: 'target_set',
    case_type: '正案例',
    current_response: {
      success: true,
      data: {
        nodeResults: [{
          nodeType: 'RuleSetServiceNode',
          result: { ruleSetCode: 'target_set', hitRules: [{ ruleCode: 'TARGET_RULE' }] },
        }],
      },
    },
    ...overrides,
  };
}

assert.strictEqual(classifyExecutionResult(archive()).status, '通过');

assert.strictEqual(classifyExecutionResult(archive({
  current_response: {
    success: true,
    data: {
      nodeResults: [{
        nodeType: 'RuleSetServiceNode',
        result: { ruleSetCode: 'target_set', hitRules: [{ id: 'TARGET_RULE' }] },
      }],
    },
  },
})).status, '通过');

assert.strictEqual(classifyExecutionResult(archive({
  case_type: '反案例',
  current_response: {
    success: true,
    data: {
      hitRules: [{ ruleCode: 'UNRELATED_RULE' }],
      nodeResults: [{
        nodeType: 'RuleSetServiceNode',
        result: { ruleSetCode: 'target_set', hitRules: [{ ruleCode: 'UNRELATED_RULE' }] },
      }],
    },
  },
})).status, '通过');

assert.strictEqual(classifyExecutionResult(archive({
  current_response: {
    success: true,
    data: {
      nodeResults: [{
        nodeType: 'RuleSetServiceNode',
        result: { ruleSetCode: 'immunity_set', hitRules: [{ ruleCode: 'IMMUNITY_RULE' }] },
      }],
    },
  },
})).status, '编排阻塞');

assert.strictEqual(classifyExecutionResult(archive({
  current_response: { success: false, message: 'timeout' },
})).status, '执行阻塞');

assert.strictEqual(classifyExecutionResult(archive({
  request_consistency_errors: ['Expected amount 1499, sent 3500'],
})).status, '无效用例');

assert.strictEqual(classifyExecutionResult(archive({
  case_type: '反案例',
})).status, '失败');

console.log('classify-execution-result tests passed');
