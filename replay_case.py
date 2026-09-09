"""
Replay an ALREADY-COMPLETED n8n execution into LangSmith, using the current
NODE_NAMES mapping in harness.py -- without triggering any new n8n run.

Use this whenever we fix NODE_NAMES (or other extraction logic) and want to
re-validate against a real execution we already have, instead of spending
more OpenAI/you.com credits and sending another approval email.

Usage:
    python3 replay_case.py <execution_id> <case_id>

Example (re-processing execution #99 from tonight's Phase 0 run):
    python3 replay_case.py 99 phase0-smoke-test-v2
"""

import sys
import requests
from harness import (
    N8N_BASE_URL,
    N8N_API_KEY,
    extract_node_runs,
    log_case_to_langsmith,
)


def fetch_execution(execution_id: str) -> dict:
    resp = requests.get(
        f"{N8N_BASE_URL}/api/v1/executions/{execution_id}",
        headers={"X-N8N-API-KEY": N8N_API_KEY},
        params={"includeData": "true"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 replay_case.py <execution_id> <case_id>")
        sys.exit(1)

    execution_id, case_id = sys.argv[1], sys.argv[2]
    execution = fetch_execution(execution_id)
    stages = extract_node_runs(execution)

    print(f"Stages successfully extracted: {list(stages.keys())}")

    final_output = stages.get("draft", {}).get("output")
    trace_id = log_case_to_langsmith(
        case_id=case_id,
        inputs={"note": f"replayed from n8n execution {execution_id}"},
        stages=stages,
        final_output={"brief": final_output},
        expected=None,
        extra_metadata={"n8n_execution_id": execution_id, "replayed": True},
    )
    print(f"Replayed execution {execution_id} as case '{case_id}' -> LangSmith trace {trace_id}")
