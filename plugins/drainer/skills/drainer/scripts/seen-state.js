// Drainer seen-state helper - fail-safe processed-id store and digest queue.
//
// State lives under the project's runtime_dir (e.g. ~/Dev/personal-ai-pod/.tmp/drainer/):
//   seen.json          { "<source>": { "<id>": { "triage" } } }
//   digest-queue.json  [ { "id", "source", "item": {...} }, ... ]
//   reclassified.json  [ { "id", "source", "bucket" }, ... ] — items awaiting the poller's next-cycle dispatch
//
// seen.json answers one question - has this id been dispatched? - so an entry's presence is the whole
// signal and `triage` rides along as a human-readable label of how it was classified. Whether the work
// finished is read off the source object itself by the poller's reconcile, never tracked here.
//
// Fail-safe: a missing or corrupt file reads as "nothing seen / empty queue" — never throws,
// so the worst case is reprocessing an item, never silently dropping one. Writes are atomic
// (write a temp file, then rename over the target).
//
// CLI (the prose poller calls these):
//   node seen-state.js seen        <runtimeDir> <source> <id>             -> prints yes|no
//   node seen-state.js record      <runtimeDir> <source> <id> <triage>    -> records (idempotent)
//   node seen-state.js queue-add   <runtimeDir> <source> <id> <json-file> -> append a captured fyi/junk item to the digest queue
//   node seen-state.js queue-list  <runtimeDir>                          -> prints the queue as JSON
//   node seen-state.js queue-clear <runtimeDir> <id>                     -> removes one item from the queue
//   node seen-state.js requeue     <runtimeDir> <source> <id>            -> drop the seen key so the item re-enumerates and re-dispatches a fresh tab
//   node seen-state.js reclassify  <runtimeDir> <id> <needs-you|auto-handle>
//                                                                        -> correct a miscategorized fyi/junk item: retag items/<id>.json and its
//                                                                           seen-state entry to the new bucket, drop it from the digest queue, and
//                                                                           stage it in reclassified.json so the poller dispatches it next cycle
//                                                                           without re-running triage (the human verdict is authoritative)

const fs = require('fs');
const path = require('path');

const SEEN_FILE = 'seen.json';
const QUEUE_FILE = 'digest-queue.json';
const RECLASSIFIED_FILE = 'reclassified.json';
const RECLASSIFY_TARGETS = ['needs-you', 'auto-handle'];

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return fallback;
  }
}

function writeJsonAtomic(file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2));
  fs.renameSync(tmp, file);
}

function seenPath(runtimeDir) { return path.join(runtimeDir, SEEN_FILE); }
function queuePath(runtimeDir) { return path.join(runtimeDir, QUEUE_FILE); }
function reclassifiedPath(runtimeDir) { return path.join(runtimeDir, RECLASSIFIED_FILE); }
function itemPath(runtimeDir, id) { return path.join(runtimeDir, 'items', `${id}.json`); }

function loadSeen(runtimeDir) {
  const data = readJson(seenPath(runtimeDir), {});
  return (data && typeof data === 'object') ? data : {};
}

function loadQueue(runtimeDir) {
  const data = readJson(queuePath(runtimeDir), []);
  return Array.isArray(data) ? data : [];
}

function isSeen(runtimeDir, source, id) {
  const seen = loadSeen(runtimeDir);
  return Boolean(seen[source] && seen[source][id]);
}

function record(runtimeDir, source, id, triage) {
  const seen = loadSeen(runtimeDir);
  if (!seen[source]) seen[source] = {};
  // Idempotent: an id already recorded keeps the triage it was first dispatched under.
  if (!seen[source][id]) {
    seen[source][id] = { triage };
  }
  writeJsonAtomic(seenPath(runtimeDir), seen);
}

function queueAdd(runtimeDir, source, id, item) {
  const queue = loadQueue(runtimeDir);
  if (!queue.some(e => e.id === id)) {
    queue.push({ id, source, item });
    writeJsonAtomic(queuePath(runtimeDir), queue);
  }
}

function queueList(runtimeDir) {
  return loadQueue(runtimeDir);
}

function queueClear(runtimeDir, id) {
  const queue = loadQueue(runtimeDir).filter(e => e.id !== id);
  writeJsonAtomic(queuePath(runtimeDir), queue);
}

// Recovery: an item the poller's reconcile found unfinished - its source object still unhandled with no
// live worker session on it - is re-dispatched by DELETING its seen key, so the next enumerate no longer
// drops it as already-seen. No retry cap is needed: an item converges the moment its worker clears the
// source, because a cleared source object is no longer unhandled and the reconcile stops selecting it.
// (A still-relevant source item re-enumerates and re-dispatches; one that's no longer present simply
// doesn't come back.)
function requeue(runtimeDir, source, id) {
  const seen = loadSeen(runtimeDir);
  if (seen[source] && seen[source][id]) {
    delete seen[source][id];
    writeJsonAtomic(seenPath(runtimeDir), seen);
  }
}

// The human override for a triage miss: a fyi/junk item that should have been needs-you (or
// auto-handle) is stuck today, because fyi/junk items never spawn workers and the poller's reconcile
// explicitly skips the digest queue. This is the one-step correction — the human verdict is
// authoritative, so the poller dispatches the staged item next cycle without re-running triage on it.
function reclassify(runtimeDir, id, newBucket) {
  if (!RECLASSIFY_TARGETS.includes(newBucket)) {
    throw new Error(`reclassify target must be one of ${RECLASSIFY_TARGETS.join('/')} (got: ${newBucket})`);
  }
  const file = itemPath(runtimeDir, id);
  const item = readJson(file, null);
  if (item === null) throw new Error(`could not read captured item: ${file}`);
  const source = item.source;
  if (!source) throw new Error(`captured item ${id} has no "source" field: ${file}`);

  // Retag the captured item and its seen-state entry so both agree with the human verdict — a plain
  // record() would no-op here since the id is already present under its original (wrong) triage.
  item.triage = newBucket;
  writeJsonAtomic(file, item);
  const seen = loadSeen(runtimeDir);
  if (!seen[source]) seen[source] = {};
  seen[source][id] = { triage: newBucket };
  writeJsonAtomic(seenPath(runtimeDir), seen);

  // Drop it from the digest queue — it's no longer fyi/junk waiting on review.
  queueClear(runtimeDir, id);

  // Stage it for the poller's dispatch step, which loads this entry, spawns a worker straight off the
  // already-captured item.json (no re-enumeration, no re-triage), then removes the entry once dispatched.
  const staged = readJson(reclassifiedPath(runtimeDir), []).filter(e => e.id !== id);
  staged.push({ id, source, bucket: newBucket });
  writeJsonAtomic(reclassifiedPath(runtimeDir), staged);
}

module.exports = {
  isSeen, record, queueAdd, queueList, queueClear, requeue, reclassify,
};

if (require.main === module) {
  const [cmd, ...rest] = process.argv.slice(2);
  try {
    switch (cmd) {
      case 'seen':
        console.log(isSeen(rest[0], rest[1], rest[2]) ? 'yes' : 'no');
        break;
      case 'record':
        record(rest[0], rest[1], rest[2], rest[3]);
        console.log(`recorded ${rest[2]} (${rest[3]})`);
        break;
      case 'queue-add': {
        const item = readJson(rest[3], null);
        if (item === null) throw new Error(`could not read item JSON file: ${rest[3]}`);
        queueAdd(rest[0], rest[1], rest[2], item);
        console.log(`queued ${rest[2]}`);
        break;
      }
      case 'queue-list':
        console.log(JSON.stringify(queueList(rest[0]), null, 2));
        break;
      case 'queue-clear':
        queueClear(rest[0], rest[1]);
        console.log(`dequeued ${rest[1]}`);
        break;
      case 'requeue':
        requeue(rest[0], rest[1], rest[2]);
        console.log(`requeued ${rest[2]}`);
        break;
      case 'reclassify':
        reclassify(rest[0], rest[1], rest[2]);
        console.log(`reclassified ${rest[1]} -> ${rest[2]}`);
        break;
      default:
        throw new Error('Usage: seen-state.js <seen|record|queue-add|queue-list|queue-clear|requeue|reclassify> ...');
    }
  } catch (e) {
    console.error('Error:', e.message);
    process.exit(1);
  }
}
