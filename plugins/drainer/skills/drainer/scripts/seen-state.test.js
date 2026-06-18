// Tests for the drainer seen-state helper. Run: node --test seen-state.test.js
const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const {
  isSeen, record, openCount, clear, queueAdd, queueList, queueClear,
} = require('./seen-state');

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'seenstate-'));
}

test('record then isSeen returns true', () => {
  const dir = tmpDir();
  record(dir, 'personal-outlook', 'id-1', 'needs-you');
  assert.strictEqual(isSeen(dir, 'personal-outlook', 'id-1'), true);
});

test('unknown id returns false', () => {
  const dir = tmpDir();
  assert.strictEqual(isSeen(dir, 'personal-outlook', 'nope'), false);
});

test('record is idempotent', () => {
  const dir = tmpDir();
  record(dir, 'personal-outlook', 'id-1', 'needs-you');
  record(dir, 'personal-outlook', 'id-1', 'needs-you');
  assert.strictEqual(openCount(dir, 'personal-outlook'), 1);
});

test('corrupt seen file is treated as nothing seen (no throw)', () => {
  const dir = tmpDir();
  fs.writeFileSync(path.join(dir, 'seen.json'), '{ this is not json');
  assert.strictEqual(isSeen(dir, 'personal-outlook', 'id-1'), false);
});

test('missing runtime dir is treated as nothing seen (no throw)', () => {
  const dir = path.join(tmpDir(), 'does-not-exist-yet');
  assert.strictEqual(isSeen(dir, 'personal-outlook', 'id-1'), false);
  assert.strictEqual(openCount(dir, 'personal-outlook'), 0);
});

test('open-count reflects needs-you records minus cleared', () => {
  const dir = tmpDir();
  record(dir, 'personal-outlook', 'a', 'needs-you');
  record(dir, 'personal-outlook', 'b', 'needs-you');
  record(dir, 'personal-outlook', 'c', 'fyi'); // fyi is not a worker tab
  assert.strictEqual(openCount(dir, 'personal-outlook'), 2);
  clear(dir, 'personal-outlook', 'a');
  assert.strictEqual(openCount(dir, 'personal-outlook'), 1);
});

test('open-count is per-source', () => {
  const dir = tmpDir();
  record(dir, 'personal-outlook', 'a', 'needs-you');
  record(dir, 'gmail', 'b', 'needs-you');
  assert.strictEqual(openCount(dir, 'personal-outlook'), 1);
  assert.strictEqual(openCount(dir, 'gmail'), 1);
});

test('digest queue add / list / clear round-trips', () => {
  const dir = tmpDir();
  queueAdd(dir, 'personal-outlook', 'q1', { subject: 'Sale!', triage: 'junk' });
  queueAdd(dir, 'personal-outlook', 'q2', { subject: 'FYI memo', triage: 'fyi' });
  let q = queueList(dir);
  assert.strictEqual(q.length, 2);
  assert.strictEqual(q[0].id, 'q1');
  assert.strictEqual(q[0].source, 'personal-outlook');
  assert.strictEqual(q[0].item.subject, 'Sale!');
  queueClear(dir, 'q1');
  q = queueList(dir);
  assert.strictEqual(q.length, 1);
  assert.strictEqual(q[0].id, 'q2');
});

test('queue-list on empty/missing dir returns []', () => {
  const dir = path.join(tmpDir(), 'empty');
  assert.deepStrictEqual(queueList(dir), []);
});
