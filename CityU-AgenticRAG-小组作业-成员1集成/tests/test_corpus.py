import json
import unittest
import os
from pathlib import Path

from src.corpus import canonicalize_url, deduplicate, export_jsonl, infer_academic_year
from src.storage import Record


class TestCorpusQuality(unittest.TestCase):
    def test_canonicalize_url_removes_tracking_noise(self):
        self.assertEqual(
            canonicalize_url("HTTPS://WWW.CityU.edu.hk/a/?utm_source=x&b=2#part"),
            "https://www.cityu.edu.hk/a?b=2",
        )

    def test_deduplicate_by_url_and_content(self):
        first = Record(url="https://x.test/a/", title="A", content="same text", crawled_at="1")
        alias = Record(url="https://x.test/a?utm_source=z", title="A2", content="same text", crawled_at="2")
        other_url = Record(url="https://x.test/b", title="B", content="same text", crawled_at="3")
        rows, stats = deduplicate([first, alias, other_url])
        self.assertEqual(len(rows), 1)
        self.assertEqual(stats["output"], 1)
        self.assertEqual(rows[0].url, other_url.url)

    def test_export_contains_academic_year(self):
        record = Record(url="https://x.test/calendar", title="Calendar 2026/27", content="Dates")
        self.assertEqual(infer_academic_year(record), "2026-2027")
        path = str(Path(__file__).parent / "_tmp_corpus.jsonl")
        try:
            stats = export_jsonl([record], path)
            row = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertEqual(stats["output"], 1)
            self.assertEqual(row["academic_year"], "2026-2027")
            self.assertEqual(row["url"], "https://x.test/calendar")
        finally:
            if os.path.exists(path):
                os.remove(path)


if __name__ == "__main__":
    unittest.main()
