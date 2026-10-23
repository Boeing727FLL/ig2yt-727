#!/usr/bin/env python3
"""Copy new Instagram videos (@boeing_727) to the Boeing727 YouTube channel.

Runs in GitHub Actions, triggered by cron-job.org via workflow_dispatch.
Dedupe marker: "ig:<media_id>" inside the YouTube video description.
No git writes. Tokens live in repo secrets; the IG 60-day token is refreshed
and written back through `gh secret set` (uses GH_PAT, not git).
"""
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

IG_TOKEN = os.environ["IG_ACCESS_TOKEN"]
YT_CLIENT_ID = os.environ["YT_CLIENT_ID"]
YT_CLIENT_SECRET = os.environ["YT_CLIENT_SECRET"]
YT_REFRESH_TOKEN = os.environ["YT_REFRESH_TOKEN"]
PUBLISH_MODE = (os.environ.get("PUBLISH_MODE") or "private").strip().lower()
if PUBLISH_MODE not in ("private", "unlisted", "public"):
    PUBLISH_MODE = "private"

GRAPH = "https://graph.instagram.com"
YT_API = "https://www.googleapis.com/youtube/v3"
YT_UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"


def http_json(method, url, data=None, headers=None, raw=False):
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = resp.read()
        return payload if raw else json.loads(payload)


def refresh_ig_token():
    """Rotate the 60-day IG token and write it back to the repo secret."""
    global IG_TOKEN
    try:
        out = http_json("GET", f"{GRAPH}/refresh_access_token?grant_type=ig_refresh_token&access_token={IG_TOKEN}")
        new = out.get("access_token")
        if not new:
            print("ig token refresh: no token in response; keeping current")
            return
        env = dict(os.environ)
        p = subprocess.run(["gh", "secret", "set", "IG_ACCESS_TOKEN", "--body", new],
                           capture_output=True, text=True, env=env)
        if p.returncode == 0:
            IG_TOKEN = new
            print("ig token refreshed and repo secret updated")
        else:
            print("ig token refreshed but secret write-back failed:", p.stderr.strip()[:200])
    except Exception as e:
        print("ig token refresh failed (continuing with current):", str(e)[:200])


def yt_access_token():
    out = http_json("POST", "https://oauth2.googleapis.com/token", data={
        "client_id": YT_CLIENT_ID,
        "client_secret": YT_CLIENT_SECRET,
        "refresh_token": YT_REFRESH_TOKEN,
        "grant_type": "refresh_token",
    })
    return out["access_token"]


def ig_recent_media():
    fields = "id,caption,media_type,media_url,permalink,timestamp"
    out = http_json("GET", f"{GRAPH}/me/media?fields={fields}&limit=25&access_token={IG_TOKEN}")
    return out.get("data", [])


def yt_uploaded_markers(token):
    headers = {"Authorization": f"Bearer {token}"}
    ch = http_json("GET", f"{YT_API}/channels?part=contentDetails&mine=true", headers=headers)
    uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    markers = set()
    page = None
    while True:
        url = f"{YT_API}/playlistItems?part=snippet&playlistId={uploads}&maxResults=50"
        if page:
            url += "&pageToken=" + page
        out = http_json("GET", url, headers=headers)
        for item in out.get("items", []):
            desc = item.get("snippet", {}).get("description", "")
            for line in desc.splitlines():
                if line.startswith("ig:"):
                    markers.add(line.strip())
        page = out.get("nextPageToken")
        if not page:
            break
    return markers


def yt_upload(token, item):
    caption = (item.get("caption") or "").strip()
    first = caption.splitlines()[0] if caption else ""
    title = (first[:97] + "...") if len(first) > 100 else (first or "Boeing 727")
    description = f"{caption}\n\nig:{item['id']}\n{item.get('permalink','')}".strip()
    media_url = item["media_url"]
    video = urllib.request.urlopen(media_url, timeout=300).read()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    meta = json.dumps({
        "snippet": {"title": title, "description": description},
        "status": {"privacyStatus": PUBLISH_MODE, "selfDeclaredMadeForKids": False},
    }).encode()
    req = urllib.request.Request(
        f"{YT_UPLOAD}?uploadType=resumable&part=snippet,status", data=meta, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=120) as resp:
        location = resp.headers["Location"]
    req2 = urllib.request.Request(location, data=video, method="PUT")
    req2.add_header("Authorization", f"Bearer {token}")
    req2.add_header("Content-Type", "video/mp4")
    with urllib.request.urlopen(req2, timeout=1800) as resp:
        result = json.loads(resp.read())
    return result.get("id")


def main():
    print("publish mode:", PUBLISH_MODE)
    refresh_ig_token()
    token = yt_access_token()
    media = ig_recent_media()
    markers = yt_uploaded_markers(token)
    uploaded, skipped, present = [], [], 0
    for item in media:
        if item.get("media_type") != "VIDEO":
            continue
        if f"ig:{item['id']}" in markers:
            present += 1
            continue
        if not item.get("media_url"):
            skipped.append(item.get("permalink", item["id"]))
            continue
        try:
            vid = yt_upload(token, item)
            uploaded.append((item.get("permalink", item["id"]), vid))
        except Exception as e:
            print("upload failed for", item.get("permalink", item["id"]), ":", str(e)[:200])
    print(f"done: {len(uploaded)} uploaded, {present} already present, {len(skipped)} skipped (no media_url, likely copyrighted audio)")
    for permalink, vid in uploaded:
        print("uploaded:", permalink, "-> video id", vid)
    for permalink in skipped:
        print("skipped:", permalink)
    if skipped:
        print("note: skipped reels usually contain Instagram music-library audio, which the Instagram API does not expose")


if __name__ == "__main__":
    sys.exit(main())
