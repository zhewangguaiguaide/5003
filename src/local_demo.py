"""Synthetic N5 plumbing demo. These are not school facts or evaluation gold."""
from __future__ import annotations

import json

from .retriever import Hit


class DemoRetriever:
    model_name = "synthetic-no-embedding"

    def list_topics(self):
        return ["学费与缴费"]

    def search(self, query, topic=None, k=5):
        if not query.strip() or k <= 0:
            return []
        return [Hit(
            chunk_id="synthetic-demo#chunk-0",
            doc_id="https://example.invalid/n5-demo",
            text="This is synthetic development evidence. It is not school policy.",
            score=1.0,
            url="https://example.invalid/n5-demo",
            title="Synthetic N5 plumbing demo",
            topic="学费与缴费",
            academic_year="",
        )]


class DemoClient:
    def chat(self, messages, tools=None):
        return {"role": "assistant", "content": json.dumps({
            "status": "answered",
            "statements": [{
                "text": "This is synthetic development evidence.",
                "source_ids": ["S1"],
            }],
            "message": "",
        })}
