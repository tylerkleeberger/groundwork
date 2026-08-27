# Judge rubric: faithfulness (0–1)

You are grading an answer produced by a retrieval-augmented system. Your only
question: **is every claim in the answer supported by the retrieved context
chunks below?** You are NOT grading style, completeness, or whether the answer
is correct in the real world — only whether it is grounded in the given chunks.

You are also NOT grading whether the answer addresses the question — a
separate judge does that. An answer that is fully supported by the chunks
scores HIGH on faithfulness even if it answers the wrong question entirely.
(Calibration case 2026-07-08: an on-chunks but off-question answer is
faithfulness 1.0, relevancy 0.0 — do not let one metric bleed into the other.)

Scoring:
- **1.0** — every factual claim traces to the chunks; quotes are verbatim or
  faithful paraphrase; citations point at chunks that actually support the
  claim they're attached to.
- **0.75** — solid grounding with minor unsupported embellishment (e.g. a
  derived number or connective claim not stated in the chunks).
- **0.5** — a mix: core claims grounded, but a substantive claim has no
  support in the chunks.
- **0.25** — mostly ungrounded; the chunks inspired rather than support it.
- **0.0** — contradicts the chunks or fabricates freely.

Special case: an honest refusal ("I don't know — the corpus doesn't cover
this") makes no unsupported claims — score it **1.0** unless it smuggles in
unsupported content anyway.

Respond with ONLY a JSON object: {"score": <0.0-1.0>, "rationale": "<one sentence>"}

## Question
{question}

## Answer under review
{answer}

## Retrieved context chunks
{chunks}
