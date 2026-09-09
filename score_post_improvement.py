"""
Scores every successfully-completed case from baseline_results.csv against
all four eval-plan metrics:
  - structural_completeness (code-based, evaluators.py)
  - citation_presence       (code-based, evaluators.py)
  - faithfulness            (LLM-as-judge, llm_judges.py)
  - competitor_relevance    (LLM-as-judge, llm_judges.py)

Writes evaluation_scores.csv (one row per completed case) and prints a
summary of pass rates against the eval plan's stated pass bars:
  90% faithfulness, 85% competitor relevance, 100% structural completeness,
  90% citation presence (task completion itself -- 90% target -- is already
  known from baseline_results.csv: 40/50 = 80%, below bar, root-caused
  separately).

Also attaches each score as LangSmith feedback on that case's trace (so the
scores are visible right on the trace in the togethr-market-research-eval
project, not just in this local CSV) -- best-effort, continues if a
particular feedback call fails.

Requires OPENAI_API_KEY in .env for the LLM-judge metrics. If it's not set,
this script still runs the two code-based metrics for every case and prints
a clear note about what's missing, rather than failing outright -- partial,
honest results beat no results.

Usage:
    python3 score_baseline.py
"""

import csv
import json
import sys

import requests
from langsmith import Client as LangSmithClient

from harness import N8N_BASE_URL, N8N_API_KEY, NODE_NAMES, LANGSMITH_API_KEY, LANGSMITH_PROJECT
from evaluators import extract_brief_text, check_structural_completeness, check_citation_presence

BASELINE_RESULTS_CSV = "post_improvement_results.csv"
GOLDEN_DATASET_CSV = "golden_dataset.csv"
OUTPUT_CSV = "evaluation_scores_post_improvement.csv"

try:
    from llm_judges import judge_faithfulness, judge_competitor_relevance
    LLM_JUDGES_AVAILABLE = True
except Exception as e:
    LLM_JUDGES_AVAILABLE = False
    _llm_judge_import_error = e


def fetch_execution(execution_id: str) -> dict:
    resp = requests.get(
        f"{N8N_BASE_URL}/api/v1/executions/{execution_id}",
        headers={"X-N8N-API-KEY": N8N_API_KEY},
        params={"includeData": "true"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_draft_brief_text(execution_id: str) -> str:
    execution = fetch_execution(execution_id)
    run_data = execution.get("data", {}).get("resultData", {}).get("runData", {})
    attempts = run_data.get(NODE_NAMES["draft"])
    if not attempts:
        return ""
    out_items = attempts[-1].get("data", {}).get("main", [[]])[0]
    stage_output = [item.get("json") for item in out_items] if out_items else None
    return extract_brief_text(stage_output)


def load_csv_as_dict(path, key_field):
    with open(path, newline="", encoding="utf-8") as f:
        return {row[key_field]: row for row in csv.DictReader(f)}


def main():
    baseline = load_csv_as_dict(BASELINE_RESULTS_CSV, "case_id")
    golden = load_csv_as_dict(GOLDEN_DATASET_CSV, "case_id")

    llm_available = LLM_JUDGES_AVAILABLE
    if not llm_available:
        print(
            f"[note] LLM-as-judge evaluators unavailable ({_llm_judge_import_error}). "
            f"Continuing with code-based metrics only (structural_completeness, "
            f"citation_presence). Add OPENAI_API_KEY to .env and re-run to get "
            f"faithfulness + competitor_relevance scores too.\n"
        )

    ls_client = LangSmithClient(api_key=LANGSMITH_API_KEY) if LANGSMITH_API_KEY else None

    rows_out = []
    completed_cases = [
        (case_id, row) for case_id, row in baseline.items()
        if row.get("task_completed") == "True"
    ]
    print(f"Scoring {len(completed_cases)} completed cases out of {len(baseline)} total...\n")

    for i, (case_id, base_row) in enumerate(completed_cases, start=1):
        execution_id = base_row["n8n_execution_id"]
        trace_id = base_row["langsmith_trace_id"]
        scenario_type = base_row["scenario_type"]
        golden_row = golden.get(case_id, {})
        market = golden_row.get("target_market", "")
        company_description = golden_row.get("company_description", "")

        print(f"[{i}/{len(completed_cases)}] {case_id} ({scenario_type})...")

        try:
            brief_text = get_draft_brief_text(execution_id)
        except Exception as e:
            print(f"  -> ERROR fetching execution {execution_id}: {e}")
            continue

        if not brief_text.strip():
            print(f"  -> WARNING: empty brief text for execution {execution_id}, skipping.")
            continue

        struct = check_structural_completeness(brief_text)
        citation = check_citation_presence(brief_text)

        result_row = {
            "case_id": case_id,
            "scenario_type": scenario_type,
            "n8n_execution_id": execution_id,
            "langsmith_trace_id": trace_id,
            "structural_completeness_score": struct["score"],
            "structural_completeness_passed": struct["passed"],
            "citation_presence_score": citation["score"],
            "citation_presence_passed": citation["passed"],
            "faithfulness_score": "",
            "faithfulness_passed": "",
            "competitor_relevance_score": "",
            "competitor_relevance_passed": "",
        }

        feedback_scores = {
            "structural_completeness": struct["score"],
            "citation_presence": citation["score"],
        }

        if llm_available:
            try:
                faith = judge_faithfulness(brief_text)
                result_row["faithfulness_score"] = faith["score"]
                result_row["faithfulness_passed"] = faith["passed"]
                feedback_scores["faithfulness"] = faith["score"]
            except Exception as e:
                print(f"  -> faithfulness judge failed: {e}")

            try:
                relevance = judge_competitor_relevance(brief_text, market, company_description)
                result_row["competitor_relevance_score"] = relevance["score"]
                result_row["competitor_relevance_passed"] = relevance["passed"]
                feedback_scores["competitor_relevance"] = relevance["score"]
            except Exception as e:
                print(f"  -> competitor_relevance judge failed: {e}")

        rows_out.append(result_row)
        print(
            f"  -> structural={struct['score']:.2f} citation={citation['score']:.2f} "
            f"faithfulness={result_row['faithfulness_score']} "
            f"competitor_relevance={result_row['competitor_relevance_score']}"
        )

        if ls_client and trace_id:
            for key, score in feedback_scores.items():
                try:
                    ls_client.create_feedback(run_id=trace_id, key=key, score=score)
                except Exception as e:
                    print(f"  -> (non-fatal) LangSmith feedback '{key}' failed: {e}")

    if not rows_out:
        print("\nNo cases scored -- nothing to write.")
        return

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        writer.writeheader()
        writer.writerows(rows_out)

    n = len(rows_out)

    def pct(field):
        passed = sum(1 for r in rows_out if r[field] is True or r[field] == "True")
        return 100.0 * passed / n if n else 0.0

    print(f"\n=== Summary across {n} scored cases (out of 50 total, 40 completed to Draft Brief) ===")
    print(f"Structural completeness: {pct('structural_completeness_passed'):.0f}% pass (bar: 100%)")
    print(f"Citation presence:       {pct('citation_presence_passed'):.0f}% pass (bar: 90%)")
    if llm_available:
        print(f"Faithfulness:            {pct('faithfulness_passed'):.0f}% pass (bar: 90%)")
        print(f"Competitor relevance:    {pct('competitor_relevance_passed'):.0f}% pass (bar: 85%)")
    else:
        print("Faithfulness / competitor relevance: not scored (OPENAI_API_KEY missing)")
    print(f"\nFull per-case results written to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
