# Common Anti-Patterns (Real Failures)

These are the failure modes the browser-chauffeur skill has hit in real automation runs. Read this file when you write a new script, when a click or selector fails unexpectedly, or when a script "completes" but the result didn't actually persist.

## Anti-Pattern 1: Text-Based Filters Match Multiple Elements

**Problem:**
```javascript
// ❌ Can match both parent <div> and child <button>
const btn = page.locator('button').filter({ hasText: /^Power-ups$/i });
await btn.click(); // Error: "locator resolved to 2 elements"
```

**Why it fails:** If a parent div contains the text "Power-ups" and so does the child button, the filter matches BOTH elements. Playwright strict mode requires exactly one match.

**Solution - Use semantic selectors instead:**
```javascript
// ✅ Much more reliable
const btn = page.getByRole('button', { name: /Power-ups/i });
await btn.click();
```

Prefer `getByRole`, `getByLabel`, `aria-label` over text filters.

## Anti-Pattern 2: page.evaluate Clicks Don't Trigger Framework Events

**Problem:**
```javascript
// ❌ Fires a native DOM click but does NOT trigger React/Fluent UI synthetic event handlers
await page.evaluate(() => {
  document.querySelector('button.confirm').click();
});
```

**Why it fails:** React, Angular, and Fluent UI use synthetic event systems that listen for events dispatched through the browser's event pipeline. A raw `element.click()` in evaluate fires a native DOM click that bypasses these frameworks. The UI may update visually (element disappears, dialog closes), but the framework never processes the action — so **no API call goes to the server**. The change vanishes on page refresh.

**Solution — Use Playwright's event dispatch:**
```javascript
// ✅ For unstable elements (menus that re-render and detach during click):
await locator.dispatchEvent('click');

// ✅ For elements that fail stability checks but are actually clickable:
await locator.click({ force: true });

// ✅ For stable elements (always prefer this):
await locator.click();
```

Use `page.evaluate` for **reading** DOM state (querying elements, checking visibility, extracting text). Never use it for **clicking** elements that trigger server-side actions.

## Anti-Pattern 3: Don't Diagnose Click Failures from Error Messages

**Problem:** When a click times out or fails with "intercepts pointer events", don't try to guess what's wrong from the error message.

**Solution - Look at the screenshot:**
```javascript
try {
  await element.click({ timeout: 5000 });
} catch (e) {
  // Take screenshot immediately
  await page.screenshot({ path: '.tmp/click-failed.png' });
  console.log('Click failed - see .tmp/click-failed.png');
  throw e;
}
```

Then **use the Read tool to view the screenshot**. You'll SEE what's actually blocking:
- Modal overlay in front of element
- Element scrolled out of view
- Wrong element selected
- Element not yet rendered

Diagnose visually, not from error text. Then fix based on what you SEE (dismiss overlay, scroll element into view, use better selector, add wait, etc.).

This applies to *silent* failures too — a click that executed without throwing but produced no navigation, no dialog, and no DOM change. The cause is usually an invisible overlay your click landed on instead of the target. **Before generating new diagnostic code, Read any screenshot you already took during the failed step.** Saving the file is not enough; opening it with the Read tool is the only way you'll see what the user sees.

## Anti-Pattern 4: Phantom Dialogs Left in the DOM with display:none

**Problem:**
```javascript
// ❌ Returns true even when dialogs are hidden
const stillOpen = await page.evaluate(() =>
  document.querySelector('[role="dialog"]') !== null
);
```

**Why it fails:** Many frameworks (Google products, Microsoft Fluent UI, Material) keep all dialog DOM nodes mounted and toggle `display: none` to hide inactive steps in a wizard. After a multi-step flow completes, you can find half a dozen hidden `[role="dialog"]` elements still in the DOM with stale text like "Choose a column to title your markers". Naive presence checks treat them as "still open" and the recovery loop spins.

**Solution — Filter by computed visibility:**
```javascript
const visibleDialogs = await page.evaluate(() => {
  return Array.from(document.querySelectorAll('[role="dialog"]')).filter(d => {
    const cs = getComputedStyle(d);
    return cs.display !== 'none' && cs.visibility !== 'hidden';
  }).map(d => d.innerText.slice(0, 200));
});
```

Apply the same `display`/`visibility` filter when looking for any element — backdrops, tooltips, menus often get the same treatment. Combine with `el.offsetParent !== null` for layout-aware visibility.

## Anti-Pattern 5: Role-Based Selectors Miss Semantic HTML Buttons

**Problem:**
```javascript
// ❌ Element is visible on the page, but selector finds nothing
const shareBtn = page.locator('[role="button"]').filter({ hasText: /^Share$/ });
await shareBtn.click(); // Times out — no match
```

**Why it fails:** Not every clickable element is wrapped in `[role="button"]`. Older or more semantic UIs use real HTML elements as their action targets — a toolbar may be `<ul><li>Share</li></ul>`, a link may be a real `<a>` with no role, a footer action may be a plain `<span>` with a click handler. `getByRole('button')` and `[role="button"]` selectors skip them entirely.

**Solution — When role queries fail on something you can see in the screenshot, broaden to the underlying HTML tag:**
```javascript
// Try the actual HTML element with text
await page.locator('li').filter({ hasText: /^Share$/ }).first().click();
// Or anchor tags acting as buttons
await page.locator('a', { hasText: /^Share$/ }).click();
```

Real example: the Share button on the Google My Maps editor is a plain `<li>` inside a horizontal action `<ul>`. `getByRole('button', { name: 'Share' })` returns nothing; `page.locator('li').filter({ hasText: /^Share$/ })` finds it on the first try.

**Diagnostic when you hit this:** enumerate elements by their *direct* text content, not innerText (which inherits children's text):
```javascript
const cands = await page.evaluate(() => {
  const out = [];
  document.querySelectorAll('*').forEach(el => {
    const direct = Array.from(el.childNodes)
      .filter(n => n.nodeType === Node.TEXT_NODE)
      .map(n => n.textContent.trim()).join('').trim();
    if (direct === 'Share' && el.offsetParent !== null) {
      out.push({ tag: el.tagName, role: el.getAttribute('role') });
    }
  });
  return out;
});
```
This tells you the true tag — often surprising (`LI/-`, `A/-`, `SPAN/-`).

## Anti-Pattern 6: OS Coordinates Don't Reach Cross-Origin Iframe Content

**Problem:**
```javascript
// ❌ Click lands visually on the button but nothing happens
await page.mouse.click(480, 325);
```

**Why it fails:** With Chrome's site isolation, a cross-origin iframe is out-of-process. An OS-level mouse event dispatched to the parent page's viewport coordinates hits the parent's `<iframe>` element — the synthetic click event does not propagate through to the framework's event handlers inside the iframe. The button appears to receive the click (the cursor lands on it) but the React/LMS event system never fires.

**Solution — evaluate a DOM `.click()` directly in the iframe's execution context via CDP:**
```javascript
// ✅ Invokes the framework event handler synchronously
await session.send('Runtime.evaluate', {
  contextId: ctxId,
  expression: `document.getElementById(${JSON.stringify(buttonId)}).click()`,
});
```

See `templates/cdp-session.js` for the full session setup pattern. Once you have a `CDPSession` attached directly to the iframe target, `Runtime.evaluate` with an explicit `contextId` is 100% reliable across all SCORM players and LMS wrappers tested.

**Signal you've hit this:** `page.mouse.click(x, y)` or `locator.click()` on an iframe's content executes without error but produces no visible navigation, no DOM change, and no network request.

## Anti-Pattern 7: Tab Key Is Unreliable Across Cross-Origin Iframe Boundaries

**Problem:**
```javascript
// ❌ Tab+Enter to "advance" in an iframe can activate the wrong element
await page.keyboard.press('Tab');
await page.keyboard.press('Enter');
```

**Why it fails:** When focus is inside a cross-origin iframe, pressing `Tab` on the parent moves focus to the next focusable element in the **parent** frame's tab order — sidebar links, navigation items, or toolbar buttons — not to the next element inside the iframe. Pressing `Enter` then activates whatever the parent gave focus to, which can silently navigate away from the current page or toggle an unrelated UI control.

**Real incident:** Repeated Tab+Enter attempts to reach a "Continue" button in a SCORM player resulted in the page navigating back to the course launch screen, requiring the entire session to restart.

**Solution:** Never use keyboard navigation for cross-origin iframe content. Use direct DOM `.click()` via `Runtime.evaluate` (see **Anti-Pattern 6**).

## Anti-Pattern 8: Empty Button IDs Break getElementById in Popups

**Problem:**
```javascript
// ❌ Silently fails when the button has id=""
await evalIn(session, ctxId, `document.getElementById('').click()`);
// Returns null — no click, no error
```

**Why it fails:** `document.getElementById('')` returns `null` per spec. Many SCORM authoring tools (Articulate, iSpring, Lectora) generate stable `id` attributes for primary content buttons but leave popup/dialog buttons with `id=""`. A dismiss button in an "Invalid Answer" modal, a confirmation OK, or a timeout notice may all have empty IDs. The click silently no-ops and the driver enters an infinite retry loop.

**Solution — fall back to text or aria-label matching:**
```javascript
// ✅ Find by visible text content
await evalIn(session, ctxId, `
  ([...document.querySelectorAll('button')]
    .find(b => /^(OK|Got it|Close|Dismiss)$/i.test(b.textContent.trim()))
    || { click() {} })
  .click()
`);

// ✅ Or use Runtime.callFunctionOn with an element reference if you already have it
```

**Rule:** Never assume `acc-` prefixed or otherwise stable IDs in popup/dialog content. Always have a text-based fallback selector for dismiss buttons.
