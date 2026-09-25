#!/usr/bin/env python3
"""Collect GitHub repositories linked in a YouTube channel's descriptions."""
import argparse
import fcntl
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from threading import Event
from urllib.error import HTTPError, URLError
from urllib.parse import unquote
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
CHANNEL = 'https://www.youtube.com/@TheNextNewThingAI'
YOUTUBE_THROTTLED = Event()
# Match only github.com, not lookalike domains; discard paths below the repo.
REPO_PATTERN = re.compile(r'(?<![\w./-])(?:https?://)?(?:www\.)?github\.com/([\w-]+)/([\w.-]+)', re.I)
RESERVED = {'topics', 'collections', 'orgs', 'users', 'settings', 'marketplace',
            'features', 'sponsors', 'search', 'login', 'signup', 'about', 'explore'}


def repo_names(description):
    result = set()
    for owner, repo in REPO_PATTERN.findall(unquote(description)):
        repo = repo.rstrip('.')
        if repo.lower().endswith('.git'):
            repo = repo[:-4]
        if owner.lower() not in RESERVED and repo and repo not in {'.', '..'}:
            result.add(f'{owner}/{repo}'.lower())
    return result


def atomic_write(path, text):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def youtube(url):
    command = [shutil.which('yt-dlp') or 'yt-dlp', '--ignore-config', '--no-update',
               '--dump-single-json', '--flat-playlist', '--skip-download',
               '--socket-timeout', '20', '--retries', '2', '--extractor-retries', '2']
    run = subprocess.run(command + [url], capture_output=True, text=True, timeout=180)
    if run.returncode:
        raise RuntimeError(run.stderr.strip()[-1200:])
    return json.loads(run.stdout)


def videos_in(data):
    if 'entries' in data:
        for entry in data['entries']:
            if entry:
                yield from videos_in(entry)
    elif data.get('id'):
        yield data


def fetch_video(video):
    url = 'https://www.youtube.com/watch?v=' + video['id']
    for attempt in range(3):
        if YOUTUBE_THROTTLED.is_set():
            raise RuntimeError('YouTube rate limited this run; retry later')
        time.sleep(3)
        try:
            with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30) as response:
                page = response.read().decode('utf-8')
            break
        except HTTPError as error:
            if error.code == 429 and attempt == 2:
                YOUTUBE_THROTTLED.set()
            if error.code not in {429, 500, 502, 503} or attempt == 2:
                raise
            time.sleep(20 * (attempt + 1))
    match = re.search(r'ytInitialPlayerResponse\s*=\s*', page)
    if not match:
        raise RuntimeError('YouTube did not return video metadata')
    info = json.JSONDecoder().raw_decode(page[match.end():])[0].get('videoDetails', {})
    if info.get('videoId') != video['id'] or 'shortDescription' not in info:
        raise RuntimeError('YouTube did not return a full description')
    return {'title': info.get('title') or video.get('title') or video['id'],
            'description': info['shortDescription']}


class GitHubMetadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            self.values[attrs.get('property') or attrs.get('name')] = attrs.get('content', '')


def github_repo(name):
    # Public page metadata avoids requiring a token or hitting the API's small quota.
    url = 'https://github.com/' + name
    with urlopen(Request(url, headers={'User-Agent': 'GitFromYT'}), timeout=30) as response:
        parser = GitHubMetadata()
        parser.feed(response.read().decode('utf-8'))
        canonical_url = response.url
    description = parser.values.get('og:description', '')
    description = description.split(' Contribute to ')[0]
    description = description.removesuffix(' - ' + name)
    return {'name': parser.values.get('octolytics-dimension-repository_nwo') or name,
            'url': canonical_url,
            'description': description or 'No description provided on GitHub.'}


def render(repos, videos, channel, notes):
    rows = []
    for name, repo in sorted(repos.items()):
        sources = ''.join(f'<li><a href="https://www.youtube.com/watch?v={escape(vid, quote=True)}">'
                          f'{escape(videos[vid]["title"])}</a></li>' for vid in repo['videos'])
        rows.append(f'<tr class="repo-row"><td><a href="{escape(repo["url"], quote=True)}">{escape(repo["name"])}</a>'
                    f'</td><td>{escape(repo["description"])}</td><td><details><summary>'
                    f'{len(repo["videos"])} video(s)</summary><ul>{sources}</ul></details></td></tr>')
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    warnings = ''.join(f'<p class="notice">{escape(note)}</p>' for note in notes)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Next New Thing · GitHub repositories</title>
<style>
body{{font:16px/1.6 system-ui,sans-serif;color:#243044;background:#f6f8fc;max-width:1100px;margin:48px auto;padding:0 20px}}
h1{{line-height:1.2;color:#152238}} a{{color:#175bc4;overflow-wrap:anywhere}} p{{color:#526077}}
table{{width:100%;border-collapse:collapse;background:white}}th,td{{text-align:left;padding:16px;border-bottom:1px solid #dce2eb;vertical-align:top}}
th{{background:#eaf0f8}}td:first-child{{width:27%;font-weight:600}}td:last-child{{width:23%}}summary{{cursor:pointer}}ul{{padding-left:18px}}.notice{{background:#fff1cd;padding:12px}}.table-wrap{{overflow-x:auto}}
input[type="search"]{{display:block;box-sizing:border-box;width:100%;padding:12px;margin:8px 0;border:1px solid #aab8cc;border-radius:6px;font:inherit}}
</style></head><body><h1>GitHub repositories</h1>
<p>From <a href="{escape(channel, quote=True)}">The Next New Thing</a> video descriptions.</p>
<p>{len(repos)} repositories · {len(videos)} descriptions available · Updated {timestamp}</p>
<p>Includes public videos and Shorts listed by the channel. Only direct GitHub repository links in descriptions are collected.</p>
{warnings}<label for="repo-search">Search repositories</label>
<input id="repo-search" type="search" placeholder="Search names, descriptions, or video titles…" aria-describedby="search-count">
<p id="search-count" role="status" aria-live="polite"></p>
<p id="no-matches" hidden>No repositories match your search. Try another keyword or clear the search.</p>
<div class="table-wrap"><table><thead><tr><th>Repository</th><th>Description</th><th>Source videos</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan="3">No repository links found in the available descriptions.</td></tr>'}</tbody></table></div>
<script>
const search = document.getElementById('repo-search');
const count = document.getElementById('search-count');
const noMatches = document.getElementById('no-matches');
const rows = Array.from(document.querySelectorAll('.repo-row'), row => ({{
  element: row,
  text: (row.textContent + ' ' + Array.from(row.querySelectorAll('a'), a => a.href).join(' ')).toLowerCase()
}}));
function filterRepos() {{
  const words = search.value.toLowerCase().trim().split(/\\s+/).filter(Boolean);
  let visible = 0;
  for (const row of rows) {{
    const matches = words.every(word => row.text.includes(word));
    row.element.hidden = !matches;
    if (matches) visible++;
  }}
  count.textContent = `Showing ${{visible}} of ${{rows.length}} repositories`;
  noMatches.hidden = visible > 0 || rows.length === 0;
}}
search.addEventListener('input', filterRepos);
filterRepos();
</script>
</body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true', help='Re-fetch all video descriptions and GitHub metadata')
    args = parser.parse_args()
    if not shutil.which('yt-dlp'):
        parser.error('Install yt-dlp first: python3 -m pip install -U yt-dlp')
    lock = (HERE / '.update.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError('Another update is already running.')
    cache_path = HERE / 'cache.json'
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {'videos': {}, 'repos': {}}
    print('Listing channel videos and Shorts...', flush=True)
    listing = {v['id']: v for v in videos_in(youtube(CHANNEL))}
    if not listing:
        raise RuntimeError('No videos returned; existing page was left untouched.')
    pending = [v for vid, v in listing.items() if args.refresh or vid not in cache['videos']]
    print(f'{len(listing)} videos listed; {len(pending)} descriptions to fetch.', flush=True)
    failed = []
    with ThreadPoolExecutor(max_workers=1) as pool:
        futures = {pool.submit(fetch_video, v): v['id'] for v in pending}
        for count, future in enumerate(as_completed(futures), 1):
            vid = futures[future]
            try:
                cache['videos'][vid] = future.result()
            except Exception as error:
                failed.append(vid)
                print(f'Warning: {vid}: {error}', file=sys.stderr)
            atomic_write(cache_path, json.dumps(cache, indent=2))
            if count % 10 == 0 or count == len(pending):
                print(f'Descriptions: {count}/{len(pending)} ({len(failed)} failed)', flush=True)
    videos = {vid: cache['videos'][vid] for vid in listing if vid in cache['videos']}
    if not videos:
        raise RuntimeError('No descriptions available; existing page was left untouched.')
    mentions = {}
    for vid, video in videos.items():
        for name in repo_names(video['description']):
            mentions.setdefault(name, []).append(vid)
    repos, metadata_failures = {}, 0
    rate_limited = False
    print(f'Fetching metadata for {len(mentions)} repositories...', flush=True)
    for name, sources in sorted(mentions.items()):
        if (args.refresh or name not in cache['repos']) and not rate_limited:
            try:
                cache['repos'][name] = github_repo(name)
                atomic_write(cache_path, json.dumps(cache, indent=2))
            except (HTTPError, URLError, TimeoutError) as error:
                print(f'Warning: GitHub {name}: {error}', file=sys.stderr)
                metadata_failures += 1
                if isinstance(error, HTTPError) and error.code in {403, 429}:
                    rate_limited = True
        info = cache['repos'].get(name, {'name': name, 'url': 'https://github.com/' + name,
                                       'description': 'GitHub metadata unavailable; repository link is unverified.'})
        canonical = info['name'].lower()
        if canonical in repos:
            repos[canonical]['videos'] = sorted(set(repos[canonical]['videos'] + sources))
        else:
            repos[canonical] = dict(info, videos=sources)
    notes = []
    if failed:
        notes.append(f'{len(failed)} video descriptions could not be refreshed. Cached descriptions were used where available; this run may be incomplete.')
    if metadata_failures:
        notes.append('Some GitHub metadata could not be refreshed. Cached descriptions are retained; unavailable metadata is labeled.')
    atomic_write(cache_path, json.dumps(cache, indent=2))
    atomic_write(HERE / 'index.html', render(repos, videos, CHANNEL, notes))
    print(f'Wrote {HERE / "index.html"}: {len(repos)} repos from {len(videos)} descriptions.', flush=True)
    return 1 if failed or metadata_failures else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, subprocess.SubprocessError, ValueError, OSError) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)
