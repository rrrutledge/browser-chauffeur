// Tests for the drainer seen-state helper. Run: node --test seen-state.test.js
const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const {
  isSeen, record, openCount, clear, queueAdd, queueList, queueClear, staleList, requeue,
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

test('record is idempotent', () => {
  const dir = tmpDir();
  record(dir, 'outlook-graph', 'id-1', 'needs-you');
  record(dir, 'outlook-graph', 'id-1', 'needs-you');
  assert.strictEqual(openCount(dir, 'outlook-graph'), 1);
});

test('corrupt seen file is treated as nothing seen (no throw)', () => {
  const dir = tmpDir();
  fs.writeFileSync(path.join(dir, 'seen.json'), '{ this is not json');
  assert.strictEqual(isSeen(dir, 'outlook-graph', 'id-1'), false);
});

test('missing runtime dir is treated as nothing seen (no throw)', () => {
  const dir = path.join(tmpDir(), 'does-not-exist-yet');
  assert.strictEqual(isSeen(dir, 'outlook-graph', 'id-1'), false);
  assert.strictEqual(openCount(dir, 'outlook-graph'), 0);
});

test('open-count reflects needs-you records minus cleared', () => {
  const dir = tmpDir();
  record(dir, 'outlook-graph', 'a', 'needs-you');
  record(dir, 'outlook-graph', 'b', 'needs-you');
  record(dir, 'outlook-graph', 'c', 'fyi'); // fyi is not a worker tab
  assert.strictEqual(openCount(dir, 'outlook-graph'), 2);
  clear(dir, 'outlook-graph', 'a');
  assert.strictEqual(openCount(dir, 'outlook-graph'), 1);
});

test('open-count is per-source', () => {
  const dir = tmpDir();
  record(dir, 'outlook-graph', 'a', 'needs-you');
  record(dir, 'gmail', 'b', 'needs-you');
  assert.strictEqual(openCount(dir, 'outlook-graph'), 1);
  assert.strictEqual(openCount(dir, 'gmail'), 1);
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

// Helper: write a captured items/<id>.json with a ts so stale-list can age it.
function writeItem(dir, id, source, ts, extra = {}) {
  const itemsDir = path.join(dir, 'items');
  fs.mkdirSync(itemsDir, { recursive: true });
  fs.writeFileSync(path.join(itemsDir, `${id}.json`),
    JSON.stringify({ id, source, ts, ...extra }, null, 2));
}

test('stale-list surfaces only dispatched needs-you older than the threshold', () => {
  const dir = tmpDir();
  const old = new Date(Date.now() - 30 * 3600 * 1000).toISOString();   // 30h ago
  const fresh = new Date(Date.now() - 2 * 3600 * 1000).toISOString();  // 2h ago
  record(dir, 'outlook-graph', 'stale-old', 'needs-you');
  writeItem(dir, 'stale-old', 'outlook-graph', old, { subject: 'old ask' });
  record(dir, 'outlook-graph', 'fresh-one', 'needs-you');
  writeItem(dir, 'fresh-one', 'outlook-graph', fresh);
  record(dir, 'outlook-graph', 'done-one', 'needs-you');
  writeItem(dir, 'done-one', 'outlook-graph', old);
  clear(dir, 'outlook-graph', 'done-one');                          // cleared -> excluded
  record(dir, 'outlook-graph', 'fyi-one', 'fyi');                   // not needs-you -> excluded

  const stale = staleList(dir, 12);
  assert.strictEqual(stale.length, 1);
  assert.strictEqual(stale[0].id, 'stale-old');
  assert.strictEqual(stale[0].item.subject, 'old ask');
  assert.ok(stale[0].ageHours >= 29 && stale[0].ageHours <= 31);
});

test('stale-list ages off the id timestamp when items json is missing', () => {
  const dir = tmpDir();
  record(dir, 'outlook-graph', 'outlook-graph-20200101-000000-x', 'needs-you');
  const stale = staleList(dir, 12);                                    // year 2020 -> very stale
  assert.strictEqual(stale.length, 1);
  assert.strictEqual(stale[0].item, null);
  assert.ok(stale[0].ageHours > 1000);
});

test('stale-list is empty when nothing is overdue', () => {
  const dir = tmpDir();
  const fresh = new Date(Date.now() - 1 * 3600 * 1000).toISOString();
  record(dir, 'outlook-graph', 'fresh', 'needs-you');
  writeItem(dir, 'fresh', 'outlook-graph', fresh);
  assert.deepStrictEqual(staleList(dir, 12), []);
});

test('requeue frees the slot and lets the orphaned item re-dispatch (drops its seen key)', () => {
  const dir = tmpDir();
  record(dir, 'trello', 'card-1', 'needs-you');
  assert.strictEqual(openCount(dir, 'trello'), 1);
  assert.strictEqual(isSeen(dir, 'trello', 'card-1'), true);

  requeue(dir, 'trello', 'card-1');
  assert.strictEqual(openCount(dir, 'trello'), 0);            // slot freed
  assert.strictEqual(isSeen(dir, 'trello', 'card-1'), false); // key dropped -> re-enumerates

  // Re-dispatch next cycle then orphan again: requeue stays idempotent in effect (key gone, slot free).
  record(dir, 'trello', 'card-1', 'needs-you');
  requeue(dir, 'trello', 'card-1');
  assert.strictEqual(isSeen(dir, 'trello', 'card-1'), false);
  assert.strictEqual(openCount(dir, 'trello'), 0);
});

test('requeue on an unknown id is a no-op (no throw)', () => {
  const dir = tmpDir();
  requeue(dir, 'trello', 'nope');
  assert.strictEqual(isSeen(dir, 'trello', 'nope'), false);
});
