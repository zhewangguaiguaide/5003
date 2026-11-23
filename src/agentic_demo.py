"""Two-round synthetic N7 demo, no school policy, gold, model or network."""
from __future__ import annotations

import json

from .local_demo import DemoRetriever
from .retriever import Hit


class AgentDemoRetriever(DemoRetriever):
    def search(self, query, topic=None, k=5):
        if "additional synthetic detail" not in query.casefold():
            return super().search(query, topic, k)
        url = "https://example.invalid/n7-demo"
        return [Hit(url + "#chunk-0", url,
                    "The additional synthetic detail is a second development fixture, not school policy.",
                    1.0, url, "Synthetic N7 fixture", "学费与缴费", "")]


class AgentDemoClient:
    def chat(self, messages, tools=None):
        payload = json.loads(messages[-1]["content"])
        if payload.get("task") == "review_answer":
            response = {"verdict": "accept", "requirements": [{"request": "Both synthetic fixtures", "covered": True}],
                        "unsupported_statements": [], "missing_information": [], "reason": "Both fixtures support the draft."}
        elif len(payload["history"]) == 1:
            response = {"action": "retrieve", "reason": "The second fixture is missing.",
                        "missing_information": ["Additional synthetic detail"],
                        "query": "additional synthetic detail", "topic": None}
        else:
            response = {"action": "answer", "reason": "Both development fixtures are now available.",
                        "missing_information": [], "response": {
                            "status": "answered", "statements": [
                                {"text": "This is synthetic development evidence.", "source_ids": ["S1"]},
                                {"text": "The additional synthetic detail is a second development fixture.",
                                 "source_ids": ["S2"]}], "message": ""}}
        return {"role": "assistant", "content": json.dumps(response)}
