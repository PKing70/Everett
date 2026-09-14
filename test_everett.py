import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import unittest
import urllib.error
import xml.etree.ElementTree as ET

import tarfile
import types
ARCHIVE = tarfile.open(Path(__file__).resolve().parent / 'everett_police-1.0.0.tar.gz')
m = types.ModuleType('collector')
exec(compile(ARCHIVE.extractfile('everett_police/bin/everett_police.py').read(), 'everett_police.py', 'exec'), m.__dict__)

class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE records(id TEXT PRIMARY KEY,digest TEXT NOT NULL)')
        self.events = []

    def tearDown(self):
        self.db.close()

    def run_scan(self, rows, size=1):
        pages = []
        def fetch(page, count, token):
            pages.append(page)
            return rows[(page-1)*count:page*count]
        result = m.collect(self.db, 'everett_police://test', size, '', fetch,
                           lambda s, e: self.events.append(e))
        return result, pages

    def test_pagination_dedup_updates_and_coordinates(self):
        rows = [{'eventnumber': '1', 'geomcoordinate': {'coordinates': [-122.2, 47.9]}},
                {'eventnumber': '2', 'disposition': 'open'}]
        result, pages = self.run_scan(rows)
        self.assertEqual(pages, [1, 2, 3])
        self.assertEqual(result['rows_emitted'], 2)
        self.assertEqual(self.events[0]['latitude'], 47.9)
        self.assertEqual(self.run_scan(rows)[0]['rows_emitted'], 0)
        rows[1]['disposition'] = 'closed'
        self.assertEqual(self.run_scan(rows)[0]['rows_emitted'], 1)

    def test_failed_output_does_not_checkpoint(self):
        def fail(*args):
            raise OSError('pipe failed')
        with self.assertRaises(OSError):
            m.collect(self.db, 'test', 10, '', lambda *a: [{'eventnumber': '1'}], fail)
        self.assertEqual(self.db.execute('SELECT count(*) FROM records').fetchone()[0], 0)

    def test_missing_id_fails(self):
        with self.assertRaises(ValueError):
            self.run_scan([{'incidenttype': 'TEST'}])

    def test_repeated_page_fails(self):
        with self.assertRaises(ValueError):
            m.collect(self.db, 'test', 1, '', lambda *a: [{'eventnumber': '1'}], lambda *a: None)

    def test_request_and_retry(self):
        calls, delays = [], []
        def opener(req, timeout):
            calls.append(req)
            if len(calls) == 1:
                raise urllib.error.HTTPError(req.full_url, 429, 'busy', {'Retry-After': '2'}, None)
            return io.BytesIO(b'[{"eventnumber":"1"}]')
        self.assertEqual(len(m.fetch_page(2, 50, 'example', opener, delays.append)), 1)
        payload = json.loads(calls[-1].data)
        self.assertEqual(payload['page'], {'pageNumber': 2, 'pageSize': 50})
        self.assertEqual(calls[-1].get_header('X-app-token'), 'example')
        self.assertEqual(delays, [2])

    def test_malformed_response(self):
        with self.assertRaises(ValueError):
            m.fetch_page(1, 10, '', lambda *a, **k: io.BytesIO(b'{"error":"bad"}'))

    def test_validation_and_scheme(self):
        self.assertEqual(m.settings({})[:2], (3600, 1000))
        for params in [{'page_size':'0'}, {'poll_seconds':'2'}, {'page_size':'bad'}]:
            with self.assertRaises(ValueError):
                m.settings(params)
        self.assertEqual(ET.fromstring(m.scheme()).findtext('streaming_mode'), 'xml')

    def test_lookback(self):
        self.assertEqual(m.scan_query(0), 'SELECT * ORDER BY eventnumber')
        self.assertIn("2026-08-14T00:00:00", m.scan_query(30, m.datetime(2026, 9, 14, tzinfo=m.timezone.utc)))
        with self.assertRaises(ValueError):
            m.settings({'lookback_days': '-1'})

    def test_event_xml_and_dashboard_xml(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            m.emit('everett_police://test', {'eventnumber': '<&"'})
        event = ET.fromstring(buf.getvalue())
        self.assertEqual(event.attrib['unbroken'], '1')
        self.assertIsNotNone(event.find('done'))
        self.assertEqual(json.loads(event.findtext('data'))['eventnumber'], '<&"')
        for path in [n for n in ARCHIVE.getnames() if n.endswith('.xml')]:
            ET.parse(ARCHIVE.extractfile(path))


if __name__ == '__main__':
    unittest.main()

