# useful git repos

A small Python script that collects direct GitHub repository links from descriptions of all public videos and Shorts listed at <https://www.youtube.com/@TheNextNewThingAI> and <https://www.youtube.com/@Cloud-Codes>, then writes `index.html` beside the script. It lists each unique repo, its GitHub description, exact star count, and labeled source videos. Use the channel dropdown and keyword search together to filter the page. Repositories mentioned by both channels appear once and match either channel. It does not clone repositories or download videos.

## Run

Requires macOS or Linux, Python 3.10+ and [yt-dlp](https://github.com/yt-dlp/yt-dlp).

```sh
python3 -m pip install -U yt-dlp
python3 update_repos.py
open index.html   # macOS; otherwise open the file in a browser
```

`yt-dlp` is already installed on this computer. The first run scans both channels and takes several minutes. Later runs check both channels for new videos, reuse `cache.json`, and regenerate the page. Files are always written beside the script, regardless of the working directory.

To pick up edits to old video descriptions and refresh GitHub descriptions:

```sh
python3 update_repos.py --refresh
```

GitHub descriptions and exact star counts are read from public repository pages; no API key is needed. Repository metadata is refreshed once per UTC day (or with `--refresh`), and cached values are retained during temporary failures. Unknown star counts are labeled unavailable rather than shown as zero. Failed requests without cached results are retried on the next run. Use `--refresh` to retry updates to already cached results.

## Nightly update

A local Codex automation named **Update useful git repos nightly** is configured for 11 p.m. America/Los_Angeles each day. Keep this Mac awake and Codex running for local scheduled work.

The automation runs the updater, commits only `index.html` when its contents change, and pushes to `origin/main` at `git@github.com:nandiraju/repos.git`. It skips publication on failed/incomplete scans, retains the cache for the next attempt, and reports failures. It does not create empty commits or include unrelated files. Git conflicts require manual attention; it never force pushes.

The schedule is managed in the Codex app and is not installed by cloning this repository. `index.html` is the generated page (there is no separate `generated.html`).

Daily runs fetch new or previously failed videos. Use `--refresh` manually to rescan edited older descriptions. Overlapping runs are prevented by a lock. Open or reload `index.html` after a run to see updates.

## Scope and failures

Only GitHub links written in descriptions are collected, including links to files, issues, or subdirectories normalized to the repository. Spoken mentions, comments, linked resource pages, short-link destinations, private videos, and deleted videos are not scanned. GitHub supplies the descriptions; missing descriptions are labeled, not invented. Deleted/private repository links are retained and labeled unavailable; use `--refresh` to check them again.

YouTube descriptions are fetched by two workers, each waiting three seconds before a request, with retries and backoff. If YouTube continues to rate limit requests, the remaining videos are deferred until a later run.

If some requests fail, available results are published with a visible notice and the script exits with status 1. Cached data is preserved. If channel listing fails or no descriptions are available, the existing HTML is left untouched. `cache.json` stores video descriptions and GitHub metadata, so you can inspect the underlying data.

Run the small parsing/rendering checks with `python3 -m unittest -v`.
