# Phase 2 scoring -- run this when you're back

## What's ready

Four new files in this folder, all written and syntax-checked while you were away:

- `evaluators.py` -- the two **code-based** evaluators (structural completeness, citation
  presence). Already validated against a real Draft Brief sample (`sample_brief_hp01.txt`,
  execution 153) -- both scored a clean 1.0 on that sample.
- `llm_judges.py` -- the two **LLM-as-judge** evaluators (faithfulness, competitor relevance).
  See the scope note at the top of that file: faithfulness here checks *citation-claim
  alignment* (does every specific claim carry a citation, attached correctly) rather than
  fetching and verifying live source URLs -- a deliberate, documented scope choice for time,
  not an oversight. Worth stating plainly in your final writeup rather than overclaiming.
- `score_baseline.py` -- orchestrates both, scoring all 40 successfully-completed baseline
  cases, writing `evaluation_scores.csv`, printing a pass-rate summary against the eval
  plan's stated bars, and (best-effort) attaching each score as LangSmith feedback directly
  on that case's trace.
- `dump_sample_brief.py` -- the small utility we used together to pull real sample text
  before designing the evaluators (already used, no more action needed on this one).

## Before running

Two things need your real Terminal (network + your OpenAI key):

```bash
cd ~/Documents/togethr-langsmith-eval
source venv/bin/activate
pip install -r requirements.txt   # adds the "openai" package
```

Then add your OpenAI API key to `.env` (append a line like):

```
OPENAI_API_KEY=sk-...
```

If you don't have one handy or don't want to spend the credits right now, that's fine --
skip this step and the script will still run the two code-based metrics for every case and
print a clear note that faithfulness/competitor_relevance were skipped. You can always
re-run later once you add the key; the code-based scores won't change, so nothing is wasted.

## Run it

```bash
python3 score_baseline.py
```

This calls the OpenAI API twice per completed case (40 cases x 2 calls = 80 calls) if the
key is present, so budget a few minutes and a small amount of API spend (gpt-4o-mini by
default, configurable via `LLM_JUDGE_MODEL` in `.env` if you want to use a different model).

## What to expect

Per-case progress lines, then a summary like:

```
=== Summary across 40 scored cases (out of 50 total, 40 completed to Draft Brief) ===
Structural completeness: XX% pass (bar: 100%)
Citation presence:       XX% pass (bar: 90%)
Faithfulness:            XX% pass (bar: 90%)
Competitor relevance:    XX% pass (bar: 85%)

Full per-case results written to evaluation_scores.csv
```

Send me `evaluation_scores.csv` (or paste the summary) once it's done -- that's the real
quality picture we need before deciding what Phase 3's 3-4 targeted improvements should be.
Combined with the max-iterations root cause we already found, we should have everything
needed to design a solid improvement pass.
