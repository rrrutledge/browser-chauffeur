// Tests for the drainer seen-state helper. Run: node --test seen-state.test.js
const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const {
  isSeen, record, queueAdd, queueList, queueClear, requeue,
} = require('./seen-state');

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'seenstate-'));
}

test('record then isSeen returns true', () => {
  const dir = tmpDir();
  record(dir, 'outlook-graph', 'id-1', 'needs-you');
  assert.strictEqual(isSeen(dir, 'outlook-graph', 'id-1'), true);
});

test('unknown id returns false', () => {
  const dir = tmpDir();
  assert.strictEqual(isSeen(dir, 'outlook-graph', 'nope'), false);
});

test('record keeps the triage it was first dispatched under', () => {
  const dir = tmpDir();
  record(dir, 'outlook-graph', 'id-1', 'needs-you');
  record(dir, 'outlook-graph', 'id-1', 'fyi');
  const seen = JSON.parse(fs.readFileSync(path.join(dir, 'seen.json'), 'utf8'));
  assert.deepStrictEqual(seen['outlook-graph']['id-1'], { triage: 'needs-you' });
});

test('record is per-source', () => {
  const dir = tmpDir();
  record(dir, 'outlook-graph', 'a', 'needs-you');
  assert.strictEqual(isSeen(dir, 'outlook-graph', 'a'), true);
  assert.strictEqual(isSeen(dir, 'gmail', 'a'), false);
});

test('corrupt seen file is treated as nothing seen (no throw)', () => {
  const dir = tmpDir();
  fs.writeFileSync(path.join(dir, 'seen.json'), '{ this is not json');
  assert.strictEqual(isSeen(dir, 'outlook-graph', 'id-1'), false);
});

test('missing runtime dir is treated as nothing seen (no throw)', () => {
  const dir = path.join(tmpDir(), 'does-not-exist-yet');
  assert.strictEqual(isSeen(dir, 'outlook-graph', 'id-1'), false);
});

test('digest queue add / list / clear round-trips', () => {
  const dir = tmpDir();
  queueAdd(dir, 'outlook-graph', 'q1', { subject: 'Sale!', triage: 'junk' });
  queueAdd(dir, 'outlook-graph', 'q2', { subject: 'FYI memo', triage: 'fyi' });
  let q = queueList(dir);
  assert.strictEqual(q.length, 2);
  assert.strictEqual(q[0].id, 'q1');
  assert.strictEqual(q[0].source, 'outlook-graph');
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

test('requeue drops the seen key so the item re-enumerates', () => {
  const dir = tmpDir();
  record(dir, 'trello', 'card-1', 'needs-you');
  assert.strictEqual(isSeen(dir, 'trello', 'card-1'), true);

  requeue(dir, 'trello', 'card-1');
  assert.strictEqual(isSeen(dir, 'trello', 'card-1'), false);

  // Re-dispatch next cycle then find it unfinished again: requeue stays idempotent in effect.
  record(dir, 'trello', 'card-1', 'needs-you');
  requeue(dir, 'trello', 'card-1');
  assert.strictEqual(isSeen(dir, 'trello', 'card-1'), false);
});

test('requeue on an unknown id is a no-op (no throw)', () => {
  const dir = tmpDir();
  requeue(dir, 'trello', 'nope');
  assert.strictEqual(isSeen(dir, 'trello', 'nope'), false);
});
