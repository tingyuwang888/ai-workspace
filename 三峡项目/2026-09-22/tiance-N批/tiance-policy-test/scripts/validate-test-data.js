#!/usr/bin/env node

const path = require('path');
const { spawnSync } = require('child_process');

const script = path.join(__dirname, 'validate-test-data.py');
const candidates = [process.env.RISK_RULE_PYTHON, 'python3'].filter(Boolean);
let lastError;

for (const python of candidates) {
  const result = spawnSync(python, [script, ...process.argv.slice(2)], { stdio: 'inherit' });
  if (!result.error) process.exit(result.status ?? 1);
  lastError = result.error;
}

console.error(`Unable to start Python validator: ${lastError?.message ?? 'unknown error'}`);
process.exit(1);
