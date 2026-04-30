# browser-chauffeur

Claude Code skill that teaches Claude to perform tasks on any website using an iterative inspect → interact → verify loop. Claude is your chauffeur — you give directions, Claude drives.

## What it does

- Navigates to a page, inspects it via accessibility snapshot, and performs the steps you describe
- Adapts when the UI changes or an overlay blocks interaction
- Optionally writes a reusable Node.js script once a flow is verified
- Recovers from script failures by re-entering discovery mode
- Two modes: MCP Playwright tools (Mode A) for public sites, Node.js CDP scripts (Mode B) for SSO-protected apps

## Prerequisite

Requires the **playwright MCP plugin**:

```
/plugin marketplace add playwright
/plugin install playwright@playwright-cli
```

## Install

```
/plugin marketplace add rrrutledge/browser-chauffeur
/plugin install browser-chauffeur@browser-chauffeur
```

## Usage

Just describe what you want to do on a website:

> "Use browser-chauffeur to go to [site] and [task]."

Or let Claude auto-invoke it when you describe a browser task.

## Skill trigger

Auto-invokes when you ask Claude to perform a task on a website — filling a form, clicking through a workflow, navigating a web app, or extracting information.
