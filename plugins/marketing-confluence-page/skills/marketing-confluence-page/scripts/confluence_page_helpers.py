"""
Confluence page creation helpers for marketing-style layouts.

Credentials come from environment variables: JIRA_USERNAME and JIRA_API_TOKEN.
"""
import urllib.request
import json
import base64
import os

BASE = "https://wellsky.atlassian.net/wiki"

HR = '<ac:layout-section ac:type="fixed-width" ac:breakout-mode="default"><ac:layout-cell><hr /></ac:layout-cell></ac:layout-section>'


def get_auth():
    username = os.environ.get("JIRA_USERNAME")
    token = os.environ.get("JIRA_API_TOKEN")
    if not username or not token:
        raise RuntimeError("Set JIRA_USERNAME and JIRA_API_TOKEN environment variables")
    return base64.b64encode(f"{username}:{token}".encode()).decode()


def api(method, path, data=None, auth=None):
    if auth is None:
        auth = get_auth()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    url = f"{BASE}{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


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


def screenshot_section(heading, body_html, filename, width=880):
    img = attachment(filename, width)
    return (
        '<ac:layout-section ac:type="fixed-width" ac:breakout-mode="default">'
        f'<ac:layout-cell>'
        f'<h2>{heading}</h2>{body_html}'
        f'<p style="text-align: center;">{img}</p>'
        f'</ac:layout-cell>'
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


def upload_attachment(page_id, src_path, filename, auth=None):
    if auth is None:
        auth = get_auth()
    with open(src_path, "rb") as f:
        file_data = f.read()
    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{BASE}/rest/api/content/{page_id}/child/attachment",
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
