# Dependencies

The engine is plain Markdown + small Python utils, but the **worker procedure** leans on a few Claude
Code skills/plugins. They are not vendored here — declare and install them per machine. Most live in
the personal plugins repo **`rrrutledge/rrrutledge-claude-code-plugins`** (adjust if yours differ).

| Dependency | Level | Why the engine needs it | Source |
| --- | --- | --- | --- |
| **document-authoring** | engine | The single voice SSOT. `worker-core.md` step 5 appends every send's lesson to its Voice learning loop. | rrrutledge-claude-code-plugins |
| **message-draft** | engine | All draft mechanics (voice, composer targeting, never-send) for every channel. `worker-core.md` step 4. | rrrutledge-claude-code-plugins |
| **trello-outreach** | behavioral | "Waiting on someone else → tracker card" (`worker-core.md` step 6). Also backs the outreach source's board reads. | rrrutledge-claude-code-plugins |
| **browser-chauffeur** | provider / machine | Only needed on a machine whose providers harvest or draft via the browser (e.g. the work machine). API/MCP-only machines don't need it. | rrrutledge-claude-code-plugins |

**Levels:**
- **engine** — assumed by the shared worker procedure on every machine.
- **behavioral** — required to honor a standing rule (tracker cards).
- **provider / machine** — needed only by specific providers; declare it in *that machine's* local
  setup, not as a core requirement.

Runtime libs: the bundled `scripts/` use the Python stdlib (`urllib`, `json`, `winreg` on Windows)
plus **PyYAML** (`pip install pyyaml`) to read `.claude/drainer.local.md`. Credentials come from the
environment (`TRELLO_KEY`, `TRELLO_TOKEN`, etc.).

If you run on a machine without one of these skills, the dependent step degrades: note the gap to the
user rather than failing the whole drain.
