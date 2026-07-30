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
// ✅ By known ID (if non-empty)
await session.send('Runtime.evaluate', {
  contextId: ctxId,
  expression: `document.getElementById(${JSON.stringify(buttonId)}).click()`,
});

// ✅ By visible text (preferred for popups/dialogs — many SCORM tools leave id="" on these)
await session.send('Runtime.evaluate', {
  contextId: ctxId,
  expression: `([...document.querySelectorAll('button')].find(b => /^Continue$/i.test(b.textContent.trim()))).click()`,
});
```

**Caution:** Popup/dialog buttons in SCORM authoring tools (Articulate, iSpring, Lectora) often have `id=""` — `getElementById('')` returns `null` per spec and silently no-ops. Always prefer text or aria-label matching for dismiss/confirm buttons.

See `templates/cdp-session.js` for the full session setup pattern. Once you have a `CDPSession` attached directly to the iframe target, `Runtime.evaluate` with an explicit `contextId` is 100% reliable across all SCORM players and LMS wrappers tested.

**Signal you've hit this:** `page.mouse.click(x, y)` or `locator.click()` on an iframe's content executes without error but produces no visible navigation, no DOM change, and no network request.

## Anti-Pattern 7: Exact Text Match Misses Fluent UI Buttons With Icon Glyphs

**Problem:**
```javascript
// ❌ All of these consistently time out on Outlook, Teams, SharePoint, OneDrive:
await page.getByRole('button', { name: 'Save', exact: true });
await page.locator('button').filter({ hasText: /^Save$/ });
const btn = await page.evaluate(() =>
  [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Save')
);
```

**Why it fails:** Fluent UI renders icon buttons as:
```html
<button><span class="fui-Button__icon"><i class="fui-Icon-font" aria-hidden="true">…</i></span>Save</button>
```
The `<i>` tag uses a private-use Unicode font glyph. That character IS part of `textContent` even though it's invisible — so `trim()` doesn't remove it and exact-match patterns never satisfy. JSON serialization may strip the glyph, which hides the real prefix and makes debugging misleading.

This applies to Outlook web, Teams web, SharePoint, OneDrive, and any other Microsoft 365 surface built on Fluent UI.

**Solution — Filter on the icon-wrapped button shape, not exact text:**
```javascript
// ✅ Matches the Fluent UI button structure regardless of the glyph prefix
const saveBtn = page.locator('button:has(span.fui-Button__icon)').filter({ hasText: 'Save' }).first();
await saveBtn.click();
```

`filter({ hasText: '...' })` does a substring match on `textContent`, so the invisible glyph prefix doesn't matter. `:has(span.fui-Button__icon)` scopes the search to Fluent UI buttons specifically, avoiding spurious matches.

---

## Anti-Pattern 8: Confirmation Dialogs Without `role="dialog"`

**Problem:**
```javascript
// ❌ Returns empty — the "Are you sure?" confirmation is on screen, but has no role attribute
const dialogs = await page.evaluate(() =>
  Array.from(document.querySelectorAll('[role="dialog"], [role="alertdialog"]'))
    .filter(d => getComputedStyle(d).display !== 'none')
    .map(d => d.innerText.slice(0, 100))
);
// dialogs === [] — handler skips the confirmation step, action never fires server-side
```

**Why it fails:** Not every confirmation dialog follows ARIA conventions. Some apps (including parts of Outlook web) render a centered `<div>` with a message and buttons but no `role` attribute on the container. Standard role-based detection misses it completely. The primary action never fires, and subsequent verification keeps showing the item as still present — which looks like the delete/move itself failed, not the confirmation step.

**Signal you've hit this:** A click on a primary action produces no navigation, no network request, and no DOM change. The item appears unchanged after verification. Before assuming the click itself failed, **check for an undetected confirmation modal** — look at a screenshot first.

**Solution — Broader modal detector by geometry when role attributes are absent:**
```javascript
const modalCandidates = await page.evaluate(() => {
  return Array.from(document.querySelectorAll('div')).filter(el => {
    const r = el.getBoundingClientRect();
    if (r.width < 100 || r.height < 100) return false;
    const centerish = r.left > 200 && r.right < window.innerWidth - 200
                   && r.top > 100 && r.bottom < window.innerHeight - 100;
    if (!centerish) return false;
    const buttons = el.querySelectorAll('button');
    return buttons.length >= 1 && buttons.length <= 5;
  }).map(el => ({
    text: el.innerText.slice(0, 200),
    buttons: [...el.querySelectorAll('button')].map(b => b.textContent.trim()),
  }));
});
```

Filter the results by expected button text (e.g., `'OK'`, `'Delete'`, `'Confirm'`) to avoid false positives from unrelated centered widgets. Once found, click the button via Playwright's locator API — not `element.click()` inside evaluate (see Anti-Pattern 2).

---

## Anti-Pattern 9: Tab Key Is Unreliable Across Cross-Origin Iframe Boundaries

**Problem:**
```javascript
// ❌ Tab+Enter to "advance" in an iframe can activate the wrong element
await page.keyboard.press('Tab');
await page.keyboard.press('Enter');
```

**Why it fails:** When focus is inside a cross-origin iframe, pressing `Tab` on the parent moves focus to the next focusable element in the **parent** frame's tab order — sidebar links, navigation items, or toolbar buttons — not to the next element inside the iframe. Pressing `Enter` then activates whatever the parent gave focus to, which can silently navigate away from the current page or toggle an unrelated UI control.

**Real incident:** Repeated Tab+Enter attempts to reach a "Continue" button in a SCORM player resulted in the page navigating back to the course launch screen, requiring the entire session to restart.

**Solution:** Never use keyboard navigation for cross-origin iframe content. Use direct DOM `.click()` via `Runtime.evaluate` (see **Anti-Pattern 6**).

---

## Anti-Pattern 10: Generic Scroll-to-Bottom Doesn't Render Virtualized Grid Rows

**Problem:**
```javascript
// ❌ Scrolls the DOM element, but off-screen rows never appear
await page.evaluate(() => {
  [...document.querySelectorAll('*')]
    .filter(el => el.scrollHeight > el.clientHeight + 50)
    .forEach(el => { el.scrollTop = el.scrollHeight; });
});
```

**Why it fails:** Virtualized grids and lists (Vaadin Grid, react-window, react-virtualized, ag-grid, and similar) only mount DOM nodes for currently-visible rows and recycle them as the user scrolls. Setting `scrollTop` on the wrong element — or even the right one — doesn't guarantee the component's internal virtualization logic renders the rows you actually need; a generic "find every scrollable element and scroll it" sweep can miss the grid's real internal scroller entirely, or scroll a wrapper that has no effect on which rows are materialized. Real incident: dozens of `innerText` dumps and `scrollTo`/`scrollTop` attempts across a BrightFeed (Vaadin) feeds-management table never surfaced a section of rows sitting below the fold — the section existed and was fully functional, but no amount of generic scrolling made it appear in the DOM.

**Solution — use the component's own scroll-to API when one exists:**
```javascript
// ✅ Vaadin Grid exposes scrollToIndex directly
await page.evaluate(() => {
  const grid = document.querySelector('vaadin-grid');
  if (grid && typeof grid.scrollToIndex === 'function') grid.scrollToIndex(30); // overshoot past the last row
});
```
Other virtualization libraries expose analogous methods (react-window's `list.scrollToItem`, ag-grid's `api.ensureIndexVisible`) — check for one before assuming a plain `scrollTop` sweep will work. If no such API exists, `locator.scrollIntoViewIfNeeded()` on a specific target (found by text) combined with a poll loop is the fallback — never a blind "scroll everything" pass.

**Verify the fix worked before proceeding:** re-check with `document.body.innerText.includes(expectedText)` after scrolling — don't assume the scroll call succeeded just because it didn't throw.

---

## Anti-Pattern 11: Locating and Clicking in Separate Script Runs Hits the Wrong Recycled Row

**Problem:**
```javascript
// ❌ Script A: measure a row's position, note the coordinates, exit
const rect = /* ...getBoundingClientRect() on the target row... */;
console.log(rect.x, rect.y);

// ❌ Script B (separate invocation, run moments later): click those coordinates
await page.mouse.click(rect.x, rect.y);
```

**Why it fails:** A virtualized grid recycles its small pool of physical row elements as the user scrolls, and — separately from that — the grid's scroll position is not guaranteed to stay put between two independent script invocations against the same live page, even with no explicit navigation in between (a background sync, a re-render, or the grid's own idle recalculation can shift it). Coordinates or matched elements captured in one script run can silently refer to a completely different row by the time a later script run acts on them. Real incident: measuring a specific feed row's delete button in one script call, then clicking those exact coordinates in the next call, hit a "Professional Messages" row instead of the intended target — caught only because a confirmation dialog named the wrong feed before anything was actually deleted.

**Solution — locate and act in the same `page.evaluate()` call, so nothing can shift in between:**
```javascript
// ✅ Single evaluate: find the row, then click its button, atomically
const result = await page.evaluate((namePrefix) => {
  const nameCell = [...document.querySelectorAll('*')]
    .find(el => el.children.length === 0 && el.textContent.trim().startsWith(namePrefix));
  if (!nameCell) return { error: 'not found' };
  const nameRect = nameCell.getBoundingClientRect();
  const btn = [...document.querySelectorAll('vaadin-button, button, [role="button"]')]
    .filter(b => b.getBoundingClientRect().x > nameRect.x)
    .sort((a, b) => Math.abs(a.getBoundingClientRect().y - nameRect.y) - Math.abs(b.getBoundingClientRect().y - nameRect.y))[0];
  btn.click();
  return { clickedNear: nameCell.textContent.trim() };
}, 'Target Row Name');
```
Then **verify the resulting confirmation dialog (or post-click state) names the thing you meant to act on** before confirming anything destructive — never trust that a prior measurement still applies.

---

## Anti-Pattern 12: Screenshot Pixel Coordinates Aren't CSS Pixel Coordinates

**Problem:**
```javascript
// ❌ Read an (x, y) off a saved screenshot image, then click those raw numbers
await page.mouse.click(1760, 864); // coordinates eyeballed from a .png
```

**Why it fails:** `page.mouse.click(x, y)` operates in CSS/viewport pixels, but a saved screenshot can be rendered at a different pixel density (`devicePixelRatio` — e.g. 1.25x is common on Windows). A viewport that's actually 1528px wide (per `document.body.clientWidth`) can produce a screenshot image that's ~1910px wide. Reading a coordinate off the image and feeding it straight to `mouse.click()` lands roughly 25% off from the intended target — enough to miss the button entirely with no error, since the click just hits empty space or an unrelated element.

**Solution — get real element bounding rects via `getBoundingClientRect()` instead of reading pixels off an image:**
```javascript
const rect = await page.evaluate(() => {
  const el = /* ...find your target... */;
  const r = el.getBoundingClientRect();
  return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
});
await page.mouse.click(rect.x, rect.y);
```
`getBoundingClientRect()` always returns CSS pixels matching what `page.mouse` expects, regardless of device pixel ratio. Reserve screenshots for visual confirmation (reading them with the Read tool), never as a coordinate source for clicks.

---

## Anti-Pattern 13: Framework Tooltips Aren't Always on the Element's `title`/`aria-label`

**Problem:**
```javascript
// ❌ Checks the button's own attributes — comes back empty even though a tooltip clearly exists
const hasDeleteBtn = await page.evaluate(() =>
  [...document.querySelectorAll('button, [role="button"]')]
    .some(b => /delete/i.test(b.getAttribute('aria-label') || '') || /delete/i.test(b.getAttribute('title') || ''))
);
// hasDeleteBtn === false, even on a page with a working "Delete feed" icon and tooltip
```

**Why it fails:** Some component libraries (Vaadin among them) implement tooltips as a separate `<vaadin-tooltip>` element rendered alongside the control, not as a `title`/`aria-label` attribute on the control itself, and not always linked back via a standard `for`/`id` pair. Scanning the button's own attributes — or even doing a full shadow-DOM-piercing walk of the button subtree — finds nothing, because the tooltip text lives in a sibling element elsewhere in the tree. This produced a false "no delete control exists" conclusion in a real session, when the control was present and working the whole time.

**Solution — search for the framework's dedicated tooltip element directly, independent of the button:**
```javascript
// ✅ Vaadin: just list every vaadin-tooltip's text on the page
const tooltips = await page.evaluate(() =>
  [...document.querySelectorAll('vaadin-tooltip')].map(t => t.getAttribute('text') || t.textContent || '')
);
console.log(tooltips); // includes "Delete feed" even though no button had that in title/aria-label
```
When a control's purpose isn't obvious from its own attributes, check for the UI framework's tooltip component by tag name before concluding the feature doesn't exist.
