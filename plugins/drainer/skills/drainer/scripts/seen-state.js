// Drainer seen-state helper — fail-safe processed-id store, needs-you status, and digest queue.
//
// State lives under the project's runtime_dir (e.g. ~/Dev/personal-ai-pod/.tmp/drainer/):
//   seen.json         { "<source>": { "<id>": { "triage", "status" } } }
//   digest-queue.json [ { "id", "source", "item": {...} }, ... ]
//
// Fail-safe: a missing or corrupt file reads as "nothing seen / empty queue" — never throws,
// so the worst case is reprocessing an item, never silently dropping one. Writes are atomic
// (write a temp file, then rename over the target).
//
// CLI (the prose poller calls these):
//   node seen-state.js seen        <runtimeDir> <source> <id>             -> prints yes|no
//   node seen-state.js record      <runtimeDir> <source> <id> <triage>    -> records (idempotent)
//   node seen-state.js open-count  <runtimeDir> <source>                  -> prints count of needs-you dispatched-not-cleared
//   node seen-state.js clear       <runtimeDir> <source> <id>            -> marks a needs-you item cleared
//   node seen-state.js queue-add   <runtimeDir> <source> <id> <json-file> -> append a captured fyi/junk item to the digest queue
//   node seen-state.js queue-list  <runtimeDir>                          -> prints the queue as JSON
//   node seen-state.js queue-clear <runtimeDir> <id>                     -> removes one item from the queue

const fs = require('fs');
const path = require('path');

const SEEN_FILE = 'seen.json';
const QUEUE_FILE = 'digest-queue.json';

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
  const status = triage === 'needs-you' ? 'dispatched' : 'queued';
  // Idempotent: do not clobber a richer existing status (e.g. an already-cleared item).
  if (!seen[source][id]) {
    seen[source][id] = { triage, status };
  }
  writeJsonAtomic(seenPath(runtimeDir), seen);
}

function openCount(runtimeDir, source) {
  const seen = loadSeen(runtimeDir);
  const items = seen[source] || {};
  let n = 0;
  for (const id of Object.keys(items)) {
    const r = items[id];
    if (r.triage === 'needs-you' && r.status === 'dispatched') n++;
  }
  return n;
}

function clear(runtimeDir, source, id) {
  const seen = loadSeen(runtimeDir);
  if (seen[source] && seen[source][id]) {
    seen[source][id].status = 'cleared';
    writeJsonAtomic(seenPath(runtimeDir), seen);
  }
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

module.exports = { isSeen, record, openCount, clear, queueAdd, queueList, queueClear };

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
      case 'open-count':
        console.log(String(openCount(rest[0], rest[1])));
        break;
      case 'clear':
        clear(rest[0], rest[1], rest[2]);
        console.log(`cleared ${rest[2]}`);
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
      default:
        throw new Error('Usage: seen-state.js <seen|record|open-count|clear|queue-add|queue-list|queue-clear> ...');
    }
  } catch (e) {
    console.error('Error:', e.message);
    process.exit(1);
  }
}
