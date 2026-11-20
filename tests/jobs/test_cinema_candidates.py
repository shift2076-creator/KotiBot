import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('cinema_candidates', Path(__file__).resolve().parents[2] / 'subsystems/jobs/cinema/cinema-candidates.py')
cc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cc)

CC_BY = 'http://creativecommons.org/licenses/by/3.0/'
MD5 = 'a' * 32


def metadata(license_url=CC_BY, files=None):
    return {'metadata': {'licenseurl': license_url},
            'files': files if files is not None else [
                {'name': 'film.mp4', 'size': '700000000', 'md5': MD5, 'height': '480', 'length': '5400'}]}


class PickFileTests(unittest.TestCase):
    def test_picks_the_largest_eligible_mp4_under_a_cc_license(self):
        files = [{'name': 'small.mp4', 'size': '100', 'md5': MD5, 'height': '240', 'length': '60'},
                 {'name': 'film.mp4', 'size': '900', 'md5': MD5, 'height': '480', 'length': '5400'},
                 {'name': 'film.mkv', 'size': '9000', 'md5': MD5, 'height': '1080', 'length': '5400'}]
        name, size, md5, height, minutes, _ = cc.pick_file(metadata(files=files))
        self.assertEqual((name, size, height, minutes), ('film.mp4', 900, 480, 90.0))

    def test_refuses_an_item_without_a_cc_or_public_domain_license(self):
        self.assertIsNone(cc.pick_file(metadata(license_url='https://example.com/all-rights-reserved')))
        self.assertIsNone(cc.pick_file(metadata(license_url='')))

    def test_refuses_a_file_without_an_md5_or_size(self):
        files = [{'name': 'film.mp4', 'size': '900', 'md5': '', 'height': '480', 'length': '60'}]
        self.assertIsNone(cc.pick_file(metadata(files=files)))
        files = [{'name': 'film.mp4', 'md5': MD5, 'height': '480', 'length': '60'}]
        self.assertIsNone(cc.pick_file(metadata(files=files)))

    def test_refuses_a_file_over_the_size_cap(self):
        files = [{'name': 'film.mp4', 'size': str(cc.MAX_BYTES + 1), 'md5': MD5, 'height': '480', 'length': '60'}]
        self.assertIsNone(cc.pick_file(metadata(files=files)))


class RowTests(unittest.TestCase):
    def test_row_matches_the_queue_format(self):
        picked = ('film.mp4', 700000000, MD5, 480, 90.0, CC_BY)
        fields = cc.row(('Freaks', 1932, 'A reason.'), 'freaks_1932', picked).split('\t')
        self.assertEqual(len(fields), 12)
        self.assertEqual(fields[0:4], ['film', 'freaks-1932', 'Freaks', '1932'])
        self.assertEqual(fields[4], 'https://archive.org/download/freaks_1932/film.mp4')
        self.assertEqual(fields[5:8], ['700000000', MD5, '-'])
        self.assertEqual(fields[10:12], ['90.0', '480'])


class ResolveTests(unittest.TestCase):
    def test_resolves_the_first_item_with_an_eligible_file(self):
        def fetch(url):
            if 'advancedsearch' in url:
                return {'response': {'docs': [{'identifier': 'no-license'}, {'identifier': 'good-item'}]}}
            if url.endswith('no-license'):
                return metadata(license_url='https://example.com/x')
            return metadata()
        line = cc.resolve(('Freaks', 1932, 'A reason.'), fetch=fetch)
        self.assertIn('https://archive.org/download/good-item/film.mp4', line)

    def test_returns_none_when_nothing_eligible(self):
        def fetch(url):
            if 'advancedsearch' in url:
                return {'response': {'docs': [{'identifier': 'x'}]}}
            return metadata(license_url='')
        self.assertIsNone(cc.resolve(('Freaks', 1932, 'A reason.'), fetch=fetch))

    def test_search_is_limited_to_movies_with_the_year(self):
        url = cc.search_url('Freaks', 1932)
        self.assertIn('mediatype%3Amovies', url)
        self.assertIn('year%3A1932', url)

    def test_fetch_refuses_hosts_other_than_archive_org(self):
        with self.assertRaises(ValueError):
            cc.get_json('https://example.com/metadata.json')


class ReadTests(unittest.TestCase):
    def test_candidates_file_skips_comments_and_blank_lines(self):
        import tempfile
        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write('# comment\n\nFreaks|1932|A reason.\n')
        self.assertEqual(cc.read_candidates(f.name), [('Freaks', 1932, 'A reason.')])


if __name__ == '__main__':
    unittest.main()
