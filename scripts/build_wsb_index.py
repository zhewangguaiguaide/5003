
import json
from dataclasses import asdict
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from src.retriever import load_corpus, chunk_records


# 项目根目录
ROOT = Path(__file__).resolve().parents[1]

# 输入与输出路径
CORPUS_PATH = ROOT / "data" / "corpus.jsonl"
INDEX_DIR = ROOT / "data" / "wsb_index"

# Embedding 模型
MODEL_NAME = "intfloat/multilingual-e5-small"


def main():
    # 1. 读取语料并生成 Chunk
    records = load_corpus(CORPUS_PATH)
    chunks = chunk_records(records)

    print("Chunk 数量:", len(chunks))

    if not chunks:
        raise ValueError("没有可用于建立索引的 Chunk")

    # 2. 加载 Embedding 模型
    model = SentenceTransformer(
        MODEL_NAME,
        local_files_only=True
    )

    # E5 文档向量需要 passage: 前缀
    texts = ["passage: " + chunk.text for chunk in chunks]

    # 3. 生成 Embedding
    embeddings = model.encode(
        texts,
        batch_size=16,
        show_progress_bar=True,
        normalize_embeddings=True
    )

    embeddings = np.asarray(embeddings, dtype=np.float32)

    print("Embedding 形状:", embeddings.shape)

    # 4. 建立 FAISS 索引
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)

    print("FAISS 向量数量:", index.ntotal)

    # 5. 保存索引和 Chunk 元数据
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

     # 使用 Python 文件操作保存 FAISS 索引，兼容中文路径
    (INDEX_DIR / "index.faiss").write_bytes(
        faiss.serialize_index(index).tobytes()
    )

    metadata = {
        "model": MODEL_NAME,
        "dimension": dimension,
        "chunks": [asdict(chunk) for chunk in chunks]
    }

    with (INDEX_DIR / "chunks.json").open(
        "w", encoding="utf-8"
    ) as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print("索引构建完成")
    print("保存目录:", INDEX_DIR)


if __name__ == "__main__":
    main()
