"""Isolate PyTorch from FAISS's OpenMP runtime on macOS.

The worker only encodes/tokenizes; all retrieval, ranking and source checks stay
in the existing Retriever and application process. No network access is needed.
"""
from __future__ import annotations

import atexit
import multiprocessing
import os


def _worker(connection, model_path):
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    try:
        import torch
        from sentence_transformers import SentenceTransformer
        torch.set_num_threads(1)
        model = SentenceTransformer(model_path, local_files_only=True, device="cpu")
        connection.send(("ready", (model.get_sentence_embedding_dimension(), model.max_seq_length)))
        while True:
            command, values, options = connection.recv()
            if command == "close":
                break
            try:
                if command == "encode":
                    answer = model.encode(values, **options)
                elif command == "token_counts":
                    answer = [len(model.tokenizer.encode(text, truncation=False)) for text in values]
                else:
                    raise ValueError("Unknown encoding operation")
                connection.send(("ok", answer))
            except Exception as exc:
                connection.send(("error", type(exc).__name__))
    except (EOFError, BrokenPipeError):
        pass
    except Exception as exc:
        try:
            connection.send(("error", type(exc).__name__))
        except (EOFError, BrokenPipeError):
            pass
    finally:
        connection.close()


class LocalEncoder:
    """Reusable single-query-at-a-time encoder; close it when the backend stops."""

    def __init__(self, model_path, *, timeout=300):
        context = multiprocessing.get_context("spawn")
        self.connection, child = context.Pipe()
        self.timeout = timeout
        self.process = context.Process(target=_worker, args=(child, str(model_path)), daemon=True)
        self.process.start()
        child.close()
        try:
            status, value = self._receive()
            if status != "ready":
                raise RuntimeError("E5 initialization failed")
            self.dimension, self.max_seq_length = value
        except Exception:
            self.close()
            raise
        atexit.register(self.close)

    def _receive(self):
        if not self.connection.poll(self.timeout):
            raise RuntimeError("E5 worker timed out")
        try:
            return self.connection.recv()
        except EOFError as exc:
            raise RuntimeError("E5 worker stopped unexpectedly") from exc

    def _request(self, command, values, options):
        try:
            self.connection.send((command, values, options))
            status, result = self._receive()
        except (OSError, EOFError, RuntimeError) as exc:
            self.close()
            raise RuntimeError("E5 worker request failed") from exc
        if status != "ok":
            raise RuntimeError("E5 encoding failed")
        return result

    def encode(self, texts, **kwargs):
        return self._request("encode", texts, kwargs)

    def token_counts(self, texts):
        return self._request("token_counts", texts, {})

    def get_sentence_embedding_dimension(self):
        return self.dimension

    def close(self):
        if self.process.is_alive():
            try:
                self.connection.send(("close", None, None))
            except (OSError, EOFError):
                pass
            self.process.join(timeout=2)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=2)
        self.connection.close()
