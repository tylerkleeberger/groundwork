"""P0 acceptance: one traced call per gateway target.
.env: see .env.example (LANGFUSE_HOST=http://localhost:8300, GATEWAY=http://localhost:4000)
Run: python scripts/smoke.py  (gateway must be up: scripts/gateway.sh)
"""
import os
from openai import OpenAI  # any OpenAI-compatible client works against LiteLLM

client = OpenAI(base_url=os.getenv("GATEWAY", "http://localhost:4000"), api_key="anything")

for alias in ("cheap", "local", "frontier"):
    try:
        r = client.chat.completions.create(
            model=alias, max_tokens=50,
            messages=[{"role": "user", "content": f"Reply with exactly: {alias} OK"}],
        )
        print(f"[PASS] {alias:9s} -> {r.choices[0].message.content!r}")
    except Exception as e:
        print(f"[FAIL] {alias:9s} -> {e}")
print("\nNow open Langfuse (http://localhost:8300): three traces, each with cost.")
