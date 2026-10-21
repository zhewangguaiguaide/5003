import unittest
from unittest.mock import patch, mock_open
from src.crawler import ColumnCrawler, ColumnSpec
from src.fetcher import FakeFetcher, FetchError
from src.storage import MockStorage, Record
from src.parser import extract_links, extract_title, is_navigation_only
from src.corpus import deduplicate


class AcceptanceRepairs(unittest.TestCase):
    def test_duplicate_title_elements(self):
        self.assertEqual(extract_title('<title>ARRO</title><title>ARRO</title>'), 'ARRO')
        self.assertEqual(extract_title('<title>ARROARRO</title>'), 'ARRO')

    def test_base_href_resolves_arro_relative_links(self):
        html = '<base href="https://www.cityu.edu.hk/arro/"><a href="enrl/enrl_main.htm">Enroll</a>'
        self.assertEqual(extract_links(html, 'https://www.cityu.edu.hk/arro/regu/regu_rule.htm'),
                         ['https://www.cityu.edu.hk/arro/enrl/enrl_main.htm'])

    def test_navigation_and_failure_not_exported(self):
        content = '\n'.join(['Hall ' + str(i) + ' ' + 'name ' * 5 for i in range(10)])
        self.assertTrue(is_navigation_only(content))
        rows, stats = deduplicate([Record(url='https://x/a', content=content),
                                   Record(url='https://x/b', error='404')])
        self.assertEqual(rows, [])
        self.assertEqual(stats['rejected'], 2)

    def test_full_scan_all_seeds_despite_existing_link(self):
        seeds = ['https://x/a', 'https://x/b']
        body = '<p>' + 'Useful student information. ' * 30 + '</p>'
        pages = {seeds[0]: '<a href="/old">old</a>' + body, seeds[1]: body}
        storage = MockStorage()
        storage.upsert(Record(url='https://x/old', content='old'))
        column = ColumnSpec(name='test', seeds=seeds, max_pages=2)
        with patch('pathlib.Path.open', mock_open()):
            stats = ColumnCrawler(column, FakeFetcher(pages), storage).crawl_full(0)
        self.assertEqual(stats.list_pages, 2)
        self.assertTrue(all(storage.exists(u) for u in seeds))

    def test_failed_record_is_retryable(self):
        storage = MockStorage()
        storage.upsert(Record(url='https://x/a', error='timeout'))
        self.assertFalse(storage.exists('https://x/a'))

    def test_two_repair_loops_recover_persisted_failure(self):
        class Flaky:
            attempts = 0
            def fetch(self, url):
                if url.endswith('/seed'):
                    return '<a href="/detail">detail</a>'
                self.attempts += 1
                if self.attempts < 3:
                    raise FetchError('timeout')
                return '<p>' + 'Student information. ' * 30 + '</p>'
        storage = MockStorage()
        column = ColumnSpec(name='retry', seeds=['https://x/seed'])
        stats = ColumnCrawler(column, Flaky(), storage).crawl(repair_loops=2)
        self.assertEqual(stats.errors, [])
        self.assertEqual(stats.repaired, 1)
        self.assertTrue(storage.exists('https://x/detail'))
        self.assertEqual(storage.rows['https://x/detail'].error, '')
