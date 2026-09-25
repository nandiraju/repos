import unittest
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from update_repos import repo_names, videos_in, render, fetch_video, YOUTUBE_THROTTLED


class RepoTests(unittest.TestCase):
    def test_normalizes_and_deduplicates_repository_links(self):
        text = ('https://github.com/Owner/Repo/tree/main and '
                'https://github.com/owner/repo.git. '
                '(https://github.com/Other/tool/issues/2) '
                'https%3A%2F%2Fgithub.com%2Fthird%2Fproject')
        self.assertEqual(repo_names(text), {'owner/repo', 'other/tool', 'third/project'})

    def test_ignores_non_repository_and_lookalike_links(self):
        self.assertEqual(repo_names('https://github.com/person '
                                   'https://github.com/topics/python '
                                   'https://evilgithub.com/owner/repo '
                                   'https://not.github.com/owner/repo'), set())

    def test_nested_channel_tabs(self):
        data = {'entries': [{'entries': [{'id': 'video'}, None]}, {'entries': [{'id': 'short'}]}]}
        self.assertEqual([v['id'] for v in videos_in(data)], ['video', 'short'])

    @patch('update_repos.time.sleep')
    def test_uses_full_description_not_shortened_display_links(self, _sleep):
        page = b'var ytInitialPlayerResponse = {"videoDetails":{"videoId":"abc","title":"Example","shortDescription":"https://github.com/abi/screenshot-to-code"}};'
        with patch('update_repos.urlopen', return_value=io.BytesIO(page)):
            video = fetch_video({'id': 'abc'})
        self.assertEqual(repo_names(video['description']), {'abi/screenshot-to-code'})

    @patch('update_repos.time.sleep')
    def test_rejects_missing_description_instead_of_caching_empty_text(self, _sleep):
        with patch('update_repos.urlopen', return_value=io.BytesIO(b'var ytInitialPlayerResponse = {};')):
            with self.assertRaises(RuntimeError):
                fetch_video({'id': 'abc'})

    @patch('update_repos.time.sleep')
    def test_persistent_rate_limit_defers_remaining_requests(self, _sleep):
        error = HTTPError('https://www.youtube.com', 429, 'Too Many Requests', {}, None)
        try:
            with patch('update_repos.urlopen', side_effect=error) as request:
                with self.assertRaises(HTTPError):
                    fetch_video({'id': 'abc'})
                self.assertEqual(request.call_count, 3)
                with self.assertRaises(RuntimeError):
                    fetch_video({'id': 'def'})
                self.assertEqual(request.call_count, 3)
        finally:
            error.close()
            YOUTUBE_THROTTLED.clear()

    def test_shared_repo_has_both_channel_filters(self):
        from html import unescape
        repos = {'owner/repo': {'name': 'owner/repo', 'url': 'https://github.com/owner/repo',
                               'description': 'Example', 'videos': ['a', 'b']}}
        videos = {'a': {'title': 'First video', 'channel': 'The Next New Thing'},
                  'b': {'title': 'Second video', 'channel': 'Cloud Codes'}}
        html = render(repos, videos, {'The Next New Thing': 'url1', 'Cloud Codes': 'url2'}, [])
        self.assertEqual(html.count('class="repo-row"'), 1)
        self.assertIn('data-channels="["Cloud Codes", "The Next New Thing"]"', unescape(html))
        self.assertIn('<option value="">All channels</option>', html)
        self.assertIn('First video', html)
        self.assertIn('Second video', html)

    def test_update_migrates_old_cache_and_keeps_page_stable(self):
        import update_repos as app
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = {'videos': {'a': {'title': 'Old video', 'description': 'https://github.com/test/repo'}},
                   'repos': {'test/repo': {'name': 'test/repo', 'url': 'https://github.com/test/repo', 'description': 'Demo', 'stars': 12, 'checked_on': app.datetime.now(app.timezone.utc).date().isoformat()}}}
            (root / 'cache.json').write_text(json.dumps(old))
            listing = lambda url: {'entries': [{'id': 'a' if 'TheNextNewThingAI' in url else 'b'}]}
            with patch.object(app, 'HERE', root), patch.object(app.sys, 'argv', ['update_repos.py']), \
                 patch.object(app.shutil, 'which', return_value='/bin/yt-dlp'), \
                 patch.object(app, 'youtube', side_effect=listing), \
                 patch.object(app, 'fetch_video', return_value={'title': 'New video', 'description': 'https://github.com/test/repo'}) as fetch, \
                 patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(app.main(), 0)
                first = (root / 'index.html').read_text()
                cache = json.loads((root / 'cache.json').read_text())
                self.assertEqual(cache['videos']['a']['channel'], 'The Next New Thing')
                self.assertEqual(cache['videos']['b']['channel'], 'Cloud Codes')
                self.assertEqual(first.count('class="repo-row"'), 1)
                self.assertEqual(app.main(), 0)
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual((root / 'index.html').read_text(), first)

    def test_exact_star_counts(self):
        from update_repos import GitHubMetadata
        parser = GitHubMetadata()
        parser.feed('<span id="repo-stars-counter-star" title="148,055">148k</span>')
        self.assertEqual(parser.stars, 148055)
        parser.feed('<span id="repo-stars-counter-star" title="0">0</span>')
        self.assertEqual(parser.stars, 0)

    def test_external_text_is_escaped(self):
        repos = {'owner/repo': {'name': 'owner/repo', 'url': 'https://github.com/owner/repo',
                               'description': '<script>alert(1)</script>', 'videos': ['abc']}}
        html = render(repos, {'abc': {'title': '<img src=x>', 'channel': 'Test channel'}}, {'Test channel': 'https://youtube.com'}, ['Partial results'])
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertNotIn('<img src=x>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('Partial results', html)
        self.assertIn('watch?v=abc', html)


if __name__ == '__main__':
    unittest.main()
