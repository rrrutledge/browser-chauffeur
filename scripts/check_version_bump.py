#!/usr/bin/env python
"""CI guardrail: every plugin with changed code/config/tests must bump its
version.

The failure this prevents: a behavior change lands under plugins/<name>/ while
plugins/<name>/.claude-plugin/plugin.json keeps the same version, so
`claude plugin update` (which keys off the version number) never re-pulls the
new source and the fix silently never ships.

For skill plugins the behavior IS markdown — `skills/**/SKILL.md` and
`commands/*.md` are the payload, not documentation. So a blanket "*.md is docs"
exemption would wave through exactly the changes that most need to ship (this is
the bug that let a SKILL.md voice-loop edit merge without a bump). The exemption
is therefore narrow: only genuine meta-docs (README, CHANGELOG, CONTRIBUTING,
LICENSE) and anything under a docs/ directory are bump-free. Everything else —
including any SKILL.md and command markdown — requires a bump.

Run in PR CI. Compares the PR head against the merge base:
  - Group changed files by their plugin directory.
  - Only genuine meta-doc changes (see is_doc_only) do not require a bump.
  - For every plugin with at least one behavior change, the `version` in its
    plugin.json must differ from the base. Brand-new plugins (no plugin.json in
    the base) are exempt.

Exit 0 = OK, exit 1 = a bump is missing. Base ref comes from $BASE_REF (CI sets
it from github.base_ref); falls back to origin/main.
"""
import json
import os
import subprocess
import sys


def git(*args):
    return subprocess.run(['git', *args], capture_output=True, text=True, check=True).stdout


def file_at(ref, path):
    """Return file contents at a git ref, or None if it doesn't exist there."""
    try:
        return subprocess.run(['git', 'show', f'{ref}:{path}'],
                              capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        return None


# Genuine meta-docs that don't change plugin behavior — safe to edit without a
# version bump. Everything else under a plugin (SKILL.md, commands/*.md, scripts,
# hooks, plugin.json) is treated as behavior and requires a bump.
DOC_BASENAMES = {'readme.md', 'changelog.md', 'contributing.md', 'license', 'license.md'}


def is_doc_only(path):
    parts = path.lower().split('/')
    if 'docs' in parts:
        return True
    return parts[-1] in DOC_BASENAMES


def version_of(ref, plugin):
    raw = file_at(ref, f'plugins/{plugin}/.claude-plugin/plugin.json')
    if raw is None:
        return None
    try:
        return json.loads(raw).get('version')
    except json.JSONDecodeError:
        return None


def main():
    base = os.environ.get('BASE_REF', 'origin/main')
    merge_base = git('merge-base', base, 'HEAD').strip()
    changed = [f for f in git('diff', '--name-only', f'{merge_base}..HEAD').splitlines() if f]

    # plugin name -> did a non-doc file change?
    touched = {}
    for f in changed:
        parts = f.split('/')
        if len(parts) < 2 or parts[0] != 'plugins':
            continue
        plugin = parts[1]
        touched[plugin] = touched.get(plugin, False) or not is_doc_only(f)

    failures = []
    for plugin, has_code_change in sorted(touched.items()):
        if not has_code_change:
            continue
        base_version = version_of(merge_base, plugin)
        if base_version is None:
            continue  # new plugin (or no manifest in base) — nothing to bump against
        head_version = version_of('HEAD', plugin)
        if head_version == base_version:
            failures.append((plugin, base_version))

    if failures:
        print('Version bump required — these plugins changed but kept the same version:\n')
        for plugin, version in failures:
            print(f'  - {plugin}: still {version} — bump plugins/{plugin}/.claude-plugin/plugin.json')
        print('\nBump the version so `claude plugin update` re-pulls the new source.')
        return 1

    print('OK: all changed plugins bumped their version (or changed docs only).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
