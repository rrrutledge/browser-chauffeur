"""zoom poller adapter — Zoom AI Companion meeting summaries (Zoom REST + OAuth), fully self-contained.

Everything generic to Zoom lives HERE — the REST calls, the OAuth token read/refresh, the
template/instance walk, the next_steps parsing, and the fan-out. Nothing about any particular user or
project: credentials come from config + environment variables, exactly like the gmail / slack / trello
adapters. Anyone who has a Zoom account with AI Companion summaries can enable this source by filling in
`providers.zoom` in their `.claude/drainer.local.md` and setting the Zoom OAuth secret in the environment.

**Fan-out without a ProviderBase change.** A Zoom meeting summary is naturally *1 meeting → N action items
assigned to the user + 1 recap*. The poller loop is one candidate → one stable_id → one worker tab, so the
fan-out happens in `enumerate`: one candidate per owner-assigned next step (recap folded into each for
context) plus one recap candidate for the meeting. Same shape as the trello adapter turning one board into
many card-items — `capture()` still writes exactly one `<iid>.json`, so no ProviderBase extension is needed.

Auth (Zoom Server-to-Server / OAuth app):
- `providers.zoom.client_id` in drainer.local.md (the OAuth app's Client ID — not a secret).
- `ZOOM_CLIENT_SECRET` in the environment (the secret).
- A refresh token: bootstrapped from `ZOOM_REFRESH_TOKEN` on first run, then cached (and rotated) in the
  token-cache file (`providers.zoom.token_cache`, default `<runtime_dir>/zoom-tokens.json`). The access
  token is auto-refreshed when it nears expiry.

Implements `../engine/provider.md`; classify by `../engine/triage.md`. Prose: `zoom-provider.md`.
id prefix: `zoom-`; body file: `<id>.zoom.md`.
"""
import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from provider_base import ProviderBase, ProviderError, slug  # noqa: E402

ZOOM_API = "https://api.zoom.us"
ZOOM_OAUTH = "https://zoom.us/oauth/token"
_STEP_LINK = re.compile(
    r"- ([^\n]+?)\[\]\(https://tasks\.zoom\.us\?meetingId=([^&\s)]+)&stepId=([0-9a-f-]+)\)")


def _hash(text, n=6):
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:n]


def _http(method, url, headers=None, data=None, timeout=45):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


class Provider(ProviderBase):
    name = "zoom"

    def __init__(self):
        self.runtime_dir = None
        self.client_id = None
        self.token_cache = None
        self.owner_names = []            # display-name tokens whose next_steps are "the user's"
        self.lookback_hours = 48
        self.cooldown_minutes = 30       # a summary is "final" only once unmodified this long
        self.poll_interval_minutes = 20  # self-throttle: skip the heavy template walk between cycles
        self._me_names = None            # /users/me-derived owner names, resolved lazily

    # --------------------------------------------------------------- config
    def configure(self, cfg):
        self.runtime_dir = cfg.get("runtime_dir")
        block = self._zoom_block(cfg.get("repo"))
        self.client_id = self._str_knob(block, "client_id") or os.environ.get("ZOOM_CLIENT_ID")
        self.owner_names = self._list_knob(block, "owner_names")
        self.lookback_hours = self._int_knob(block, "lookback_hours", self.lookback_hours)
        self.cooldown_minutes = self._int_knob(block, "cooldown_minutes", self.cooldown_minutes)
        self.poll_interval_minutes = self._int_knob(block, "poll_interval_minutes", self.poll_interval_minutes)
        cache = self._str_knob(block, "token_cache")
        if cache:
            self.token_cache = os.path.expanduser(os.path.expandvars(cache))
        elif self.runtime_dir:
            self.token_cache = os.path.join(self.runtime_dir, "zoom-tokens.json")

    @staticmethod
    def _zoom_block(repo):
        if not repo:
            return ""
        try:
            with open(os.path.join(repo, ".claude", "drainer.local.md"), encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return ""
        out, in_block = [], False
        for line in text.splitlines():
            if re.match(r"^  zoom\s*:\s*$", line):
                in_block = True
                continue
            if in_block:
                if re.match(r"^  \S", line) or re.match(r"^\S", line):
                    break
                out.append(line)
        return "\n".join(out)

    @staticmethod
    def _int_knob(block, key, default):
        m = re.search(rf"^\s*{re.escape(key)}\s*:\s*(\d+)\s*$", block, re.MULTILINE)
        return int(m.group(1)) if m else default

    @staticmethod
    def _str_knob(block, key):
        m = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.+?)\s*$", block, re.MULTILINE)
        return m.group(1).strip().strip('"\'') if m else None

    @staticmethod
    def _list_knob(block, key):
        m = re.search(rf"^\s*{re.escape(key)}\s*:\s*\[(.*?)\]\s*$", block, re.MULTILINE)
        if not m or not m.group(1).strip():
            return []
        return [x.strip().strip('"\'') for x in m.group(1).split(",") if x.strip()]

    # --------------------------------------------------------------- OAuth token
    def _read_cache(self):
        try:
            with open(self.token_cache, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError, TypeError):
            return {}

    def _write_cache(self, data):
        if not self.token_cache:
            return
        os.makedirs(os.path.dirname(self.token_cache), exist_ok=True)
        tmp = f"{self.token_cache}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.token_cache)

    @staticmethod
    def _age_seconds(obtained_at):
        try:
            t = datetime.fromisoformat((obtained_at or "").replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - t).total_seconds()
        except (ValueError, TypeError):
            return 1e12

    def _access_token(self):
        """Return a fresh Zoom access token, refreshing (and rotating the refresh token in the cache)
        when the cached one is near expiry. Bootstraps from ZOOM_REFRESH_TOKEN if the cache has none."""
        cache = self._read_cache()
        if cache.get("access_token") and self._age_seconds(cache.get("obtained_at")) < 3500:
            return cache["access_token"]
        return self._refresh(cache.get("refresh_token") or os.environ.get("ZOOM_REFRESH_TOKEN"))

    def _refresh(self, refresh_token):
        if not refresh_token:
            raise ProviderError(
                "zoom: no refresh token — set ZOOM_REFRESH_TOKEN (first run) or point token_cache at an "
                "existing Zoom token file.", kind="config")
        secret = os.environ.get("ZOOM_CLIENT_SECRET")
        if not self.client_id or not secret:
            raise ProviderError(
                "zoom: set providers.zoom.client_id in drainer.local.md and ZOOM_CLIENT_SECRET in the "
                "environment.", kind="config")
        auth = base64.b64encode(f"{self.client_id}:{secret}".encode()).decode()
        body = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": refresh_token}).encode()
        status, text = _http("POST", ZOOM_OAUTH, {
            "Authorization": "Basic " + auth,
            "Content-Type": "application/x-www-form-urlencoded",
        }, body)
        data = json.loads(text) if text else {}
        if status != 200 or data.get("error"):
            raise ProviderError(
                f"zoom token refresh failed: {data.get('error') or status} {data.get('reason', '')}".strip(),
                kind="auth")
        self._write_cache({
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token") or refresh_token,  # rotates each refresh
            "token_type": data.get("token_type"),
            "expires_in": data.get("expires_in"),
            "scope": data.get("scope"),
            "obtained_at": datetime.now(timezone.utc).isoformat(),
        })
        return data.get("access_token")

    # --------------------------------------------------------------- Zoom REST
    def _get(self, token, path):
        status, text = _http("GET", ZOOM_API + path, {
            "Authorization": "Bearer " + token, "Content-Type": "application/json"})
        try:
            return status, json.loads(text)
        except ValueError:
            return status, text

    def _owner_tokens(self, token):
        """Whose next_steps count as the user's: the configured owner_names, else the authed account's
        own name from /users/me (first name + display name), so a fresh install works with no name config."""
        if self.owner_names:
            return self.owner_names
        if self._me_names is None:
            self._me_names = []
            status, me = self._get(token, "/v2/users/me")
            if status == 200 and isinstance(me, dict):
                for key in ("first_name", "display_name"):
                    v = (me.get(key) or "").strip()
                    if v:
                        self._me_names.append(v.split()[0] if key == "display_name" else v)
        return self._me_names

    def _collect_instances(self, token, from_ts, to_ts):
        """Every previousMeetings template + its past instances whose start_time is in [from_ts, to_ts]
        (ISO UTC strings compare lexically), de-duped by occurrence uuid."""
        templates, page_token = [], ""
        while True:
            qs = f"type=previousMeetings&page_size=300{('&next_page_token=' + page_token) if page_token else ''}"
            status, body = self._get(token, f"/v2/users/me/meetings?{qs}")
            if status != 200:
                raise ProviderError(f"zoom list-meetings failed: HTTP {status} {str(body)[:150]}", kind="auth")
            templates.extend(body.get("meetings", []) or [])
            page_token = body.get("next_page_token") or ""
            if not page_token:
                break
        out = {}
        for m in templates:
            st = m.get("start_time")
            # A meeting's own listed uuid is its *scheduled* uuid, not necessarily the uuid of the
            # occurrence that actually ran — Zoom mints a distinct occurrence uuid once a meeting is
            # started, for one-time (type 2) meetings too, and the summary endpoint only recognizes that
            # occurrence uuid. So resolve via past_meetings/instances for every meeting, regardless of
            # type, and only fall back to the listed uuid if that call finds nothing in-window.
            found = False
            status, body = self._get(token, f"/v2/past_meetings/{m.get('id')}/instances")
            if status == 200:
                for inst in body.get("meetings", []) or []:
                    ist = inst.get("start_time")
                    if ist and from_ts <= ist <= to_ts and inst.get("uuid") not in out:
                        out[inst["uuid"]] = {"topic": m.get("topic"), "uuid": inst["uuid"],
                                             "id": m.get("id"), "start_time": ist}
                        found = True
            if not found and st and from_ts <= st <= to_ts and m.get("uuid") not in out:
                out[m["uuid"]] = {"topic": m.get("topic"), "uuid": m["uuid"], "id": m.get("id"), "start_time": st}
        return sorted(out.values(), key=lambda x: x["start_time"])

    @staticmethod
    def _step_ids(summary_content):
        """{normalized bullet text -> (stepId, meetingIdEnc)} from summary_content. Steps are grouped by
        person in the HTML, so the bullet order differs from next_steps[] — match by TEXT, not index."""
        out = {}
        for m in _STEP_LINK.finditer(summary_content or ""):
            out[re.sub(r"\s+", " ", m.group(1)).strip()] = (m.group(3), m.group(2))
        return out

    def _assignee_is_owner(self, line, owner_tokens):
        i = line.find(":")
        assignee = line[:i] if i != -1 else ""
        return any(re.search(rf"\b{re.escape(n)}\b", assignee, re.I) for n in owner_tokens)

    # --------------------------------------------------------------- self-throttle
    def _throttle_path(self):
        return os.path.join(self.runtime_dir, "zoom-poll-state.json") if self.runtime_dir else None

    def _throttled(self):
        p = self._throttle_path()
        if not p:
            return False
        try:
            with open(p, encoding="utf-8") as f:
                last = datetime.fromisoformat(json.load(f)["last_run"])
        except (OSError, ValueError, KeyError):
            return False
        return (datetime.now(timezone.utc) - last).total_seconds() / 60 < self.poll_interval_minutes

    def _mark_run(self):
        p = self._throttle_path()
        if not p:
            return
        os.makedirs(self.runtime_dir, exist_ok=True)
        tmp = f"{p}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"last_run": datetime.now(timezone.utc).isoformat()}, f)
        os.replace(tmp, p)

    # --------------------------------------------------------------- finalized-summary cache
    # A once-a-meeting summary is FINAL after the cooldown (Zoom stops refining it), so there's no reason to
    # re-fetch it every cycle for the whole lookback window. This client-side cache keeps each finalized
    # summary keyed by occurrence uuid — the drainer's own "already processed this meeting" record, the
    # counterpart to the teams provider's per-conversation message horizons. Candidates are still rebuilt
    # from the cached summary every cycle, so the poller's seen-state stays the single authority on what
    # gets dispatched (an item held at the concurrency cap still resurfaces) — the cache only skips the
    # network fetch, never the dedup.
    def _summary_cache_path(self):
        return os.path.join(self.runtime_dir, "zoom-summary-cache.json") if self.runtime_dir else None

    def _load_summary_cache(self):
        p = self._summary_cache_path()
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save_summary_cache(self, cache):
        p = self._summary_cache_path()
        if not p:
            return
        os.makedirs(self.runtime_dir, exist_ok=True)
        tmp = f"{p}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        os.replace(tmp, p)

    def _meeting_items(self, inst, s, owner_tokens):
        """Build the candidates for one meeting from its summary `s`: one recap + one per owner-assigned
        next step. Works identically whether `s` came from the network or the finalized-summary cache."""
        raw_steps = s.get("next_steps")
        all_steps = raw_steps if isinstance(raw_steps, list) else \
            [l for l in str(raw_steps or "").split("\n") if l.strip()]
        step_ids = self._step_ids(s.get("summary_content"))
        base = {
            "meetingId": inst["uuid"], "meetingNumericId": inst.get("id"), "topic": inst.get("topic"),
            "meetingStart": inst.get("start_time"), "meetingEnd": s.get("meeting_end_time"),
            "summaryModified": s.get("summary_last_modified_time") or s.get("summary_created_time"),
            "recap": s.get("summary_overview") or "", "allNextSteps": all_steps,
            "summaryDetails": s.get("summary_details") or [], "docUrl": s.get("summary_doc_url"),
        }
        out = [self._to_item({**base, "kind": "recap"})]
        for raw in [l for l in all_steps if self._assignee_is_owner(l, owner_tokens)]:
            step = re.sub(r"^[•\-*\s]+", "",
                          re.sub(r"^[•\-*\s]*[A-Za-z][\w .'-]*:\s*", "", raw)).strip()
            hit = step_ids.get(re.sub(r"\s+", " ", step).strip())
            task_url = f"https://tasks.zoom.us?meetingId={hit[1]}&stepId={hit[0]}" if hit else None
            out.append(self._to_item({**base, "kind": "action-item", "stepText": step,
                                      "stepId": hit[0] if hit else None, "taskUrl": task_url}))
        return out

    # --------------------------------------------------------------- the ProviderBase contract
    def enumerate(self, limit):
        if self._throttled():
            return []
        token = self._access_token()
        owner_tokens = self._owner_tokens(token)
        now = datetime.now(timezone.utc)
        from_ts = (now.timestamp() - self.lookback_hours * 3600)
        from_iso = datetime.fromtimestamp(from_ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        to_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        cache = self._load_summary_cache()
        items, in_window = [], set()
        for inst in self._collect_instances(token, from_iso, to_iso):
            uuid = inst["uuid"]
            in_window.add(uuid)
            s = (cache.get(uuid) or {}).get("summary")
            if s is None:  # not cached — fetch it
                enc = urllib.parse.quote(urllib.parse.quote(uuid, safe=""), safe="")
                status, fetched = self._get(token, f"/v2/meetings/{enc}/meeting_summary")
                if status != 200 or not isinstance(fetched, dict):
                    continue  # 404 = no AI summary; other non-200 = transient, retry next cycle
                modified = fetched.get("summary_last_modified_time") or fetched.get("summary_created_time")
                # Finality gate: the AI keeps refining a summary for tens of minutes after a meeting;
                # capturing early would miss next_steps added later. Until it's been quiet for
                # cooldown_minutes, don't cache it and don't emit — re-fetch next cycle until it settles.
                if modified and self._age_seconds(modified) < self.cooldown_minutes * 60:
                    continue
                s = fetched
                cache[uuid] = {"cached_at": to_iso, "summary": s}  # finalized -> never re-fetched
            items.extend(self._meeting_items(inst, s, owner_tokens))

        # Bound the cache to the current window — finalized summaries never change, and a meeting that has
        # aged out of the lookback window is done, so drop it rather than let the cache grow forever.
        self._save_summary_cache({u: e for u, e in cache.items() if u in in_window})
        items.sort(key=lambda it: it.get("received") or "", reverse=True)
        self._mark_run()
        return items[:limit]

    @staticmethod
    def _to_item(c):
        topic = c.get("topic") or "Zoom meeting"
        recap = c.get("recap") or ""
        if c.get("kind") == "action-item":
            step = c.get("stepText") or ""
            preview = (f"Zoom action item assigned to you, from the meeting \"{topic}\".\n"
                       f"Action: {step}\n\nMeeting recap (context): {recap[:600]}")
            subject = step[:120]
        else:
            n = len(c.get("allNextSteps") or [])
            preview = (f"Recap of the Zoom meeting \"{topic}\" (informational — nothing is asked of you by "
                       f"the recap itself; your action items from this meeting are tracked as their own "
                       f"separate drainer items). Recap: {recap[:800]}\n\nMeeting had {n} next step(s) total.")
            subject = f"Meeting recap: {topic}"
        item = dict(c)
        item.update({"from": topic, "subject": subject, "received": c.get("meetingStart"), "preview": preview})
        return item

    def stable_id(self, item):
        topic = slug(item.get("topic"), 20)
        mh = _hash(item.get("meetingId"))
        if item.get("kind") == "action-item":
            return f"{self.name}-{topic}-{mh}-{_hash(item.get('stepText'))}".strip("-")[:72]
        return f"{self.name}-{topic}-{mh}-recap".strip("-")[:72]

    def capture(self, item, iid, runtime_dir):
        items_dir = os.path.join(runtime_dir, "items")
        os.makedirs(items_dir, exist_ok=True)
        body_file = os.path.join(items_dir, f"{iid}.zoom.md")
        is_action = item.get("kind") == "action-item"
        url = (item.get("taskUrl") or item.get("docUrl")) if is_action else item.get("docUrl")

        steps = "\n".join(f"- {s}" for s in (item.get("allNextSteps") or [])) or "(none)"
        details = "\n\n".join(
            f"### {d.get('label', '')}\n{d.get('summary', '')}" for d in (item.get("summaryDetails") or [])
        ) or "(none)"
        action_block = f"## This action item (assigned to you)\n\n{item.get('stepText')}\n\n" if is_action else ""
        with open(body_file, "w", encoding="utf-8") as f:
            f.write(
                f"# {item.get('subject')}\n\n"
                f"Meeting: {item.get('topic')}\n"
                f"When: {item.get('meetingStart')} to {item.get('meetingEnd') or '?'}\n"
                f"Summary doc: {item.get('docUrl') or '(none)'}\n"
                f"Task link: {url or '(none)'}\n"
                f"MeetingId: {item.get('meetingId')}\n"
                f"StepId: {item.get('stepId') or '(none)'}\n\n"
                f"{action_block}"
                f"## Meeting recap\n\n{item.get('recap') or '(none)'}\n\n"
                f"## All next steps (whole meeting)\n\n{steps}\n\n"
                f"## Details\n\n{details}\n")

        record = {
            "id": iid, "source": self.name, "triage": item.get("_bucket", "needs-you"),
            "kind": item.get("_kind"), "zoomKind": item.get("kind"),
            "from": item.get("from"), "subject": item.get("subject"), "received": item.get("received"),
            "snippet": item.get("preview"), "url": url,
            "meetingId": item.get("meetingId"), "meetingTopic": item.get("topic"),
            "stepId": item.get("stepId"), "stepText": item.get("stepText"),
            "bodyFile": body_file, "ts": datetime.now(timezone.utc).isoformat(),
        }
        json_file = os.path.join(items_dir, f"{iid}.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        return json_file
