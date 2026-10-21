-- 存储层 schema（分工方案 §5.3 契约，成员①落地）
-- records 表保留为采集原始层（见 src/storage.py），本文件定义其上的规范化层。
-- 用法：python -m src.main --migrate

-- 规范化文档层：URL 为 canonical 形式（导出/迁移时规范化并去重）
CREATE TABLE IF NOT EXISTS documents (
    url           TEXT PRIMARY KEY,
    title         TEXT,
    source        TEXT,
    topic         TEXT,
    column_name   TEXT NOT NULL DEFAULT '', -- 对应 corpus.column
    active        INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    index_dirty   INTEGER NOT NULL DEFAULT 1 CHECK (index_dirty IN (0, 1)),
    corpus_sha256 TEXT NOT NULL DEFAULT '', -- 快照来源；空串表示 records 迁移
    academic_year TEXT,          -- T1：从导出阶段下沉为库列；无学年留空串，不猜测
    date          TEXT,
    crawled_at    TEXT,
    content       TEXT,
    image_urls    TEXT,          -- JSON 数组（不进检索条件，不拆 3NF）
    file_urls     TEXT           -- JSON 数组
);

-- 切块层：WS-B（成员③）负责填充；embedding BLOB 或走 sqlite-vec/FAISS 侧车
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id  TEXT PRIMARY KEY,
    doc_id    TEXT REFERENCES documents(url),
    ord       INTEGER,
    text      TEXT,
    embedding BLOB
);

-- 抓取审计：每次 live 抓取一行，失败计数落库（接管 R1 止血方案后的正式版）
CREATE TABLE IF NOT EXISTS crawl_runs (
    run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT,
    finished_at TEXT,
    column_name TEXT,
    new_count   INTEGER,
    skip_count  INTEGER,
    error_count INTEGER
);

-- 问答日志：demo/评估留痕
CREATE TABLE IF NOT EXISTS qa_logs (
    log_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    question   TEXT,
    answer     TEXT,
    citations  TEXT,             -- JSON 数组（引用 URL 列表）
    latency_ms INTEGER,
    created_at TEXT
);

-- 检索过滤索引（§5.2 Hit 的 topic / academic_year 过滤）
CREATE INDEX IF NOT EXISTS idx_documents_topic_year ON documents(topic, academic_year);
CREATE INDEX IF NOT EXISTS idx_documents_crawled_at ON documents(crawled_at);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id, ord);

-- JSONL 接收审计，独立于真实抓取审计 crawl_runs。
CREATE TABLE IF NOT EXISTS corpus_imports (
    import_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    input_count INTEGER NOT NULL,
    active_count INTEGER NOT NULL,
    report_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_column ON documents(column_name);
CREATE INDEX IF NOT EXISTS idx_documents_active ON documents(active, index_dirty);
