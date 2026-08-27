"""P1-T7 reranker: local quantized ONNX cross-encoder (owner-ratified).

D17 applies: reranking sees the query AND chunk contents, so it stays
on-machine — API rerankers are barred while local delivers (it does:
int8 median 1.1s per 50-pair set on this hardware, top-5 sets identical
to fp32 on all five benchmark sets).

Model identity is pinned in config/retrieval.json (repo + file), weights
cached by huggingface_hub under ~/.cache/huggingface. Tokenization uses the
`tokenizers` library directly (already a transitive dependency) — torch and
transformers are deliberately absent: this machine's torch CPU path
bus-faults inside Apple's Accelerate BLAS (see CLAUDE.md environment facts).

Pure ordering logic (top_k_by_score) is offline-tested; the ONNX session is
lazy-loaded on first use and reused across requests.
"""
from __future__ import annotations

from typing import Hashable

_session = None
_tokenizer = None


def top_k_by_score(ids: list[Hashable], scores: list[float], k: int) -> list[Hashable]:
    """Order ids by descending score, take k. Ties break by original
    (RRF-fused) position so results stay deterministic."""
    if len(ids) != len(scores):
        raise ValueError(f"ids/scores length mismatch: {len(ids)} vs {len(scores)}")
    order = sorted(range(len(ids)), key=lambda i: (-scores[i], i))
    return [ids[i] for i in order[:k]]


def _load(cfg: dict):
    global _session, _tokenizer
    if _session is None:
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        path = hf_hub_download(cfg["model_repo"], cfg["model_file"])
        _session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        _tokenizer = Tokenizer.from_pretrained(cfg["model_repo"])
        _tokenizer.enable_truncation(max_length=512)
        _tokenizer.enable_padding()
    return _session, _tokenizer


def rerank_scores(cfg: dict, question: str, contents: list[str],
                  batch_size: int = 16) -> list[float]:
    """Cross-encoder relevance score for each (question, content) pair."""
    import numpy as np

    session, tokenizer = _load(cfg)
    scores: list[float] = []
    for i in range(0, len(contents), batch_size):
        batch = contents[i:i + batch_size]
        enc = tokenizer.encode_batch([(question, c) for c in batch])
        feed = {
            "input_ids": np.array([e.ids for e in enc], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64),
            "token_type_ids": np.array([e.type_ids for e in enc], dtype=np.int64),
        }
        scores.extend(float(s) for s in session.run(None, feed)[0][:, 0])
    return scores
