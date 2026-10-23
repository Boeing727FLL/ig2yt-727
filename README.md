# ig2yt-727

Automatically copies newly published videos from the team's Instagram
[@boeing_727](https://www.instagram.com/boeing_727/) to the team's YouTube
channel. Free forever: GitHub Actions (public repo) + cron-job.org, no server.

## How it works

1. cron-job.org POSTs a `workflow_dispatch` to this repo every 30 minutes.
2. The workflow runs `ig2yt.py`:
   - refreshes the 60-day Instagram token and writes it back to the repo
     secret (`gh secret set`, using `GH_PAT`, no git writes);
   - lists the latest Instagram media;
   - compares against the YouTube uploads playlist (dedupe marker
     `ig:<media_id>` in the video description);
   - uploads missing videos with the Instagram caption as title/description.

## Publishing mode

Repository variable `PUBLISH_MODE` controls visibility of new uploads:
`private` (default, testing), `unlisted`, or `public` (after team approval).

## Secrets (repo Settings > Secrets and variables > Actions)

| Secret | Purpose |
| --- | --- |
| `IG_ACCESS_TOKEN` | Instagram Graph API long-lived token (auto-refreshed) |
| `YT_CLIENT_ID` / `YT_CLIENT_SECRET` | Google OAuth client for the uploader |
| `YT_REFRESH_TOKEN` | YouTube refresh token for the team's channel |
| `GH_PAT` | Fine-grained PAT: Actions + Secrets on this repo only |

## Known limitation

Instagram does not expose `media_url` for reels that use Instagram
music-library audio. Those reels are skipped and listed in the run log.
