# browser-chauffeur

A [Claude Code](https://claude.ai/code) plugin marketplace for **browser-chauffeur** — a skill that teaches Claude to reliably perform tasks on any website.

Claude is your chauffeur — you give directions, Claude drives. The skill provides a self-healing methodology: inspect the page, interact step-by-step, verify each action, and autonomously recover when things go wrong.

## Quick start

```
/plugin marketplace add rrrutledge/browser-chauffeur
/plugin install browser-chauffeur@browser-chauffeur
```

### Prerequisite

The skill requires the **playwright MCP plugin** for browser control:

```
/plugin marketplace add playwright
/plugin install playwright@playwright-cli
```

## How it works

The skill operates in two modes:

- **Mode A** (MCP Playwright tools) — for public websites or apps without corporate SSO. Opens a fresh Chromium window.
- **Mode B** (Node.js CDP scripts) — for SSO-protected apps. Connects to an existing Chrome or Edge session via the Chrome DevTools Protocol.

### Key capabilities

- **Self-healing recovery** — when a script fails, Claude reads diagnostic screenshots, diagnoses the issue, fixes the script, and retries automatically
- **Overlay dismissal** — detects and dismisses cookie banners, first-run prompts, and other blockers
- **Iframe detection** — finds content hidden in iframes (common in enterprise SPAs)
- **Semantic selectors** — uses aria-labels and roles instead of brittle CSS classes
- **Verification** — always confirms actions succeeded before moving on

## License

MIT
