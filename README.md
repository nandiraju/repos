# GitHub repos from The Next New Thing

A small Python script that collects direct GitHub repository links from descriptions of all public videos and Shorts listed at <https://www.youtube.com/@TheNextNewThingAI>, then writes `index.html` beside the script. It lists each unique repo, its GitHub description, and links to the source videos. It does not clone repositories or download videos.

## Run

Requires macOS or Linux, Python 3.10+ and [yt-dlp](https://github.com/yt-dlp/yt-dlp).

```sh
python3 -m pip install -U yt-dlp
python3 update_repos.py
open index.html   # macOS; otherwise open the file in a browser
```

`yt-dlp` is already installed on this computer. The first run scans the entire channel and takes several minutes. Later runs check the channel for new videos, reuse `cache.json`, and regenerate the page. Files are always written beside the script, regardless of the working directory.

To pick up edits to old video descriptions and refresh GitHub descriptions:

```sh
python3 update_repos.py --refresh
```

GitHub descriptions are read from public repository pages; no API key is needed. Failed requests without cached results are retried on the next run. Use `--refresh` to retry updates to already cached results.

## Schedule later

Example daily cron entry (not installed automatically):

```cron
PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin
0 7 * * * cd /Users/srikanthnandiraju/CODEX_WORKSPACE/GitFromYT && python3 update_repos.py >> run.log 2>&1
```

Add `--refresh` if every scheduled run should rescan old descriptions as well. The computer must be awake at the scheduled time. Overlapping runs are prevented by a lock. Open or reload `index.html` after a run to see the updated page.

## Scope and failures

Only GitHub links written in descriptions are collected, including links to files, issues, or subdirectories normalized to the repository. Spoken mentions, comments, linked resource pages, short-link destinations, private videos, and deleted videos are not scanned. GitHub supplies the descriptions; missing descriptions are labeled, not invented.

YouTube descriptions are fetched one at a time, with a three-second pause before each request and retries with backoff. If YouTube continues to rate limit requests, the remaining videos are deferred until a later run.

If some requests fail, available results are published with a visible notice and the script exits with status 1. Cached data is preserved. If channel listing fails or no descriptions are available, the existing HTML is left untouched. `cache.json` stores video descriptions and GitHub metadata, so you can inspect the underlying data.

Run the small parsing/rendering checks with `python3 -m unittest -v`.
