import unittest
import io
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
            YOUTUBE_THROTTLED.clear()

    def test_external_text_is_escaped(self):
        repos = {'owner/repo': {'name': 'owner/repo', 'url': 'https://github.com/owner/repo',
                               'description': '<script>alert(1)</script>', 'videos': ['abc']}}
        html = render(repos, {'abc': {'title': '<img src=x>'}}, 'https://youtube.com', ['Partial results'])
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertNotIn('<img src=x>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('Partial results', html)
        self.assertIn('watch?v=abc', html)


if __name__ == '__main__':
    unittest.main()
