import json
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock, patch

from src.retriever import Hit, Retriever


INDEX_DIR = Path(__file__).resolve().parents[1] / "data" / "wsb_index"


class TestRetriever(unittest.TestCase):

    def setUp(self):
                self.r = Retriever("data/wsb_index")

    def test_index_consistency(self):
        self.assertEqual(self.r.index.ntotal, len(self.r.chunks))
        self.assertEqual(self.r.index.ntotal, 862)
        self.assertEqual(self.r.index.d, 384)

    def test_topics(self):
        topics = self.r.list_topics()
        self.assertEqual(len(topics), 8)
        self.assertIn("图书馆", topics)
        self.assertIn("学费与缴费", topics)

    def test_invalid_inputs(self):
        self.assertEqual(self.r.search(""), [])
        self.assertEqual(self.r.search("   "), [])
        self.assertEqual(self.r.search("test", k=0), [])
        self.assertEqual(self.r.search("test", k=-1), [])
        self.assertEqual(
            self.r.search("test", topic="不存在的主题"), []
        )

    def test_search_and_topic_filter(self):
        fake_model = Mock()
        fake_model.encode.return_value = (
            self.r.index.reconstruct(0).reshape(1, -1)
        )
        self.r._model = fake_model

        hits = self.r.search("test question", k=3)
        self.assertEqual(len(hits), 3)
        self.assertTrue(all(isinstance(h, Hit) for h in hits))

        topic_hits = self.r.search(
            "test question", topic="图书馆", k=3
        )
        self.assertEqual(len(topic_hits), 3)
        self.assertTrue(
            all(h.topic == "图书馆" for h in topic_hits)
        )

    def test_json_serialization(self):
        hit = Hit("c1", "d1", "text", 0.9,
                  "url", "title", "图书馆", "")
        data = json.dumps(asdict(hit), ensure_ascii=False)
        self.assertIn("chunk_id", data)
        self.assertIn("图书馆", data)

    def test_rerank_order(self):
        hits = [
            Hit("c1", "d1", "first", 0.9, "u1", "t1", "图书馆", ""),
            Hit("c2", "d2", "second", 0.8, "u2", "t2", "图书馆", "")
        ]
        with patch("sentence_transformers.CrossEncoder") as model:
            model.return_value.predict.return_value = [1.0, 2.0]
            ranked = self.r.rerank_hits("question", hits)

        self.assertEqual(ranked[0].chunk_id, "c2")
        self.assertEqual(ranked[0].score, 2.0)


if __name__ == "__main__":
    unittest.main()
