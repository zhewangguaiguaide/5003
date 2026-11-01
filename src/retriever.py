import json
import re
from pathlib import Path
from dataclasses import dataclass


@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    text: str
    score: float
    url: str
    title: str
    topic: str
    academic_year: str

@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    text: str
    url: str
    title: str
    topic: str
    academic_year: str

def load_corpus(path: str | Path) -> list[dict]:
    path = Path(path)

    records = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    return records

def split_faq_text(content: str) -> list[str]:
    pattern = r"(?m)^(?:\d+\.[ \t]+[^\n]*\?|(?:Can|Could|How|What|When|Where|Why|Who|Which|Do|Does|Did|Is|Are|Will|Would|Should|May)\b[^\n]{0,250}\?)[ \t]*$"

    starts = [m.start() for m in re.finditer(pattern, content)]

    if not starts:
        return [content.strip()] if content.strip() else []

    starts.append(len(content))

    chunks = []
    for i in range(len(starts) - 1):
        text = content[starts[i]:starts[i + 1]].strip()
        chunks.append(text)

    return chunks


def chunk_records(records: list[dict]) -> list[Chunk]:
    chunks = []

    for record in records:
        title = record.get("title", "")
        url = record.get("url", "")
        content = record.get("content", "")

        if not url or not content.strip():
            continue

        # 跳过没有有效正文的 Student Stories 网页
        if url.rstrip("/") == "https://www.cityu.edu.hk/en/geo/international-campus/student-stories":
            continue

        # 清理交换院校网页中的筛选菜单
        if url.rstrip("/") == "https://www.cityu.edu.hk/en/geo/global-opportunities/student-exchange/student-exchange-partners":
            start = content.find("Filter by Continent")
            end = content.find("Reset Filter", start)

            if start != -1 and end != -1:
                content = content[:start] + "\n" + content[end + len("Reset Filter"):]

        # 跳过没有实际活动内容的 Upcoming Events 页面
        if title == "Upcoming Events | CityUHK Admission":
            continue
        
        # 清理 News 和 Upcoming Events 网页的筛选菜单
        if title in ("News | CityUHK Admission", "Upcoming Events | CityUHK Admission"):
            start = content.find("Department - Any -")
            end = content.find("Start Date", start)

            if start != -1 and end > start:
                content = content[:start] + "\n" + content[end:]

        # 清理本科生和研究生学费页面的导航栏及页脚
        if url.rstrip("/") in (
            "https://www.cityu.edu.hk/fo/htm/degree_fees.htm",
            "https://www.cityu.edu.hk/fo/htm/TPg_Fees.htm",
        ):
            content = clean_general_text(
                content,
                start_marker="Fees and Charges\n1.\nTuition Fees",
                end_marker="\nAbout Us\nOrganisation Structure\n",
            ).replace("\ufeff", "").strip()

        # 清理本科生和研究生缴费时间表的导航栏及页脚
        if url.rstrip("/") in (
            "https://www.cityu.edu.hk/fo/htm/Degree_PaySchedule.htm",
            "https://www.cityu.edu.hk/fo/htm/TPg_PaySchedule.htm",
        ):
            content = clean_general_text(
                content,
                start_marker="Payment Schedule\nYou can retrieve your e-statement of account",
                end_marker="\nAbout Us\nOrganisation Structure\n",
            ).replace("\ufeff", "").strip()

        # 根据网页类型选择切块方法
        if "faq" in title.lower():
            faq_texts = split_faq_text(content)
            texts = []

            for faq_text in faq_texts:
                # 短 FAQ 保持原样
                if len(faq_text) <= 1500:
                    texts.append(faq_text)
                    continue

                # 提取问题和答案
                question, sep, answer = faq_text.partition("\n")

                if not sep:
                    texts.append(faq_text)
                    continue

                # 拆分长答案，并为问题预留空间
                parts = split_general_text(
                    answer,
                    max_chars=1500 - len(question) - 1,
                    overlap=0
                )

                # 每个子 Chunk 都保留原问题
                for part in parts:
                    texts.append(question + "\n" + part)

        else:
            # 普通网页切块
            texts = split_general_text(content)

        # 生成 Chunk，保留元数据
        for i, text in enumerate(texts):

            # 删除视频URL，保留视频标题
            text = "\n".join(
                line for line in text.splitlines()
                if "youtu.be/" not in line
                and "bilibili.com/video/" not in line
            ).strip()

            # 跳过清洗后为空的 Chunk
            if not text:
                continue

            chunk = Chunk(
                chunk_id=f"{url}#chunk-{i}",
                doc_id=url,
                text=text,
                url=url,
                title=title,
                topic=record.get("topic", ""),
                academic_year=record.get("academic_year", "")
            )

            chunks.append(chunk)

    return chunks


def split_general_text(
    content: str,
    max_chars: int = 1500,
    overlap: int = 200
) -> list[str]:

    lines = [
        line.strip()
        for line in content.splitlines()
        if line.strip()
    ]

    chunks = []
    current = []

    for line in lines:
        if current and len("\n".join(current + [line])) > max_chars:
            chunks.append("\n".join(current))

            # 保留上一块末尾的部分内容
            overlap_lines = []
            total = 0

            for old_line in reversed(current):
                if total + len(old_line) + 1 > overlap:
                    break
                overlap_lines.insert(0, old_line)
                total += len(old_line) + 1

            current = overlap_lines

        current.append(line)

    if current:
        chunks.append("\n".join(current))

    return chunks

def clean_general_text(
    content: str,
    start_marker: str | None = None,
    end_marker: str | None = None
) -> str:

    text = content.strip()

    # 删除正文开始位置之前的导航
    if start_marker and start_marker in text:
        pos = text.find(start_marker)
        text = text[pos:]

    # 删除正文结束位置之后的导航
    if end_marker and end_marker in text:
        pos = text.rfind(end_marker)
        text = text[:pos]

    return text.strip()


    
class Retriever:
    def __init__(self, index_dir: str = "data/wsb_index"):
        import json
        from pathlib import Path
        import faiss

        index_dir = Path(index_dir)

        # 1. 加载 FAISS 向量索引
        self.index = faiss.read_index(
            str(index_dir / "index.faiss")
        )

        # 2. 加载 Chunk 元数据
        with open(
            index_dir / "chunks.json",
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        self.chunks = data["chunks"]

        # 3. 检查索引与 Chunk 数量是否一致
        if self.index.ntotal != len(self.chunks):
            raise ValueError(
                "FAISS 索引数量与 Chunk 数量不一致"
            )

        # 4. 提取全部主题
        self.topics = sorted({
            chunk["topic"]
            for chunk in self.chunks
            if chunk.get("topic")
        })

        # 5. 记录 Embedding 模型名称
        self.model_name = "intfloat/multilingual-e5-small"

    def list_topics(self) -> list[str]:
        return self.topics.copy()

    
    def search(
        self,
        query: str,
        topic: str | None = None,
        k: int = 5
    ) -> list[Hit]:
        import numpy as np

        # 1. 检查输入
        if not query or not query.strip() or k <= 0:
            return []

        if topic is not None and topic not in self.topics:
            return []

        # 2. 加载 Embedding 模型（仅首次调用时加载）
        if not hasattr(self, "_model"):
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                self.model_name,
                local_files_only=True
            )

        # 3. 将用户问题转换为向量
        query_vector = self._model.encode(
            ["query: " + query.strip()],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False
        )

        query_vector = np.asarray(
            query_vector, dtype=np.float32
        )

        # 4. FAISS 相似度检索
        # 指定主题时，先检索全部向量，再过滤
        search_k = (
            self.index.ntotal
            if topic is not None
            else min(k, self.index.ntotal)
        )

        if search_k == 0:
            return []

        scores, indices = self.index.search(
            query_vector, search_k
        )

        # 5. 整理检索结果
        hits = []

        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue

            chunk = self.chunks[int(idx)]

            # 主题过滤
            if topic is not None:
                if chunk.get("topic") != topic:
                    continue

            hit = Hit(
                chunk_id=chunk["chunk_id"],
                doc_id=chunk.get("doc_id", chunk.get("url", "")),
                text=chunk["text"],
                score=float(score),
                url=chunk.get("url", ""),
                title=chunk.get("title", ""),
                topic=chunk.get("topic", ""),
                academic_year=chunk.get("academic_year", "")
            )

            hits.append(hit)

            if len(hits) >= k:
                break

        return hits

