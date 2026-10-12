import test from 'node:test';
import assert from 'node:assert/strict';
import {approvalChecks} from '../infra/telegram-approval-evidence.mjs';

const idle = {permissions: [], status: 'idle', completed: true};
const denied = {terminal_reason: 'user', resolver_kind: 'channel', status: 'denied', decision: 'deny'};
const allowed = {...denied, status: 'allowed', decision: 'allow-once'};
const blocked = {calls: 1, completed: 0, outputMatches: false};
const executed = {calls: 1, completed: 1, outputMatches: true};
const passed = checks => Object.values(checks).every(Boolean);

test('expiration cannot masquerade as a human denial', () => {
  const timeout = {...denied, status: 'expired', terminal_reason: 'timeout', resolver_kind: 'system'};
  assert.equal(passed(approvalChecks('deny', blocked, idle, [timeout])), false);
  assert.equal(passed(approvalChecks('deny', blocked, idle, [])), false);
  assert.equal(passed(approvalChecks('deny', blocked, idle, [{...denied, resolver_kind: 'device'}])), false);
});

test('human denial requires a settled task with no execution', () => {
  assert.equal(passed(approvalChecks('deny', blocked, idle, [denied])), true);
  assert.equal(passed(approvalChecks('deny', executed, idle, [denied])), false);
  assert.equal(passed(approvalChecks('deny', blocked, {...idle, permissions: [{}]}, [denied])), false);
});

test('an accepted deny fixture qualifies only as an actual one-time authorization', () => {
  assert.equal(passed(approvalChecks('deny', executed, idle, [allowed])), false);
  assert.equal(passed(approvalChecks('allow', executed, idle, [allowed])), true);
});

test('authorization alone does not prove single execution and real output', () => {
  assert.equal(passed(approvalChecks('allow', blocked, idle, [allowed])), false);
  assert.equal(passed(approvalChecks('allow', {...executed, calls: 2, completed: 2}, idle, [allowed])), false);
  assert.equal(passed(approvalChecks('allow', {...executed, outputMatches: false}, idle, [allowed])), false);
  assert.equal(passed(approvalChecks('allow', executed, idle, [{...allowed, decision: 'allow-always'}])), false);
});
