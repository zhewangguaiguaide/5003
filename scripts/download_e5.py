"""Download one pinned official E5 snapshot; no API key or custom model code."""
import argparse
from pathlib import Path

MODEL = "intfloat/multilingual-e5-small"
REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
FILES = ["config.json", "modules.json", "1_Pooling/config.json", "sentence_bert_config.json",
         "sentencepiece.bpe.model", "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json",
         "model.safetensors", "README.md"]


def main():
    from huggingface_hub import snapshot_download
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/models/e5-small-614241f")
    args = parser.parse_args()
    path = snapshot_download(MODEL, revision=REVISION, local_dir=args.output,
                             allow_patterns=FILES, token=False, max_workers=4)
    (Path(path) / "REVISION").write_text(REVISION + "\n", encoding="utf-8")
    print(f"Prepared {MODEL} revision {REVISION} in {args.output}")


if __name__ == "__main__":
    main()
