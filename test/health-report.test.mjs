import test from 'node:test';
import assert from 'node:assert/strict';
import { assessHealth } from '../infra/health-report.mjs';

const healthy = { name: 'gateway', healthy: true };
const goodBackup = { verified: true, ageHours: 2 };
const goodDelegation = { state: 'succeeded' };

const okInput = () => ({
  services: [healthy],
  backup: { ...goodBackup },
  delegation: { ...goodDelegation },
});

test('a fully nominal snapshot is ok with no issues', () => {
  const result = assessHealth(okInput());
  assert.deepEqual(result, { status: 'ok', issues: [] });
});

test('an unhealthy service is degraded', () => {
  const result = assessHealth({ ...okInput(), services: [{ name: 'litellm', healthy: false }] });
  assert.equal(result.status, 'degraded');
  assert.ok(result.issues.length > 0);
});

test('a null service flag is unknown, never healthy', () => {
  assert.equal(assessHealth({ ...okInput(), services: [{ name: 'gateway', healthy: null }] }).status, 'unknown');
  assert.equal(assessHealth({ ...okInput(), services: [{ name: 'gateway' }] }).status, 'unknown');
});

test('a string flag is not coerced to a boolean', () => {
  assert.equal(assessHealth({ ...okInput(), services: [{ name: 'gateway', healthy: 'false' }] }).status, 'unknown');
  assert.equal(assessHealth({ ...okInput(), services: [{ name: 'gateway', healthy: 'true' }] }).status, 'unknown');
});

test('an empty or missing service list is unknown', () => {
  assert.equal(assessHealth({ ...okInput(), services: [] }).status, 'unknown');
  const withoutServices = okInput();
  delete withoutServices.services;
  assert.equal(assessHealth(withoutServices).status, 'unknown');
});

test('an unverified backup is degraded and a missing flag is unknown', () => {
  assert.equal(assessHealth({ ...okInput(), backup: { verified: false, ageHours: 2 } }).status, 'degraded');
  assert.equal(assessHealth({ ...okInput(), backup: { ageHours: 2 } }).status, 'unknown');
  assert.equal(assessHealth({ ...okInput(), backup: { verified: null, ageHours: 2 } }).status, 'unknown');
});

test('a stale backup is degraded and a broken age is unknown', () => {
  assert.equal(assessHealth({ ...okInput(), backup: { verified: true, ageHours: 27 } }).status, 'degraded');
  assert.equal(assessHealth({ ...okInput(), backup: { verified: true, ageHours: 26 } }).status, 'ok');
  assert.equal(assessHealth({ ...okInput(), backup: { verified: true } }).status, 'unknown');
  assert.equal(assessHealth({ ...okInput(), backup: { verified: true, ageHours: -1 } }).status, 'unknown');
  assert.equal(assessHealth({ ...okInput(), backup: { verified: true, ageHours: NaN } }).status, 'unknown');
  assert.equal(assessHealth({ ...okInput(), backup: null }).status, 'unknown');
});

test('delegation states map to degraded or unknown', () => {
  assert.equal(assessHealth({ ...okInput(), delegation: { state: 'succeeded' } }).status, 'ok');
  assert.equal(assessHealth({ ...okInput(), delegation: { state: 'failed' } }).status, 'degraded');
  assert.equal(assessHealth({ ...okInput(), delegation: { state: 'cancelled' } }).status, 'degraded');
  assert.equal(assessHealth({ ...okInput(), delegation: { state: 'running' } }).status, 'unknown');
  assert.equal(assessHealth({ ...okInput(), delegation: {} }).status, 'unknown');
});

test('degraded takes precedence over unknown and ok', () => {
  const result = assessHealth({
    services: [{ name: 'gateway', healthy: false }, { name: 'worker', healthy: null }],
    backup: { verified: true, ageHours: 1 },
    delegation: { state: 'running' },
  });
  assert.equal(result.status, 'degraded');
});

test('a malformed or missing input never becomes a success', () => {
  assert.equal(assessHealth(undefined).status, 'unknown');
  assert.equal(assessHealth(null).status, 'unknown');
  assert.equal(assessHealth('ok').status, 'unknown');
  assert.equal(assessHealth([]).status, 'unknown');
});

test('the report never echoes raw input or extra fields', () => {
  const secret = 'TEST_ONLY_SECRET_CANARY';
  const result = assessHealth({
    services: [{ name: 'gateway', healthy: false, note: secret }],
    backup: { verified: true, ageHours: 1, path: 'D:/private/backup.aes' },
    delegation: { state: 'failed', detail: secret },
    internalToken: secret,
    raw: { anything: secret },
  });
  const serialized = JSON.stringify(result);
  assert.ok(!serialized.includes(secret));
  assert.ok(!serialized.includes('backup.aes'));
  assert.deepEqual(Object.keys(result).sort(), ['issues', 'status']);
  assert.ok(result.issues.every(issue => typeof issue === 'string'));
});

test('the input is not mutated', () => {
  const input = okInput();
  const snapshot = JSON.stringify(input);
  assessHealth(input);
  assert.equal(JSON.stringify(input), snapshot);
});

// Regressions finales : des champs sensibles ajoutes sont exclus et l'entree
// n'est jamais modifiee.
test('token/password fields are excluded and the input is unchanged', () => {
  const input = {
    services: [
      { name: 'gateway', healthy: false, token: 'tok-live-123', password: 'pw-live-456' },
      { name: 'worker', healthy: null, token: 'tok-live-789' },
    ],
    backup: { verified: true, ageHours: null, token: 'tok-backup' },
    delegation: { state: 'running', password: 'pw-delegation' },
    token: 'tok-root',
    password: 'pw-root',
  };
  const snapshot = JSON.stringify(input);
  const result = assessHealth(input);
  assert.equal(JSON.stringify(input), snapshot, 'input must not be mutated');
  const serialized = JSON.stringify(result);
  for (const leak of ['tok-live-123', 'pw-live-456', 'tok-live-789', 'tok-backup', 'pw-delegation', 'tok-root', 'pw-root']) {
    assert.ok(!serialized.includes(leak), 'leaked: ' + leak);
  }
  assert.deepEqual(Object.keys(result).sort(), ['issues', 'status']);
});

// Regressions finales : aucun texte arbitraire provenant de service.name ou
// d'un delegation.state inconnu ne doit etre recopie dans le rapport.
test('arbitrary service.name and unknown delegation.state are not echoed', () => {
  const injected = '<script>alert(1)</script> evil-token-xyz';
  const result = assessHealth({
    services: [{ name: injected, healthy: false }],
    backup: { verified: true, ageHours: 1 },
    delegation: { state: injected },
  });
  const serialized = JSON.stringify(result);
  assert.ok(!serialized.includes(injected));
  assert.ok(!serialized.includes('evil-token-xyz'));
  assert.ok(!serialized.includes('<script>'));
  assert.ok(result.issues.some(issue => issue.includes('services[0]')));
});
