"""
Pulls raw execution data for a handful of baseline-v1 FAILED cases and prints,
per node in that execution:
  - whether it ran at all
  - how many output items it produced
  - whether n8n recorded an explicit error on it

Goal: figure out WHY these 10 cases stopped before Draft Brief -- specifically
whether "Agent 1 - Discover Competitors" / "Split Competitors" produced zero
competitors (a real "no discoverable competitors" outcome) vs. some node
throwing an actual error (rate limit, timeout, API failure) that would point
to infra flakiness rather than a genuine agent capability gap.

Usage:
    python3 diagnose_failures.py <execution_id> [<execution_id> ...]

Example (checking a spread of the 10 real baseline-v2 failures):
    python3 diagnose_failures.py 161 165 166 171 176 178 181 184 186 191
"""

import sys
import requests
from harness import N8N_BASE_URL, N8N_API_KEY


def fetch_execution(execution_id: str) -> dict:
    resp = requests.get(
        f"{N8N_BASE_URL}/api/v1/executions/{execution_id}",
        headers={"X-N8N-API-KEY": N8N_API_KEY},
        params={"includeData": "true"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def summarize(execution_id: str):
    execution = fetch_execution(execution_id)
    run_data = execution.get("data", {}).get("resultData", {}).get("runData", {})
    print(f"\n=== Execution {execution_id} (status: finished={execution.get('finished')}, stoppedAt={execution.get('stoppedAt')}) ===")
    if not run_data:
        print("  No runData at all -- execution may not have started properly.")
        return
    for node_name, attempts in run_data.items():
        if not attempts:
            continue
        last = attempts[-1]
        out_items = last.get("data", {}).get("main", [[]])[0]
        n_items = len(out_items) if out_items else 0
        error = last.get("error")
        error_msg = ""
        if error:
            error_msg = f"  <-- ERROR: {error.get('message', error)}"
        print(f"  {node_name}: {n_items} output item(s), {last.get('executionTime')}ms{error_msg}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 diagnose_failures.py <execution_id> [<execution_id> ...]")
        sys.exit(1)
    for execution_id in sys.argv[1:]:
        try:
            summarize(execution_id)
        except Exception as e:
            print(f"\n=== Execution {execution_id}: FAILED TO FETCH -- {e} ===")
