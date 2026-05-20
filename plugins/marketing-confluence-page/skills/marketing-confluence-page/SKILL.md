---
skill: marketing-confluence-page
description: Create a marketing-style Confluence page with alternating two-column sections (text + image), a hero intro, and a full-width CTA. Used for broad internal audience pages like feature announcements, onboarding guides, and platform documentation.
instructions: |-
  ## Marketing-Style Confluence Page

  This skill creates polished Confluence pages in the style of the SkyStage overview page
  (wellsky.atlassian.net/wiki/spaces/ME/pages/3104833641/SkyStage) — alternating two-column
  sections with text on one side and an image on the other, separated by horizontal rules.

  ---

  ## Layout Pattern

  The page uses Confluence's `ac:layout` storage format with three section types:

  ```
  Hero          two_left_sidebar   image (left/narrow) + title+intro (right/wide)
  ──────────────────────────────────────────────────────
  Section A     two_right_sidebar  text (left) + image (right)
  ──────────────────────────────────────────────────────
  Section B     two_left_sidebar   image (left) + text (right)
  ──────────────────────────────────────────────────────
  Section C     two_right_sidebar  text (left) + image (right)
  ──────────────────────────────────────────────────────
  ...alternating
  ──────────────────────────────────────────────────────
  CTA           fixed-width        tip callout, full width
  ```

  **Key rules:**
  - Alternate `two_right_sidebar` and `two_left_sidebar` so images zigzag left/right
  - Separate every section with a `fixed-width` HR divider
  - Hero always uses `two_left_sidebar` (image on left sidebar, text on right)
  - CTA uses `fixed-width` with a `tip` macro callout
  - Use `ac:breakout-mode="wide"` on all two-column sections
  - Image width: 380–400px in hero sidebar, 500px in body sections

  ---

  ## Two Section Types — Rules

  There are exactly two kinds of sections. Never mix them.

  ### Type A: Concept section (two-column, stock image)
  Use when the section explains a concept, reason, or benefit with no screenshot.
  - Image side: Unsplash stock photo, logo, or clip art
  - Text side: heading + 2–3 short paragraphs or a bullet list
  - Stock image width: 500px in body, 300px in hero sidebar

  ### Type B: Screenshot section (full-width, no stock image)
  Use when the section shows what the user sees or does in the product.
  - `fixed-width` layout — the entire section width
  - Contains: h2 heading + explanatory paragraph(s) + centered screenshot
  - No stock image — the screenshot IS the visual
  - Screenshot width: 880px, centered
  - No caption needed if the paragraph already explains it

  | Content                     | Section type          | Image            |
  |-----------------------------|-----------------------|------------------|
  | Why this matters / value    | Two-column (Type A)   | Unsplash stock   |
  | Hero intro                  | Two-column (Type A)   | Stock or logo    |
  | Step-by-step / UI walkthroughs | Full-width (Type B) | Real screenshot |
  | Flexibility / concepts      | Two-column (Type A)   | Unsplash stock   |
  | CTA                         | Full-width            | None             |

  **NEVER put a full UI screenshot in a two-column cell.** It renders too small.
  **NEVER add a stock image to a screenshot section.** The screenshot is the visual.

  ### Type B: Screenshot section template
  ```xml
  <ac:layout-section ac:type="fixed-width" ac:breakout-mode="default">
    <ac:layout-cell>
      <h2>Section Heading</h2>
      <p>Explanatory paragraph describing what this step does or what the user sees.</p>
      <p style="text-align: center;">
        <ac:image ac:align="center" ac:layout="center" ac:custom-width="true" ac:width="880">
          <ri:attachment ri:filename="my-screenshot.png"/>
        </ac:image>
      </p>
    </ac:layout-cell>
  </ac:layout-section>
  ```

  ### Stock images (ri:url via Unsplash)
  Use for concept sections where no real screenshot exists. These Unsplash photo IDs
  are known to work well for technology/team/collaboration topics:

  | Photo ID                              | Subject                     |
  |---------------------------------------|-----------------------------|
  | 1522071820081-009f0129c71c            | Team meeting / collaboration |
  | 1498050108023-c5249f4df085            | Laptop / coding              |
  | 1486406146926-c627a92ad1ab            | Buildings / enterprise       |
  | 1460925895917-afdab827c52f            | Analytics / charts           |
  | 1521587760476-6c12a4b040da            | Library / knowledge          |
  | 1576670659221-578949ce6284            | Tech / abstract code         |
  | 1586281380117-5a60ae2050cc            | Documents / process          |
  | 1697577418970-95d99b5a55cf            | AI / technology              |
  | 1499669478454-6f140f73d5de            | Study / focus                |

  URL format: `https://images.unsplash.com/photo-{ID}?w=600&h=400&fit=crop&auto=format`

  In storage format (note the `&amp;` escaping):
  ```xml
  <ac:image ac:align="center" ac:layout="center" ac:custom-width="true" ac:width="500">
    <ri:url ri:value="https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=600&amp;h=400&amp;fit=crop&amp;auto=format" />
  </ac:image>
  ```

  ---

  ## Storage Format Templates

  ### Horizontal rule divider
  ```xml
  <ac:layout-section ac:type="fixed-width" ac:breakout-mode="default">
    <ac:layout-cell><hr /></ac:layout-cell>
  </ac:layout-section>
  ```

  ### Image left, text right (two_left_sidebar)
  ```xml
  <ac:layout-section ac:type="two_left_sidebar" ac:breakout-mode="wide">
    <ac:layout-cell>
      <p>IMAGE_TAG_HERE</p>
    </ac:layout-cell>
    <ac:layout-cell>
      <h2>Section Title</h2>
      <p>Body text here.</p>
    </ac:layout-cell>
  </ac:layout-section>
  ```

  ### Text left, image right (two_right_sidebar)
  ```xml
  <ac:layout-section ac:type="two_right_sidebar" ac:breakout-mode="wide">
    <ac:layout-cell>
      <h2>Section Title</h2>
      <p>Body text here.</p>
    </ac:layout-cell>
    <ac:layout-cell>
      <p>IMAGE_TAG_HERE</p>
    </ac:layout-cell>
  </ac:layout-section>
  ```

  ### Info callout (used inside a cell)
  ```xml
  <ac:structured-macro ac:name="info" ac:schema-version="1">
    <ac:rich-text-body>
      <p><strong>Key point:</strong></p>
      <ul><li>Item one</li><li>Item two</li></ul>
    </ac:rich-text-body>
  </ac:structured-macro>
  ```

  ### Tip callout for CTA
  ```xml
  <ac:structured-macro ac:name="tip" ac:schema-version="1">
    <ac:rich-text-body>
      <p><strong><a href="URL">Action text &rarr;</a></strong></p>
      <p>Supporting text or feedback prompt.</p>
    </ac:rich-text-body>
  </ac:structured-macro>
  ```

  ---

  ## Python Helper Pattern

  Use this pattern to build pages programmatically (from `.tmp/create-PAGENAME.py`).
  Credentials come from `~/.claude/settings.local.json` → env vars JIRA_USERNAME and JIRA_API_TOKEN.

  ```python
  import urllib.request, json, base64

  BASE = "https://wellsky.atlassian.net/wiki"
  USERNAME = "russell.rutledge@wellsky.com"
  TOKEN = "..."  # from JIRA_API_TOKEN env var
  PAGE_ID = "..."

  auth = base64.b64encode(f"{USERNAME}:{TOKEN}".encode()).decode()
  HEADERS = {
      "Authorization": f"Basic {auth}",
      "Content-Type": "application/json",
      "Accept": "application/json",
  }

  def api(method, path, data=None):
      url = f"{BASE}{path}"
      body = json.dumps(data).encode("utf-8") if data else None
      req = urllib.request.Request(url, data=body, headers=HEADERS, method=method)
      with urllib.request.urlopen(req) as resp:
          return json.loads(resp.read().decode())

  HR = '<ac:layout-section ac:type="fixed-width" ac:breakout-mode="default"><ac:layout-cell><hr /></ac:layout-cell></ac:layout-section>'

  def left_image_section(image_tag, heading, body_html):
      return (
          '<ac:layout-section ac:type="two_left_sidebar" ac:breakout-mode="wide">'
          f'<ac:layout-cell><p>{image_tag}</p></ac:layout-cell>'
          f'<ac:layout-cell><h2>{heading}</h2>{body_html}</ac:layout-cell>'
          '</ac:layout-section>'
      )

  def right_image_section(heading, body_html, image_tag):
      return (
          '<ac:layout-section ac:type="two_right_sidebar" ac:breakout-mode="wide">'
          f'<ac:layout-cell><h2>{heading}</h2>{body_html}</ac:layout-cell>'
          f'<ac:layout-cell><p>{image_tag}</p></ac:layout-cell>'
          '</ac:layout-section>'
      )

  def attachment(filename, width=500):
      return (
          f'<ac:image ac:align="center" ac:layout="center" ac:custom-width="true" ac:width="{width}">'
          f'<ri:attachment ri:filename="{filename}"/></ac:image>'
      )

  def unsplash(photo_id, width=500):
      url = f"https://images.unsplash.com/photo-{photo_id}?w=600&amp;h=400&amp;fit=crop&amp;auto=format"
      return (
          f'<ac:image ac:align="center" ac:layout="center" ac:custom-width="true" ac:width="{width}">'
          f'<ri:url ri:value="{url}" /></ac:image>'
      )
  ```

  ---

  ## Workflow: Creating a New Page

  1. **Identify parent page** — find its Confluence page ID
  2. **Write the script** to `.tmp/create-PAGENAME.py` using the helpers above
  3. **Run the script** — it POSTs to `/wiki/rest/api/content` and prints the page ID
  4. **Upload screenshots** as attachments via a second script (see upload pattern below)
     - Use `X-Atlassian-Token: no-check` header
     - Use multipart/form-data
     - Images reference each other by filename, so names must match exactly
  5. **Review in browser** — open the page URL in Confluence to verify layout

  ### Upload script pattern
  ```python
  import urllib.request, base64

  def upload(page_id, src_path, filename, auth):
      with open(src_path, "rb") as f:
          file_data = f.read()
      boundary = "----FormBoundary7MA4YWxkTrZu0gW"
      body = (
          f"--{boundary}\r\n"
          f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
          f"Content-Type: image/png\r\n\r\n"
      ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
      req = urllib.request.Request(
          f"https://wellsky.atlassian.net/wiki/rest/api/content/{page_id}/child/attachment",
          data=body,
          headers={
              "Authorization": f"Basic {auth}",
              "Content-Type": f"multipart/form-data; boundary={boundary}",
              "X-Atlassian-Token": "no-check",
          },
          method="POST"
      )
      with urllib.request.urlopen(req) as resp:
          resp.read()
  ```

  ---

  ## Content Guidelines for Marketing Pages

  - **Tone**: Clear, practical, grounded — not promotional
  - **Headings**: No emojis; sentence case or title case
  - **Paragraphs**: 2–3 sentences max per paragraph
  - **No transition framing**: Write in present tense as if this is simply how things work.
    Never say "we're changing X" or "X is being disabled". State the current reality.
  - **Stock images**: Use for concept/philosophy sections (why, value, flexibility)
  - **Real screenshots**: Use for "how it works" and "what you see" sections
  - **Info callout**: Use to highlight a short list of key requirements or facts
  - **Tip callout**: Reserve for the CTA at the bottom

  ---

  ## Example Page: GitHub Repository Creation
  - Page: wellsky.atlassian.net/wiki/spaces/ME/pages/3109945345/
  - Script: .tmp/reformat-github-repo-page.py
  - Reference page (SkyStage overview): wellsky.atlassian.net/wiki/spaces/ME/pages/3104833641/SkyStage
---
