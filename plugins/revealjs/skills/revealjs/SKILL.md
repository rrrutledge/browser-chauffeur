---
name: revealjs
description: Create polished, professional reveal.js presentations. Use when the user asks to create slides, a presentation, a deck, or a slideshow. Supports themes, multi-column layouts, code highlighting, animations, speaker notes, and custom styling. Generates HTML + CSS with no build step required.
---

# Reveal.js Presentations

Create HTML presentations using reveal.js. No build step required — just open the HTML in a browser.

## Design Principles

**CRITICAL**: Before creating any presentation, analyze the content and choose appropriate design elements:

1. **Consider the subject matter**: What tone, industry, or mood does it suggest?
2. **Check for branding**: If the user mentions a company/organization, consider their brand colors
3. **Match palette to content**: Select colors that reflect the subject
4. **State your approach**: Explain your design choices before writing code

**Requirements**:
- State your content-informed design approach BEFORE writing code
- Use web-safe fonts or Google Fonts via `@import` in CSS
- **Always use `pt` (points) for font sizes** — slides are fixed-size, so `pt` is predictable (like PowerPoint). Never use `em`, `rem`, or `px` for font sizes.
- When a slide has less content, scale text up with `.text-lg`, `.text-xl`, `.text-2xl`, `.text-3xl`, `.text-4xl` classes (defined in base-styles.css)

### Slide Content Principles

**Diverse presentation is key.** Even when slides have similar content types, vary the visual presentation:
- Use **different layouts** across slides: columns on one, stacked containers on another, styled cards on a third
- Don't repeat the same layout pattern on consecutive slides
- Use inline CSS grid for multi-column layouts (each slide's needs vary)
- When a visual pattern repeats 3+ times, create a CSS class instead of inline styles
- **All visible text must be inside a text element** (`<p>`, `<li>`, or `<h1>`–`<h6>`) — never bare text in `<div>` or `<span>`

## Workflow

### Step 1: Plan the Structure

Based on the user's content, determine how many slides are needed, which should be section dividers, and where to use vertical stacks.

### Step 2: Generate the Scaffold

Use the `create-presentation.js` script in the `scripts/` directory next to this SKILL.md:

```bash
node <path-to-skill>/scripts/create-presentation.js --structure 1,1,d,3,1,d,1 --title "My Presentation" --output presentation.html
```

**Options:**
- `--slides N` — N horizontal slides (simple mode)
- `--structure <list>` — Mixed layout: `1` = single slide, `N` = vertical stack, `d` = section divider
- `--output <file>`, `--title <text>`, `--styles <file>`

The scaffold auto-copies `base-styles.css` as `styles.css` into the output directory.

### Step 3: Customize the CSS

Edit `styles.css` — customize the CSS variables (especially colors and fonts) for your theme. The base file uses `--background-color`, `--primary-color`, `--text-color`, etc.

For Google Fonts, add `@import` at the top of CSS and set `--heading-font` / `--body-font`.

### Step 4: Fill in the HTML Content

**Use the Edit tool incrementally** — one or a few slides at a time. The scaffold generates unique placeholder text per slide (e.g., `Slide 2 Title Here`) for easy targeting.

Key patterns:
- Every `<section>` should have a unique `id`
- Use `class="section-divider"` for centered section title slides
- Wrap main content in `<div class="content">` for consistent spacing
- Use `<div class="footnote">` for attribution at bottom

### Step 5: Check for Content Overflow

```bash
node <path-to-skill>/scripts/check-overflow.js presentation.html
```

### Step 6: Visual Review with Screenshots

**CRITICAL: Review screenshots of EVERY SINGLE SLIDE.**

```bash
npx decktape reveal "presentation.html?export" output.pdf \
  --screenshots \
  --screenshots-directory "screenshots/$(date +%Y%m%d_%H%M%S)"
```

The `?export` parameter disables chart animations for cleaner rendering. Use the Read tool to examine each screenshot image.

Watch for: color inheritance in containers, icons not rendering, unexpected text wrap in column layouts.

### Step 7: Suggest Browser Editing

After completing the presentation, let the user know they can edit text directly:

```bash
node <path-to-skill>/scripts/edit-html.js presentation.html
```

Click any text to edit inline, then save changes back to the file.

## Charts

**Before adding ANY chart, read [references/charts.md](references/charts.md).** Charts require a specific flexbox pattern to size correctly. The key requirement: `maintainAspectRatio: false` in chart options, inside a flex container with `min-height: 0`.
