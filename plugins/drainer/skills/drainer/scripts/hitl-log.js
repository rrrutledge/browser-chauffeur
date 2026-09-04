// Drainer HITL-signal helper - one self-reported line per worker, at close.
//
// Every worker appends one JSON line to <runtimeDir>/hitl-log.jsonl as its last act
// (see worker-core.md §8). The line is the worker's own read of how the item ended -
// the one thing a transcript can't reveal reliably: whether a human turn was a
// by-design approval Russell's rules reserve for him (load_bearing) or an avoidable
// rescue. The weekly pod-review miner prefers this precise signal when present and
// falls back to its transcript heuristic when a worker never reached a close (crash,
// still open), so the log upgrades precision without ever being load-bearing itself.
//
// Fail-safe, exactly like seen-state.js: a missing/corrupt item file or a missing
// session id never throws - the line is written with whatever is known, because a
// worker must never be blocked from closing by its own bookkeeping. The append is a
// single line write; concurrent workers each write one short line, so interleaving is
// a non-issue in practice.
//
// CLI:
//   node hitl-log.js <runtimeDir> <source> <id> <outcome> <loadBearing> [reason]
//     outcome     one of: self-closed | parked | help-needed | corrected
//     loadBearing true|false - were this item's human turns by-design (an approval /
//                 a decision only Russell can make), not avoidable friction?
//     reason      optional; falls back to the item's dispositionReason / helpNeeded.reason

const fs = require('fs');
const path = require('path');

const LOG_FILE = 'hitl-log.jsonl';
const OUTCOMES = new Set(['self-closed', 'parked', 'help-needed', 'corrected']);

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return fallback;
  }
}

function logHitl(runtimeDir, source, id, outcome, loadBearing, reason) {
  const item = readJson(path.join(runtimeDir, 'items', `${id}.json`), {}) || {};
  const help = (item && typeof item.helpNeeded === 'object') ? item.helpNeeded : null;
  const line = {
    session_id: process.env.CLAUDE_CODE_SESSION_ID || null,
    item_id: id,
    source: source || item.source || null,
    task: item.subject || item.task || item.title || id,
    outcome: OUTCOMES.has(outcome) ? outcome : outcome, // pass through even if unexpected, so nothing is lost
    load_bearing: loadBearing === true || loadBearing === 'true',
    // human_turns stays the transcript's job (the miner counts it authoritatively); a worker that
    // stamped its own count on the item rides it along, otherwise null.
    human_turns: Number.isInteger(item.humanTurns) ? item.humanTurns : null,
    reason: reason || item.dispositionReason || (help && help.reason) || '',
    disposition: item.disposition || null,
    timestamp: new Date().toISOString(),
  };
  const file = path.join(runtimeDir, LOG_FILE);
  fs.mkdirSync(runtimeDir, { recursive: true });
  fs.appendFileSync(file, JSON.stringify(line) + '\n');
  return line;
}

module.exports = { logHitl };

if (require.main === module) {
  const [runtimeDir, source, id, outcome, loadBearing, ...reasonParts] = process.argv.slice(2);
  if (!runtimeDir || !id || !outcome) {
    console.error('Usage: hitl-log.js <runtimeDir> <source> <id> <outcome> <loadBearing> [reason]');
    process.exit(1);
  }
  if (!OUTCOMES.has(outcome)) {
    // Not fatal - warn and still record, so a typo never costs the signal.
    console.error(`hitl-log: warning - unrecognized outcome "${outcome}" (expected one of ${[...OUTCOMES].join(', ')})`);
  }
  try {
    const line = logHitl(runtimeDir, source, id, outcome, loadBearing, reasonParts.join(' '));
    console.log(`logged HITL: ${id} -> ${line.outcome} (load_bearing=${line.load_bearing})`);
  } catch (e) {
    // Never block the worker's close on a logging failure.
    console.error('hitl-log: non-fatal error:', e.message);
    process.exit(0);
  }
}
