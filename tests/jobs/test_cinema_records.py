import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2] / 'subsystems/jobs/cinema'


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cc = load('cinema_candidates', 'cinema-candidates.py')
cr = load('cinema_rights', 'cinema-rights.py')

CC_BY = 'http://creativecommons.org/licenses/by/3.0/'
MD5 = 'a' * 32
CANDIDATE = ('Freaks', 1932, 'A reason.')


def item_metadata():
    return {'metadata': {'licenseurl': CC_BY, 'creator': 'Tod Browning'},
            'files': [{'name': 'film.mp4', 'size': '900', 'md5': MD5, 'height': '480', 'length': '5400'}]}


def fetch(url):
    if 'advancedsearch' in url:
        return {'response': {'docs': [{'identifier': 'good-item'}]}}
    return item_metadata()


class ResolverRecordTests(unittest.TestCase):
    def test_a_resolved_film_gets_a_rights_entry_with_its_archive_metadata(self):
        records = []
        cc.resolve(CANDIDATE, fetch=fetch, records=records)
        self.assertEqual(len(records), 1)
        entry = records[0]
        self.assertEqual(entry['key'], 'freaks-1932')
        self.assertEqual(entry['item'], 'https://archive.org/details/good-item')
        self.assertEqual(entry['license'], CC_BY)
        self.assertEqual(entry['creator'], 'Tod Browning')
        self.assertEqual(entry['archive_metadata'], item_metadata())

    def test_nothing_is_recorded_when_no_item_is_eligible(self):
        records = []
        cc.resolve(CANDIDATE, fetch=lambda url: {'response': {'docs': []}} if 'advancedsearch' in url else {}, records=records)
        self.assertEqual(records, [])


class CandidateRightsTests(unittest.TestCase):
    def test_a_candidate_outside_the_catalogue_gets_a_dossier(self):
        records = []
        cc.resolve(CANDIDATE, fetch=fetch, records=records)
        with tempfile.TemporaryDirectory() as tmp:
            records_path = Path(tmp) / 'candidate-records.json'
            records_path.write_text(json.dumps(records))
            destination = Path(tmp) / 'dossier'
            cr.prepare(HERE / 'rights-evidence', 'freaks-1932', 'archive',
                       'https://archive.org/download/good-item/film.mp4', '900', MD5, destination,
                       records=str(records_path))
            transfer = json.loads((destination / 'transfer.json').read_text())
            self.assertEqual((transfer['film'], transfer['year'], transfer['bytes']), ('Freaks', 1932, 900))
            self.assertEqual(json.loads((destination / 'source-metadata.json').read_text()), item_metadata())
            self.assertTrue((destination / 'CC-BY-3.0.txt').exists())
            self.assertIn('Tod Browning', (destination / 'RIGHTS.txt').read_text())

    def test_catalogue_films_still_work_without_a_candidate_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'dossier'
            cr.prepare(HERE / 'rights-evidence', 'the-general-1926', 'archive',
                       'https://archive.org/download/x/general.mp4', '900', MD5, destination,
                       records=str(Path(tmp) / 'missing.json'))
            self.assertTrue((destination / 'transfer.json').exists())

    def test_a_key_with_no_record_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(LookupError):
                cr.prepare(HERE / 'rights-evidence', 'no-such-film-1900', 'archive',
                           'https://archive.org/download/x/y.mp4', '900', MD5, Path(tmp) / 'dossier')


if __name__ == '__main__':
    unittest.main()
