"""Offline-first evidence QA for the DSC5003 CityUHK frontend.

Reads the frozen R05 881-chunk retrieval snapshot and answers only from those
chunks. Live mode uses a configured model for an evidence-bound answer plus an
independent support review; offline mode quotes the best matching sentences.
Citations, URLs and source identities are always mapped by this server.
"""
from __future__ import annotations

import collections
import hashlib
import json
import math
import os
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TOPIC_LABEL = {
    "fees": "学费与缴费",
    "library": "图书馆",
    "scholarship": "奖学金与助学金",
    "admission": "申请",
    "visa": "签证与国际学生服务",
    "registration": "注册与学籍",
    "residence": "宿舍",
    "calendar": "校历与重要日期",
}

TOPIC_ALIASES = {
    "admission": "申请",
    "visa": None,
    "visa_geo": None,
    "registration": "注册与学籍",
    "residence": "宿舍",
    "fees": "学费与缴费",
    "scholarship": "奖学金与助学金",
    "library": "图书馆",
    "calendar": "校历与重要日期",
}

TOPIC_TERMS = {
    "fees": [("tuition", 4), ("fee", 3), ("fees", 3), ("payment", 3), ("pay", 2),
             ("settle", 2), ("student account", 3), ("refund", 4), ("refundable", 4),
             ("deferral", 3), ("学费", 4), ("缴费", 4), ("支付", 3), ("付款", 3),
             ("退款", 4), ("退费", 4), ("交学费", 4)],
    "library": [("library", 4), ("libguides", 4), ("borrow", 4), ("borrowing", 4),
                ("library access", 4), ("enter the library", 4), ("id card", 3),
                ("eid", 3), ("图书馆", 4), ("借书", 4), ("借阅", 4),
                ("进入图书馆", 4), ("学生证", 3)],
    "scholarship": [("scholarship", 4), ("scholarships", 4), ("entrance scholarship", 4),
                    ("bursary", 4), ("bursaries", 4), ("financial assistance", 3),
                    ("emergency fund", 4), ("loan", 2), ("奖学金", 4), ("助学金", 4),
                    ("助学", 3), ("贷款", 3), ("紧急基金", 4)],
    "admission": [("admission", 4), ("admissions", 4), ("apply", 1), ("application", 2),
                  ("jupas", 4), ("non-jupas", 4), ("programme", 2), ("programmes", 2),
                  ("offer", 2), ("入学", 4), ("申请", 1), ("录取", 4), ("报名", 3)],
    "visa": [("visa", 4), ("immigration", 3), ("non-local", 3), ("exchange", 2),
             ("inbound", 2), ("outbound", 2), ("签证", 4), ("入境", 4),
             ("交换", 2), ("非本地", 3)],
    "registration": [("registration", 4), ("register", 3), ("course", 2), ("courses", 2),
                     ("add/drop", 4), ("credit", 2), ("credits", 2), ("transcript", 4),
                     ("graduation", 3), ("注册", 4), ("选课", 4), ("学分", 3),
                     ("成绩单", 4), ("毕业", 3)],
    "residence": [("hostel", 4), ("hostels", 4), ("residence", 4), ("housing", 4),
                  ("accommodation", 4), ("dormitory", 4), ("宿舍", 4), ("住宿", 4),
                  ("宿位", 4)],
    "calendar": [("calendar", 4), ("semester", 3), ("term dates", 4), ("deadline", 3),
                 ("timetable", 3), ("important dates", 4), ("校历", 4), ("学期", 3),
                 ("开学", 3), ("截止日期", 4), ("时间表", 3)],
}

REFUND_OBJECTS = ("tuition", "fee", "fees", "course", "hostel", "hall", "residence",
                  "housing", "deposit", "acceptance fee", "overpayment", "student account",
                  "学费", "课程", "宿舍", "住宿", "押金", "留位费", "多缴", "账户")

OUT_OF_SCOPE_OBJECTS = ("job", "employment", "credit card", "bank account", "passport",
                        "driving licence", "driver license", "mortgage", "loan application",
                        "工作", "求职", "信用卡", "银行账户", "护照", "驾照", "房贷")

STOPWORDS = set(
    "a an the and or of to in on for by with from is are was were be been being "
    "this that these those it its as at into about than then there their they you "
    "your we our can could should would may might will shall do does did not no yes "
    "i me my he she his her them also more most other such only own same so too very "
    "s t just don now".split()
)

SYNONYMS = {
    "tuition": ["tuition", "fee", "fees", "student account", "payment", "pay", "settle"],
    "fee": ["fee", "fees", "tuition", "payment"],
    "fees": ["fees", "fee", "tuition", "payment"],
    "pay": ["pay", "payment", "settle", "settlement", "methods"],
    "payment": ["payment", "pay", "settle", "settlement", "methods"],
    "library": ["library", "libguides", "borrow", "access", "eid", "id card"],
    "enter": ["enter", "entry", "access"],
    "borrow": ["borrow", "borrowing", "loan", "items"],
    "refund": ["refund", "refundable", "withdrawal", "withdraw", "overpayment"],
    "scholarship": ["scholarship", "scholarships", "entrance", "award", "awarded"],
    "apply": ["apply", "application", "submit", "deadline"],
    "visa": ["visa", "immigration", "student visa", "entry permit"],
    "hostel": ["hostel", "residence", "housing", "accommodation"],
    "course": ["course", "courses", "add/drop", "registration"],
    "deadline": ["deadline", "due", "date", "period"],
    "semester": ["semester", "term", "calendar", "dates"],
}

ZH_TERMS = {
    "学费": ["tuition", "fee"], "缴费": ["pay", "payment", "settle"],
    "怎么交": ["pay", "payment", "methods", "settle"], "如何缴": ["pay", "payment", "methods"],
    "缴费方式": ["payment", "methods"], "怎么付": ["pay", "payment", "methods"],
    "支付": ["pay", "payment"], "付款": ["pay", "payment"],
    "退款": ["refund"], "退费": ["refund"], "图书馆": ["library"],
    "进入": ["enter", "access"], "借书": ["borrow"], "借阅": ["borrow"],
    "学生证": ["id card", "cityuhk id"], "奖学金": ["scholarship"],
    "助学金": ["financial assistance", "bursary"], "签证": ["visa"],
    "入境": ["immigration", "entry permit"], "宿舍": ["hostel", "residence", "housing"],
    "住宿": ["accommodation", "hostel"], "注册": ["registration", "register"],
    "选课": ["course", "add/drop"], "校历": ["calendar", "important dates"],
    "截止": ["deadline"], "申请": ["apply", "application", "admission"],
    "入学": ["admission", "entrance"], "非本地": ["non-local"], "本地": ["local"],
    "交换": ["exchange"], "毕业": ["graduation"], "成绩单": ["transcript"],
    "学分": ["credit"],
}

SCOPE_EN = ("Scope: 159 CityUHK student-services pages in 8 configured topics "
            "(admission, visa, registration, residence, fees, scholarships, library, calendar). "
            "It is not the whole CityUHK website and not a general-purpose assistant.")
SCOPE_ZH = ("范围：索引只覆盖8个配置主题下的159篇城大学生服务页面"
            "（申请、签证、注册、宿舍、学费、奖学金、图书馆、校历），不是城大网站全量，也不是通用助手。")

DATE_RE = re.compile(
    r"\b(?:\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)"
    r"|(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}"
    r"|\d{1,2}[/-]\d{1,2}[/-]20\d{2})\b", re.I)

LEAD_EN = {
    "fees": "From the indexed CityUHK finance pages, the relevant points are:",
    "library": "From the indexed CityUHK Library pages, the relevant points are:",
    "scholarship": "From the indexed CityUHK scholarship pages, the relevant points are:",
    "admission": "From the indexed CityUHK admission pages, the relevant points are:",
    "visa": "From the indexed CityUHK visa pages, the relevant points are:",
    "registration": "From the indexed CityUHK registration pages, the relevant points are:",
    "residence": "From the indexed CityUHK student-residence pages, the relevant points are:",
    "calendar": "From the indexed CityUHK calendar pages, the relevant points are:",
}
LEAD_ZH = {
    "fees": "根据索引中的城大财务页面，与你问题相关的要点如下：",
    "library": "根据索引中的城大图书馆页面，与你问题相关的要点如下：",
    "scholarship": "根据索引中的城大奖学金页面，与你问题相关的要点如下：",
    "admission": "根据索引中的城大招生页面，与你问题相关的要点如下：",
    "visa": "根据索引中的城大签证页面，与你问题相关的要点如下：",
    "registration": "根据索引中的城大注册页面，与你问题相关的要点如下：",
    "residence": "根据索引中的城大学生宿舍页面，与你问题相关的要点如下：",
    "calendar": "根据索引中的城大校历页面，与你问题相关的要点如下：",
}


def _language(question: str) -> str:
    return "zh" if len(re.findall(r"[\u4e00-\u9fff]", question or "")) >= 2 else "en"


def _stem(word: str) -> str:
    word = word.lower()
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 3 and word.endswith("es"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


def _tokens(text: str) -> list[str]:
    out = []
    for word in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if word not in STOPWORDS and len(word) > 1:
            out.append(_stem(word))
    for run in re.findall(r"[\u4e00-\u9fff]+", text or ""):
        out.append(run)
        out.extend(run[i:i + 2] for i in range(len(run) - 1))
    return out


def _expand_query(question: str) -> list[str]:
    ql = (question or "").lower()
    terms = _tokens(ql)
    for key, values in SYNONYMS.items():
        if key in ql:
            for value in values:
                terms.extend(_tokens(value))
    for key, values in ZH_TERMS.items():
        if key in question:
            for value in values:
                terms.extend(_tokens(value))
    return list(dict.fromkeys(terms))


def _split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    # Date-list pages often concatenate events without punctuation. Split before
    # a date expression so each event remains inspectable.
    text = re.sub(
        r"\s+(?=(?:\d{1,2}\s+)?(?:january|february|march|april|may|june|july|august|september|october|november|december)\b)",
        "\n", text, flags=re.I)
    parts = re.split(r"(?<=[.!?])\s+|(?<=[。！？])\s*|\n+", text)
    return [part.strip(" -–—\t") for part in parts
            if 45 <= len(part.strip(" -–—\t")) <= 700]


@dataclass
class Hit:
    score: float
    chunk: dict[str, Any]


class EvidenceIndex:
    def __init__(self, chunks_path: Path):
        self.path = Path(chunks_path)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.meta = {k: v for k, v in payload.items() if k != "chunks"}
        self.chunks = list(payload.get("chunks") or [])
        self.index_hash_verified = None
        index_file = self.path.with_name("index.faiss")
        expected_index_sha = self.meta.get("index_sha256")
        if index_file.is_file() and expected_index_sha:
            digest = hashlib.sha256(index_file.read_bytes()).hexdigest()
            self.index_hash_verified = digest == expected_index_sha
        if not self.chunks:
            raise ValueError("Retrieval snapshot has no chunks.")
        self._clean: list[str] = []
        self._titles: list[str] = []
        self._docs: list[list[str]] = []
        self._df: collections.Counter = collections.Counter()
        self._idf: dict[str, float] = {}
        self._avgdl = 0.0
        self._build()

    def _build(self) -> None:
        line_freq = collections.Counter()
        for chunk in self.chunks:
            seen = set()
            for line in re.split(r"\n+", chunk.get("text", "")):
                line = re.sub(r"\s+", " ", line).strip().lower()
                if 8 < len(line) < 180:
                    seen.add(line)
            line_freq.update(seen)
        bad_line = re.compile(
            r"^(skip to|search|menu|home|about us|contact us|privacy|copyright|"
            r"accessibility|sitemap|login|sign in|back to top|share|print|facebook|"
            r"twitter|linkedin|youtube|instagram|we use cookies|accept all|enquire|"
            r"apply now|quick links|useful links|main menu|search form)\b", re.I)

        def clean(text: str) -> str:
            out = []
            for line in re.split(r"\n+", text or ""):
                line = re.sub(r"[ \t]+", " ", line).strip()
                if not line:
                    continue
                low = line.lower()
                if bad_line.search(low) or (len(line) < 180 and line_freq[low] >= 8):
                    continue
                if re.fullmatch(r"[\W_]+", line):
                    continue
                out.append(line)
            return " ".join(out)

        for chunk in self.chunks:
            text = clean(chunk.get("text", ""))
            title = clean(chunk.get("title", ""))
            url_terms = _tokens(str(chunk.get("url", "")).replace("/", " ").replace("-", " "))
            doc = _tokens(text)
            doc += [t for t in _tokens(title) for _ in range(3)]
            doc += [t for t in url_terms for _ in range(2)]
            self._clean.append(text)
            self._titles.append(title)
            self._docs.append(doc)
            self._df.update(set(doc))
        count = len(self._docs)
        self._avgdl = sum(len(doc) for doc in self._docs) / max(count, 1)
        self._idf = {term: math.log(1 + (count - freq + 0.5) / (freq + 0.5))
                     for term, freq in self._df.items()}

    def list_topics(self) -> list[str]:
        return sorted({str(c.get("topic", "")) for c in self.chunks if c.get("topic")})

    def _bm25(self, query_terms: list[str]) -> list[float]:
        scores = []
        for doc in self._docs:
            tf = collections.Counter(doc)
            dl = len(doc)
            score = 0.0
            for term in query_terms:
                freq = tf.get(term, 0)
                if not freq:
                    continue
                score += (self._idf.get(term, 0.0) * freq * 2.2
                          / (freq + 1.2 * (1 - 0.75 + 0.75 * dl / max(self._avgdl, 1))))
            scores.append(score)
        return scores

    def search(self, question: str, topic_keys: list[str] | None = None, k: int = 5) -> list[Hit]:
        query_terms = _expand_query(question)
        if not query_terms:
            return []
        scores = self._bm25(query_terms)
        ql = (question or "").lower()
        labels = [TOPIC_LABEL[key] for key in (topic_keys or []) if key in TOPIC_LABEL]
        if "visa" in (topic_keys or []):
            labels.append("申请")
        if any(t in ql for t in ("when", "deadline", "period", "日期", "什么时候")) and "registration" in (topic_keys or []):
            labels.append("校历与重要日期")

        def ranked(use_labels: list[str]) -> list[Hit]:
            candidates = []
            for index, base in enumerate(scores):
                chunk = self.chunks[index]
                if use_labels and chunk.get("topic") not in use_labels:
                    continue
                score = base
                url = str(chunk.get("url", "")).lower()
                title = str(chunk.get("title", "")).lower()
                if len(self._clean[index]) < 250:
                    score -= 18
                elif len(self._clean[index]) < 400:
                    score -= 6
                year_match = re.search(r"(20\d{2})", str(chunk.get("academic_year", "")))
                if year_match and int(year_match.group(1)) < 2025:
                    score -= 2
                if any(t in ql for t in ("library", "借书", "图书馆", "enter the library", "borrow")):
                    if "/start" in url or "getting started" in title:
                        score += 8
                    if "libguides" in url:
                        score += 1
                    if any(x in url for x in ("/aim", "/altmetric", "/career", "/citing", "/current", "/thes")):
                        score -= 6
                refund_query = any(t in ql for t in ("refund", "refundable", "退款", "退费"))
                if any(t in ql for t in ("tuition", "fee", "pay", "payment", "学费", "缴费", "支付", "交")) and not refund_query:
                    if "paymethods" in url or "payments" in title:
                        score += 10
                    if "payschedule" in url:
                        score += 2
                    if "refund" in url and not any(t in ql for t in ("refund", "退款", "退费")):
                        score -= 4
                if refund_query and "refund" in url and len(self._clean[index]) >= 300:
                    score += 16
                if any(t in ql for t in ("scholarship", "奖学金")):
                    if "scholarship" in url:
                        score += 6
                    if "entrance-scholarships" in url:
                        score += 5
                    if "non-local" in ql and "non-local" in url:
                        score += 10
                    if "non-local" in ql and "local-students" in url and "non-local" not in url:
                        score -= 12
                    if "sports" in url and not any(t in ql for t in ("sport", "运动", "体育")):
                        score -= 8
                    if "financial-assistance" in url and not any(
                            t in ql for t in ("financial", "助学金", "贷款", "emergency", "紧急")):
                        score -= 4
                if any(t in ql for t in ("visa", "签证")):
                    if "student-visa" in url:
                        score += 12
                    if "visa" in url:
                        score += 8
                    if "must-do-list" in url and not any(t in ql for t in ("hkid", "identity card", "身份证")):
                        score -= 3
                if any(t in ql for t in ("add/drop", "add drop", "选课")):
                    if "impd" in url:
                        score += 15
                    if "important-dates" in title or "important dates" in title:
                        score += 5
                    if "creg" in url:
                        score += 3
                if score > 0:
                    candidates.append(Hit(score, chunk))
            candidates.sort(key=lambda hit: hit.score, reverse=True)
            return candidates

        ranked_hits = ranked(labels)
        if len(ranked_hits) < max(3, k) and labels:
            ranked_hits = ranked([])
        out: list[Hit] = []
        per_doc = collections.Counter()
        seen_signature = set()
        for hit in ranked_hits:
            doc_id = str(hit.chunk.get("doc_id", ""))
            if per_doc[doc_id] >= 2:
                continue
            signature = re.sub(r"\W+", " ", self.text_for(hit.chunk)[:260].lower()).strip()
            if signature in seen_signature:
                continue
            seen_signature.add(signature)
            out.append(hit)
            per_doc[doc_id] += 1
            if len(out) >= k:
                break
        return out

    def text_for(self, chunk: dict[str, Any]) -> str:
        try:
            return self._clean[self.chunks.index(chunk)]
        except ValueError:
            return re.sub(r"\s+", " ", chunk.get("text", "")).strip()


def _topic_scores(question: str) -> dict[str, int]:
    ql = (question or "").lower()
    scores = {}
    for topic, terms in TOPIC_TERMS.items():
        total = 0
        for phrase, weight in terms:
            if phrase in ql:
                total += weight
        if total:
            scores[topic] = total
    return scores


def _refund_ambiguous(question: str) -> bool:
    ql = (question or "").lower()
    if not any(t in ql for t in ("refund", "refundable", "退款", "退费")):
        return False
    return not any(t in ql for t in REFUND_OBJECTS)


def _options(language: str, kind: str) -> list[dict[str, str]]:
    if language == "zh":
        if kind == "refund":
            return [
                {"label": "学费/学生账户退款", "query": "我退课/退学后可以申请学费退款吗？"},
                {"label": "录取留位费退款", "query": "录取时交的留位费可以退吗？"},
                {"label": "宿舍费退款", "query": "宿舍费可以退款吗？"},
                {"label": "课程退选退款", "query": "退选课程后可以退款吗？"},
            ]
        return [
            {"label": "入学申请", "query": "如何申请城大入学？"},
            {"label": "奖学金", "query": "如何申请奖学金？"},
            {"label": "学生宿舍", "query": "如何申请学生宿舍？"},
            {"label": "学生签证", "query": "如何申请学生签证？"},
        ]
    if kind == "refund":
        return [
            {"label": "Tuition / student account", "query": "Can I get a tuition refund after withdrawing from a course?"},
            {"label": "Admission deposit", "query": "Is the admission acceptance deposit refundable?"},
            {"label": "Hostel / hall fees", "query": "Can I get a refund of my hostel fees?"},
            {"label": "Course add/drop", "query": "Can I get a refund for a course I dropped?"},
        ]
    return [
        {"label": "Admission", "query": "How do I apply for admission?"},
        {"label": "Scholarship", "query": "How do I apply for a scholarship?"},
        {"label": "Student residence", "query": "How do I apply for student residence?"},
        {"label": "Student visa", "query": "How do I apply for a student visa?"},
    ]


def classify_intent(question: str, topic: str | None = None) -> dict[str, Any]:
    language = _language(question)
    scores = _topic_scores(question)
    if topic:
        topic_key = next((k for k, v in TOPIC_ALIASES.items() if v and v == topic), None)
        if topic_key is None:
            topic_key = topic if topic in TOPIC_LABEL else None
        if topic_key:
            scores[topic_key] = scores.get(topic_key, 0) + 20
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    if ordered:
        topics = [topic for topic, value in ordered if value >= 4][:2] or [ordered[0][0]]
    else:
        topics = []
    ambiguous = None
    unsupported = False
    ql = (question or "").lower()

    if any(obj in ql for obj in OUT_OF_SCOPE_OBJECTS):
        unsupported = True
        topics = []

    refund_intent = any(t in ql for t in ("refund", "refundable", "退款", "退费"))
    if refund_intent and not _refund_ambiguous(question) and not unsupported:
        if any(t in ql for t in ("hostel", "hall", "宿舍", "住宿")):
            topics = ["residence"]
        elif any(t in ql for t in ("acceptance fee", "deposit", "留位费", "押金")):
            topics = ["fees"]
        elif any(t in ql for t in ("tuition", "学费", "fee", "fees")):
            topics = ["fees"]
        elif any(t in ql for t in ("course", "add/drop", "课程", "选课")):
            topics = ["registration", "fees"]
        else:
            topics = ["fees"]

    if not unsupported and _refund_ambiguous(question):
        ambiguous = {"kind": "refund", "options": _options(language, "refund")}
    elif not unsupported and any(t in ql for t in ("apply", "application", "申请")) and not any(
            phrase in ql for phrase, weight in TOPIC_TERMS["admission"] if weight >= 4) and not any(
            any(phrase in ql for phrase, weight in TOPIC_TERMS[key] if weight >= 4)
            for key in ("library", "scholarship", "visa", "registration", "residence", "fees", "calendar")):
        ambiguous = {"kind": "generic_apply", "options": _options(language, "generic_apply")}

    if ambiguous:
        topics = []
    return {
        "language": language,
        "topics": topics,
        "scores": scores,
        "ambiguous": ambiguous,
        "unsupported": unsupported,
        "topic_label": " · ".join(TOPIC_LABEL.get(t, t) for t in topics),
    }


def _score_sentence(sentence: str, query_terms: set[str], title_terms: set[str], position: int, focus_terms: set[str] | None = None, date_focus: bool = False, amount_focus: bool = False) -> float:
    low = sentence.lower()
    terms = set(_tokens(low))
    score = len(terms & query_terms) + len(terms & title_terms) * 0.35
    if focus_terms:
        score += sum(2.4 for term in focus_terms if term in low)
    cues = ("required", "must", "need", "should", "can", "may", "apply", "submit",
            "pay", "payment", "deadline", "due", "fee", "fees", "refund", "eligible",
            "provide", "bring", "card", "eid", "borrow", "register", "document",
            "penalty", "amount", "date", "semester", "award", "scholarship")
    score += sum(0.35 for cue in cues if cue in low)
    if "cityuhk pay" in low:
        score += 1.6
    if "students are encouraged" in low:
        score += 2.2
    if "one stop" in low or "one-stop" in low:
        score += 1.5
    if "payment methods" in low or "settle your student account" in low:
        score += 1.0
    if "required at all time" in low or "required at all times" in low:
        score += 1.5
    if "do not have to submit" in low or "no need to submit" in low:
        score += 1.2
    has_date = bool(DATE_RE.search(sentence))
    if has_date:
        score += 1.8
        if date_focus:
            score += 5.0
    elif date_focus:
        score -= 4.0
    if amount_focus and re.search(r"(HK\$|HKD|\$\s?\d|per year|per semester)", sentence, re.I):
        score += 3.0
    if amount_focus and "penalty" in low:
        score -= 2.5
    if re.search(r"(HK\$|HKD|\$\s?\d|per year|per semester|per month)", sentence, re.I):
        score += 1.4
    if "opening hours" in low:
        score += 1.5
    if position < 500:
        score += 0.5
    if len(sentence) > 520:
        score -= 0.7
    if re.search(r"\b(skip to|click here|privacy|copyright|accept all)\b", low):
        score -= 3
    return score


def _extractive_answer(index: EvidenceIndex, question: str, topic_keys: list[str],
                       hits: list[Hit], language: str) -> dict[str, Any]:
    query_terms = set(_expand_query(question))
    ql = question.lower()
    focus_terms = set()
    if any(t in ql for t in ("refund", "退款", "退费")):
        focus_terms.add("refund")
    if any(t in ql for t in ("scholarship", "奖学金")):
        focus_terms.update(("scholarship", "entrance"))
    if any(t in ql for t in ("visa", "签证")):
        focus_terms.update(("visa", "entry permit"))
    if any(t in ql for t in ("add/drop", "add drop", "选课")):
        focus_terms.update(("add/drop", "add drop"))
    if "non-local" in ql:
        focus_terms.add("non-local")
    if any(t in ql for t in ("hostel", "hall", "宿舍", "住宿")):
        focus_terms.update(("hostel", "hall", "lodging", "room"))
    if any(t in ql for t in ("when", "什么时候", "deadline", "period", "截止日期", "日期")):
        focus_terms.update(("2026", "2027", "semester a", "semester b", "week"))
    date_focus = any(t in ql for t in ("when", "什么时候", "deadline", "period", "截止日期", "日期"))
    amount_focus = any(t in ql for t in ("how much", "多少钱", "费用多少", "fee amount"))
    candidates = []
    for rank, hit in enumerate(hits, 1):
        chunk = hit.chunk
        text = index.text_for(chunk)
        title_terms = set(_tokens(chunk.get("title", "")))
        for position, sentence in enumerate(_split_sentences(text)):
            score = _score_sentence(sentence, query_terms, title_terms, position * 90, focus_terms, date_focus, amount_focus)
            candidates.append((score, rank, chunk, text, sentence))
    primary_focus = focus_terms & {"refund", "scholarship", "visa", "entry permit", "add/drop", "add drop"}
    if date_focus:
        dated = [item for item in candidates if DATE_RE.search(item[4])]
        if primary_focus:
            both = [item for item in dated if any(term in item[4].lower() for term in primary_focus)]
            candidates = both or dated
        else:
            candidates = dated
    candidates.sort(key=lambda item: item[0], reverse=True)
    selected: list[tuple[str, dict[str, Any], str]] = []
    citations: list[dict[str, Any]] = []
    used_ranks = set()
    for score, rank, chunk, text, sentence in candidates:
        if score <= 0.5 or rank in used_ranks:
            continue
        if date_focus:
            if not DATE_RE.search(sentence):
                continue
        elif primary_focus and not any(term in sentence.lower() for term in primary_focus):
            continue
        normalized = re.sub(r"\W+", " ", sentence[:120].lower()).strip()
        if any(normalized == re.sub(r"\W+", " ", item[2][:120].lower()).strip() for item in selected):
            continue
        selected.append((f"S{rank}", chunk, sentence))
        used_ranks.add(rank)
        citations.append({
            "source_id": f"S{rank}", "chunk_id": chunk.get("chunk_id", ""),
            "doc_id": chunk.get("doc_id", ""), "url": chunk.get("url", ""),
            "title": chunk.get("title", ""), "topic": chunk.get("topic", ""),
            "excerpt": _excerpt_around(text, sentence),
        })
        if len(selected) >= 4:
            break

    if not selected and hits:
        for rank, hit in enumerate(hits[:2], 1):
            chunk = hit.chunk
            text = index.text_for(chunk)
            if text.strip():
                selected.append((f"S{rank}", chunk, text[:360].strip()))
                citations.append({
                    "source_id": f"S{rank}", "chunk_id": chunk.get("chunk_id", ""),
                    "doc_id": chunk.get("doc_id", ""), "url": chunk.get("url", ""),
                    "title": chunk.get("title", ""), "topic": chunk.get("topic", ""),
                    "excerpt": _excerpt_around(text, text[:360]),
                })

    if not selected:
        message = ("索引中没有找到足以回答该问题的片段。请换一种问法，或指定主题后重试。"
                   if language == "zh" else
                   "No indexed passage was strong enough to answer this question. Try a more specific wording or select a topic.")
        return {"status": "abstained", "answer": message, "points": [], "citations": [], "message": message}

    joined = " ".join(sentence for _, _, sentence in selected)
    ql = question.lower()
    gate_failed = None
    clock_query = any(t in ql for t in ("what time", "几点", "开放时间", "opening hours", "开门", "关门"))
    date_query = any(t in ql for t in ("when", "什么时候", "deadline", "period", "截止日期", "日期"))
    if clock_query:
        hours_match = re.search(r"opening hours[^.]{0,140}", joined, re.I)
        if not hours_match or not re.search(r"\d{1,2}(?::\d{2})?\s*(?:am|pm)|monday|tuesday|wednesday|thursday|friday|saturday|sunday", hours_match.group(0), re.I):
            gate_failed = "clock_time"
    elif date_query:
        if not DATE_RE.search(joined):
            gate_failed = "date_time"
    if any(t in ql for t in ("how much", "多少钱", "费用多少", "fee amount")) and not gate_failed:
        if not re.search(r"(HK\$|HKD|\$\s?\d|per year|per semester|fee)", joined, re.I):
            gate_failed = "amount"
    if any(t in ql for t in ("refund", "退款", "退费")) and not gate_failed:
        if "refund" not in joined.lower():
            gate_failed = "refund"
    if any(t in ql for t in ("visa", "签证")) and not gate_failed:
        if not re.search(r"visa|entry permit", joined, re.I):
            gate_failed = "visa"
    if any(t in ql for t in ("scholarship", "奖学金")) and not gate_failed:
        if "scholarship" not in joined.lower():
            gate_failed = "scholarship"
    if any(t in ql for t in ("hostel", "hall", "宿舍", "住宿")) and not gate_failed:
        if not re.search(r"hostel|hall|residence|room|宿舍", joined, re.I):
            gate_failed = "residence"
    if gate_failed:
        message = ("离线摘录没有找到直接回答该问题类型的句子。为避免误答，未发布要点；请配置模型或打开来源核对。"
                   if language == "zh" else
                   "The offline extractor did not find a sentence that directly answers this question type. To avoid a misleading answer, no points were published; configure the model or inspect the sources.")
        return {"status": "abstained", "answer": message, "points": [], "citations": citations, "message": message}

    if date_focus:
        selected.sort(key=lambda item: 0 if DATE_RE.search(item[2]) else 1)
    if amount_focus:
        amount_pattern = re.compile(r"(HK\$|HKD|\$\s?\d|per year|per semester)", re.I)
        selected.sort(key=lambda item: 0 if amount_pattern.search(item[2]) and "penalty" not in item[2].lower() else 1)
    topic = topic_keys[0] if topic_keys else ""
    lead = LEAD_ZH.get(topic, "根据索引中的城大官方页面，与你问题相关的要点如下：") if language == "zh" else LEAD_EN.get(topic, "From the indexed CityUHK pages, the relevant points are:")
    points, lines = [], [lead]
    for source_id, chunk, sentence in selected:
        points.append({"text": sentence, "source_ids": [source_id]})
        lines.append(f"- {sentence} [{source_id}]")
    if language == "zh":
        lines.append("说明：以上为离线摘录模式，句子直接取自索引页面，未做模型改写；请以链接页面为准。")
    else:
        lines.append("Note: this is offline extractive mode; the points are quoted from the indexed pages, not model paraphrase. Check the linked page for the full context.")
    return {"status": "answered", "answer": "\n\n".join(lines), "points": points, "citations": citations, "message": ""}


def _llm_config() -> dict[str, Any]:
    return {
        "enabled": os.environ.get("DSC5003_DISABLE_LLM", "").strip() not in ("1", "true", "yes"),
        "api_key": os.environ.get("DEEPSEEK_API_KEY", "").strip(),
        "base_url": os.environ.get("DSC5003_LLM_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        "model": os.environ.get("DSC5003_LLM_MODEL", "deepseek-flash").strip() or "deepseek-flash",
        "timeout": float(os.environ.get("DSC5003_LLM_TIMEOUT", "60")),
    }


def _call_llm(messages: list[dict[str, str]], max_tokens: int, config: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    body = {"model": config["model"], "messages": messages, "max_tokens": max_tokens,
            "temperature": 0.1, "thinking": {"type": "disabled"}}
    request = urllib.request.Request(
        config["base_url"] + "/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + config["api_key"]})
    with urllib.request.urlopen(request, timeout=config["timeout"]) as response:
        payload = json.load(response)
    return payload["choices"][0]["message"].get("content") or "", payload.get("usage") or {}


def _parse_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    fence = chr(96) * 3
    if text.startswith(fence):
        text = re.sub(r"^" + fence + r"[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*" + fence + r"$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def _validate_candidate(value: dict[str, Any], evidence_ids: set[str], language: str, fallback_kind: str = 'generic_apply') -> dict[str, Any]:
    status = value.get("status")
    if status not in ("answered", "clarify", "abstained", "out_of_scope"):
        raise ValueError("Unknown status")
    summary = value.get("summary") if isinstance(value.get("summary"), str) else ""
    message = value.get("message") if isinstance(value.get("message"), str) else ""
    points = value.get("points") if isinstance(value.get("points"), list) else []
    options = value.get("clarify_options") if isinstance(value.get("clarify_options"), list) else []
    scope_note = value.get("scope_note") if isinstance(value.get("scope_note"), str) else ""
    if len(summary) > 2000 or len(message) > 1200 or len(scope_note) > 600:
        raise ValueError("Field too long")
    if re.search(r"https?://|www\.", summary, re.I):
        raise ValueError("Summary contains a generated URL")
    if re.search(r"https?://|www\.", message, re.I):
        raise ValueError("Message contains a generated URL")
    unknown = set(re.findall(r"S\d+", summary)) - evidence_ids
    if unknown:
        raise ValueError("Summary cites unknown evidence")
    if status == "answered":
        if not summary.strip() or not points:
            raise ValueError("Answered without summary or points")
        message = ""
    else:
        points = []
        if not message.strip():
            raise ValueError("Non-answer without message")
    clean_points = []
    for point in points[:6]:
        if not isinstance(point, dict):
            raise ValueError("Invalid point")
        text, ids = point.get("text"), point.get("source_ids")
        if not isinstance(text, str) or not text.strip() or len(text) > 1200:
            raise ValueError("Invalid point text")
        if re.search(r"https?://|www\.", text, re.I):
            raise ValueError("Point contains a generated URL")
        if re.search(r"\[S\d+\]", text):
            raise ValueError("Point contains a citation marker; citations are server-mapped")
        if not isinstance(ids, list) or not ids or len(ids) > 4:
            raise ValueError("Point has no citation")
        clean_ids = []
        for source_id in ids:
            if not isinstance(source_id, str) or source_id not in evidence_ids:
                raise ValueError("Point cites unknown evidence")
            if source_id not in clean_ids:
                clean_ids.append(source_id)
        clean_points.append({"text": text.strip(), "source_ids": clean_ids})
    clean_options = []
    for option in options[:4]:
        if not isinstance(option, dict):
            continue
        label, query = option.get("label"), option.get("query")
        if isinstance(label, str) and isinstance(query, str) and label.strip() and query.strip():
            clean_options.append({"label": label.strip()[:80], "query": query.strip()[:500]})
    if status == "clarify" and not clean_options:
        clean_options = _options(language, fallback_kind)
    return {"status": status, "summary": summary.strip(), "points": clean_points,
            "message": message.strip(), "clarify_options": clean_options,
            "scope_note": scope_note.strip()}


def _compose_answer(candidate: dict[str, Any], language: str) -> str:
    if candidate["status"] != "answered":
        return candidate["message"] or candidate["summary"]
    summary = re.sub(r"\((S\d+(?:,\s*S\d+)*)\)",
                     lambda m: "".join(f"[{x.strip()}]" for x in m.group(1).split(",")),
                     candidate["summary"])
    lines = [summary]
    for point in candidate["points"]:
        refs = "".join(f"[{source_id}]" for source_id in point["source_ids"])
        lines.append(f"- {point['text']} {refs}")
    lines.append("说明：以上回答只依据索引中的校方页面；引用编号可在下方来源抽屉核对。"
                 if language == "zh" else
                 "Note: this answer is limited to the indexed CityUHK pages; open the citation drawer to verify each source.")
    return "\n\n".join(lines)


def _excerpt_around(text: str, sentence: str, radius: int = 220) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    sentence = re.sub(r"\s+", " ", sentence or "").strip()
    if not sentence:
        return text[:420]
    needle = sentence[:100].lower()
    position = text.lower().find(needle)
    if position < 0:
        return text[:420]
    start = max(0, position - radius)
    end = min(len(text), position + len(sentence) + radius)
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


def _citations_for(index: EvidenceIndex, hits: list[Hit], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {}
    chunk_by_source = {}
    support: dict[str, str] = {}
    for rank, hit in enumerate(hits, 1):
        chunk = hit.chunk
        chunk_by_source[f"S{rank}"] = chunk
        by_id[f"S{rank}"] = {
            "source_id": f"S{rank}", "chunk_id": chunk.get("chunk_id", ""),
            "doc_id": chunk.get("doc_id", ""), "url": chunk.get("url", ""),
            "title": chunk.get("title", ""), "topic": chunk.get("topic", ""),
            "excerpt": index.text_for(chunk)[:420],
        }
    for point in candidate.get("points") or []:
        for source_id in point.get("source_ids") or []:
            support.setdefault(source_id, point.get("text", ""))
    used = []
    text = ((candidate.get("summary") or "") + " " + (candidate.get("message") or "") + " "
            + " ".join(" ".join(point.get("source_ids") or []) for point in candidate.get("points") or []))
    for source_id in re.findall(r"S\d+", text):
        if source_id not in used:
            used.append(source_id)
    for point in candidate.get("points") or []:
        for source_id in point.get("source_ids") or []:
            if source_id not in used:
                used.append(source_id)
    out = []
    for source_id in used:
        if source_id not in by_id:
            continue
        citation = dict(by_id[source_id])
        if support.get(source_id) and source_id in chunk_by_source:
            raw = index.text_for(chunk_by_source[source_id])
            citation["excerpt"] = _excerpt_around(raw, support[source_id])
        out.append(citation)
    return out


def _retrieval_round(question: str, topic_keys: list[str], hits: list[Hit], index: EvidenceIndex) -> dict[str, Any]:
    return {"round": 1, "query": question,
            "topic": TOPIC_LABEL.get(topic_keys[0], "") if topic_keys else "",
            "hits": [{"chunk_id": hit.chunk.get("chunk_id", ""),
                      "doc_id": hit.chunk.get("doc_id", ""),
                      "url": hit.chunk.get("url", ""),
                      "title": hit.chunk.get("title", ""),
                      "topic": hit.chunk.get("topic", ""),
                      "academic_year": hit.chunk.get("academic_year", ""),
                      "score": round(hit.score, 4),
                      "text": index.text_for(hit.chunk)[:500]} for hit in hits]}


def ask(index: EvidenceIndex, question: str, topic: str | None = None,
        use_llm: bool | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    question = (question or "").strip()
    classification = classify_intent(question, topic)
    language = classification["language"]
    topic_keys = classification["topics"]
    warnings = []
    result: dict[str, Any] = {
        "status": "error", "answer": "", "mode": "offline-extractive", "question": question,
        "language": language, "topics": topic_keys, "topic_label": classification["topic_label"],
        "citations": [], "retrieval_rounds": [], "tool_calls": [], "llm_calls": 0,
        "usage": None, "latency_ms": 0, "warnings": warnings,
        "scope_note": SCOPE_ZH if language == "zh" else SCOPE_EN,
        "clarify_options": [], "review": None, "error": None,
        "versions": {"corpus_sha256": index.meta.get("corpus_sha256"),
                     "index_sha256": index.meta.get("index_sha256"),
                     "embedding_model": index.meta.get("model"),
                     "chunks": len(index.chunks), "index_hash_verified": index.index_hash_verified,
                     "git_commit": (index.path.parents[2].name.rsplit("_", 1)[-1]
                                    if len(index.path.parents) >= 3 else None)},
    }

    def finish(status: str, answer: str = "", message: str = "", error: str | None = None) -> dict[str, Any]:
        result["status"], result["answer"], result["message"] = status, answer, message
        if error:
            result["error"] = {"code": status, "message": error}
        result["latency_ms"] = round((time.perf_counter() - started) * 1000)
        return result

    if not question or len(question) > 2000:
        return finish("invalid_input", message="请输入1–2000字符的问题。" if language == "zh" else "Enter a question between 1 and 2,000 characters.",
                      error="Question must be 1–2000 characters.")

    if classification.get("unsupported"):
        message = ("这个问题涉及的对象不在城大学生服务索引范围内（例如求职、信用卡、银行账户、护照等）。请改问8个已覆盖主题之一。"
                   if language == "zh" else
                   "That object is outside the CityUHK student-services index (for example jobs, credit cards, bank accounts or passports). Ask within the eight covered topics instead.")
        result["mode"] = "out_of_scope"
        return finish("out_of_scope", message, message)

    if classification["ambiguous"]:
        ambiguous = classification["ambiguous"]
        if ambiguous["kind"] == "refund":
            message = ("这个问题需要先明确对象。请选择一种退款类型，我会按对应页面回答。"
                       if language == "zh" else
                       "Which refund do you mean? Choose one option and I will answer from the matching pages.")
        else:
            message = ("这个问题缺少主题。请选择要申请的事项，我会按对应主题检索。"
                       if language == "zh" else
                       "This question needs a topic. Choose one option and I will retrieve the matching pages.")
        result["clarify_options"] = ambiguous["options"]
        result["mode"] = "clarify"
        return finish("clarify", message, message)

    if not topic_keys:
        message = ("这个问题不在当前索引范围内。本演示只覆盖8个城大学生服务主题：申请、签证、注册、宿舍、学费、奖学金、图书馆、校历。请选择相关主题后重试。"
                   if language == "zh" else
                   "This question is outside the indexed scope. The demo covers eight CityUHK student-service topics: admission, visa, registration, residence, fees, scholarships, library and calendar. Choose a topic or rephrase within that scope.")
        result["clarify_options"] = _options(language, "generic_apply")
        result["mode"] = "out_of_scope"
        return finish("out_of_scope", message, message)

    hits = index.search(question, topic_keys, k=5)
    if not hits:
        message = ("没有检索到可用片段。请换一种问法，或选择更具体的主题。"
                   if language == "zh" else
                   "No indexed passage was retrieved. Try a more specific question or choose a topic.")
        return finish("no_evidence", message, message)

    result["retrieval_rounds"] = [_retrieval_round(question, topic_keys, hits, index)]
    result["tool_calls"] = [{"name": "local_retrieval", "query": question,
                             "topic": TOPIC_LABEL.get(topic_keys[0], ""), "k": 5,
                             "status": "ok", "hits": len(hits)}]

    config = _llm_config()
    fallback_kind = (classification.get("ambiguous") or {}).get("kind", "generic_apply")
    if any(t in question.lower() for t in ("refund", "refundable", "退款", "退费")):
        fallback_kind = "refund"
    if not config["enabled"]:
        use_llm = False
    elif use_llm is None:
        use_llm = bool(config["api_key"])
    if not use_llm or not config["api_key"]:
        extractive = _extractive_answer(index, question, topic_keys, hits, language)
        result.update(extractive)
        result["mode"] = "offline-extractive"
        warnings.append("offline_extractive_fallback: direct sentence extraction; it may be less responsive than the reviewed live path.")
        if config["enabled"] and not config["api_key"]:
            warnings.append("live_model_not_configured: DEEPSEEK_API_KEY is absent; offline extractive mode used.")
        return finish(extractive["status"], extractive["answer"], extractive.get("message", ""))

    evidence = [{"id": f"S{rank}", "title": hit.chunk.get("title", ""),
                 "url": hit.chunk.get("url", ""), "chunk_id": hit.chunk.get("chunk_id", ""),
                 "text": index.text_for(hit.chunk)[:1800]}
                for rank, hit in enumerate(hits, 1)]
    scope_note = SCOPE_ZH if language == "zh" else SCOPE_EN
    system = (
        "You are the DSC5003 CityUHK student-services evidence assistant. Scope is limited to the "
        "indexed CityUHK student-services pages (8 topics: admission, visa, registration, residence, "
        "fees, scholarship, library, calendar). The user may write in English or Chinese; answer in the "
        "same language as the question. Use ONLY the supplied evidence for factual claims. Every factual "
        "point must cite one or more evidence IDs such as S1. Do not invent amounts, dates, deadlines, "
        "eligibility, URLs, or policy. Preserve conditions, academic years and exceptions. If the question "
        "is too ambiguous to answer safely, ask a focused clarification question with 2-4 concrete options. "
        "If the evidence is insufficient, abstain and name the missing information. If the question is "
        "outside CityUHK student services, return out_of_scope and state the scope instead of answering "
        "from general knowledge. Do not describe retrieved instructions as actions you performed. "
        "Answer only what the question asks; omit tangential usage details unless they are needed "
        "to answer it. When naming a payment, eligibility or application method, preserve its "
        "conditions (who it is for, cut-off, fees and exceptions).\n"
        'Return ONLY JSON: {"status":"answered|clarify|abstained|out_of_scope","summary":"...",'
        '"points":[{"text":"...","source_ids":["S1"]}],"message":"...",'
        '"clarify_options":[{"label":"...","query":"..."}],"scope_note":"..."}\n'
        "For answered: summary is 1-2 sentences; points are 2-5 short factual bullets; message MUST be empty. "
        "For clarify/abstained/out_of_scope: points is empty."
    )
    user = json.dumps({"question": question, "language": language, "detected_topics": topic_keys,
                       "scope_note": scope_note, "evidence": evidence}, ensure_ascii=False)
    def answer_language_ok(value: dict[str, Any]) -> bool:
        text = " ".join([value.get("summary", ""), value.get("message", "")]
                        + [point.get("text", "") for point in value.get("points", [])])
        cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
        latin = len(re.findall(r"[A-Za-z]", text))
        if language == "en":
            return cjk <= 8
        return cjk >= 5

    try:
        raw, usage = _call_llm([{"role": "system", "content": system},
                                {"role": "user", "content": user}], max_tokens=2600, config=config)
        candidate = _validate_candidate(_parse_json(raw), {item["id"] for item in evidence}, language, fallback_kind)
        result["llm_calls"], result["usage"] = 1, usage
        if not answer_language_ok(candidate):
            retry_system = system + f"\nLanguage requirement: the JSON values MUST be written in {'Chinese' if language == 'zh' else 'English'}."
            raw, retry_usage = _call_llm([{"role": "system", "content": retry_system},
                                          {"role": "user", "content": user}], max_tokens=2600, config=config)
            candidate = _validate_candidate(_parse_json(raw), {item["id"] for item in evidence}, language, fallback_kind)
            result["llm_calls"] = int(result.get("llm_calls") or 1) + 1
            result["usage"] = {
                "prompt_tokens": (usage or {}).get("prompt_tokens", 0) + (retry_usage or {}).get("prompt_tokens", 0),
                "completion_tokens": (usage or {}).get("completion_tokens", 0) + (retry_usage or {}).get("completion_tokens", 0),
                "total_tokens": (usage or {}).get("total_tokens", 0) + (retry_usage or {}).get("total_tokens", 0),
            }
            usage = result["usage"]
            if not answer_language_ok(candidate):
                warnings.append("language_mismatch: model did not answer in the question language; offline extractive mode used.")
                extractive = _extractive_answer(index, question, topic_keys, hits, language)
                result.update(extractive)
                result["mode"] = "offline-extractive"
                return finish(extractive["status"], extractive["answer"], extractive.get("message", ""))
    except Exception as exc:
        warnings.append(f"live_model_failed: {type(exc).__name__}; offline extractive mode used.")
        extractive = _extractive_answer(index, question, topic_keys, hits, language)
        result.update(extractive)
        result["mode"] = "offline-extractive"
        return finish(extractive["status"], extractive["answer"], extractive.get("message", ""))

    review = None
    if candidate["status"] == "answered":
        review_system = (
            "You are an independent evidence reviewer for a CityUHK student-services RAG demo. "
            "You do not answer from general knowledge. Check the candidate answer ONLY against the "
            "supplied evidence. For every summary sentence and bullet, verify that the cited evidence "
            "actually supports it, including numbers, dates, deadlines, eligibility, conditions and "
            "exceptions. Also check that all parts of the user question are addressed. If a statement is "
            "unsupported, too strong, or missing a material condition, revise it or remove it. "
            "Write the issues in the same language as the question. Ignore scope_note: it is a fixed "
            "UI scope banner, not a factual claim to verify. "
            'Return ONLY JSON: {"verdict":"pass|revise|reject","issues":["short issue"],'
            '"revised":{"status":"answered|clarify|abstained|out_of_scope","summary":"...",'
            '"points":[{"text":"...","source_ids":["S1"]}],"message":"...",'
            '"clarify_options":[],"scope_note":"..."}}\n'
            "Use pass only if no material issue remains. Use revise with a corrected full candidate. "
            "Use reject if the answer cannot be supported from the evidence."
        )
        review_user = json.dumps({"question": question, "evidence": evidence, "candidate": candidate}, ensure_ascii=False)
        try:
            raw_review, review_usage = _call_llm(
                [{"role": "system", "content": review_system},
                 {"role": "user", "content": review_user}], max_tokens=2200, config=config)
            result["llm_calls"] = int(result.get("llm_calls") or 1) + 1
            result["usage"] = {
                "prompt_tokens": (usage or {}).get("prompt_tokens", 0) + (review_usage or {}).get("prompt_tokens", 0),
                "completion_tokens": (usage or {}).get("completion_tokens", 0) + (review_usage or {}).get("completion_tokens", 0),
                "total_tokens": (usage or {}).get("total_tokens", 0) + (review_usage or {}).get("total_tokens", 0),
            }
            reviewed = _parse_json(raw_review)
            verdict = reviewed.get("verdict")
            issues = reviewed.get("issues") if isinstance(reviewed.get("issues"), list) else []
            issues = [str(issue)[:300] for issue in issues[:6]]

            def issues_language_ok(items: list[str]) -> bool:
                text = " ".join(items)
                cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
                return cjk <= 8 if language == "en" else (cjk >= 3 or not text.strip())

            if issues and not issues_language_ok(issues):
                lang_name = "English" if language == "en" else "Chinese"
                retry_review_system = review_system + f"\nWrite the issues in {lang_name}."
                raw_review, retry_review_usage = _call_llm(
                    [{"role": "system", "content": retry_review_system},
                     {"role": "user", "content": review_user}], max_tokens=2200, config=config)
                reviewed = _parse_json(raw_review)
                verdict = reviewed.get("verdict")
                retry_issues = reviewed.get("issues") if isinstance(reviewed.get("issues"), list) else []
                retry_issues = [str(issue)[:300] for issue in retry_issues[:6]]
                if issues_language_ok(retry_issues):
                    issues = retry_issues
                else:
                    warnings.append("review_language_mismatch: reviewer issues were not in the question language; issues hidden.")
                    issues = []
                result["llm_calls"] = int(result.get("llm_calls") or 1) + 1
            if verdict not in ("pass", "revise", "reject"):
                review = {"verdict": "invalid", "issues": issues or ["Reviewer returned an unknown verdict."],
                          "used_revision": False}
                result["citations"] = _citations_for(index, hits, candidate)
                result["review"], result["mode"] = review, "live-llm-reviewed"
                message = ("独立复核没有返回合法结论，因此不发布答案。请重试或查看来源。"
                           if language == "zh" else
                           "The independent review did not return a valid verdict, so no answer was published. Retry or inspect the sources.")
                return finish("abstained", message, message)
            review = {"verdict": verdict, "issues": issues, "used_revision": False}
            if review["verdict"] == "reject":
                revised = reviewed.get("revised") if isinstance(reviewed.get("revised"), dict) else {}
                message = revised.get("message") or ("独立复核认为现有证据不足以支持可靠回答。请换一种问法或查看来源。"
                                                     if language == "zh" else
                                                     "The independent review found the evidence insufficient for a reliable answer. Rephrase the question or inspect the sources.")
                result["citations"] = _citations_for(index, hits, candidate)
                result["review"], result["mode"] = review, "live-llm-reviewed"
                return finish("abstained", message, message)
            if review["verdict"] == "revise" and isinstance(reviewed.get("revised"), dict):
                try:
                    revised_candidate = _validate_candidate(reviewed["revised"], {item["id"] for item in evidence}, language, fallback_kind)
                    if not answer_language_ok(revised_candidate):
                        raise ValueError("revised answer language does not match the question")
                    candidate = revised_candidate
                    review["used_revision"] = True
                except ValueError as exc:
                    issues.append(f"Revised candidate failed local validation: {exc}")
                    result["citations"] = _citations_for(index, hits, candidate)
                    result["review"] = {"verdict": "reject", "issues": issues, "used_revision": False}
                    message = ("复核要求修订，但修订稿未通过本地引用校验，因此不发布答案。"
                               if language == "zh" else
                               "The reviewer requested a revision, but the revised answer failed local citation validation; no answer was published.")
                    return finish("abstained", message, message)
            result["review"] = review
        except Exception as exc:
            warnings.append(f"independent_review_failed: {type(exc).__name__}; answer published without second-pass review.")
            result["review"] = {"verdict": "unavailable", "issues": [], "used_revision": False}

    result["citations"] = _citations_for(index, hits, candidate)
    result["clarify_options"] = candidate.get("clarify_options") or []
    result["scope_note"] = scope_note
    result["mode"] = "live-llm-reviewed" if result["llm_calls"] >= 2 else "live-llm"
    result["answer"] = _compose_answer(candidate, language)
    result["message"] = candidate.get("message", "")
    result["answer_points"] = candidate.get("points", [])
    return finish(candidate["status"], result["answer"], result["message"])


def health(index: EvidenceIndex | None) -> dict[str, Any]:
    config = _llm_config()
    return {"status": "ok" if index is not None else "index_missing",
            "index_ready": index is not None,
            "chunks": len(index.chunks) if index else 0,
            "topics": index.list_topics() if index else [],
            "llm_configured": bool(config["api_key"]),
            "llm_enabled": config["enabled"],
            "llm_model": config["model"],
            "default_mode": "live-llm-reviewed" if config["enabled"] and config["api_key"] else "offline-extractive",
            "index_hash_verified": index.index_hash_verified if index else None}
