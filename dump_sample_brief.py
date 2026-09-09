"""
Dumps the raw "Orchestrator - Draft Brief" output text for one successful
execution to a local file, so we can inspect the real structure (headers,
table format, sources format, etc.) before designing evaluators against it.

Usage:
    python3 dump_sample_brief.py <execution_id> [<output_file>]

Example (a happy-path success from the real baseline run):
    python3 dump_sample_brief.py 153 sample_brief_hp01.txt
"""

import sys
import json
import requests
from harness import N8N_BASE_URL, N8N_API_KEY, NODE_NAMES


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
    if len(sys.argv) < 2:
        print("Usage: python3 dump_sample_brief.py <execution_id> [<output_file>]")
        sys.exit(1)

    execution_id = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else f"sample_brief_{execution_id}.txt"

    execution = fetch_execution(execution_id)
    run_data = execution.get("data", {}).get("resultData", {}).get("runData", {})
    draft_node = NODE_NAMES["draft"]
    attempts = run_data.get(draft_node)
    if not attempts:
        print(f"No '{draft_node}' output found in execution {execution_id}.")
        sys.exit(1)

    out_items = attempts[-1].get("data", {}).get("main", [[]])[0]
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump([item.get("json") for item in out_items], f, indent=2, ensure_ascii=False)

    print(f"Wrote Draft Brief output for execution {execution_id} to {output_file}")
