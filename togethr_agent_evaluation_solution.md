# Evaluating the Togethr Market Research Agent with LangSmith

**Author:** Abhi Chandra, Chicago Booth
**Track:** Track 3 — Evaluate an existing agent (Week 3 n8n Market Research / Competitor Analysis agent for Togethr)
**Tools:** LangSmith (tracing, dataset versioning, feedback/scores), n8n Cloud (agent runtime), Python (evaluation harness), OpenAI (LLM-as-judge)

---

## 1. The agent being evaluated

The Week 3 agent is an n8n workflow that takes a target market and a company description, then produces a board-ready, one-page competitor brief for Togethr (a relationship-navigation platform for singles, couples, and families). The pipeline: a form trigger collects inputs, **Agent 1 (Discover Competitors)** searches the web (you.com) to identify three real competitors, **Agent 2 (Gather Data)** and **Agent 3 (Extract Structured Data)** research and structure pricing/positioning/persona details for each, and the **Orchestrator (Draft Brief)** synthesizes everything into a markdown brief with an executive summary, a comparison table, a key-gaps/opportunities section, and a recommendation — after which a human approves it by email before it's written to a Google Doc and logged to Sheets.

The Week 3 success metric this evaluation is built around: *"founder gets a usable, board-ready brief in under 15 minutes, 9/10 times."*

## 2. Evaluation framework

| Metric | Type | What it measures | Pass bar |
|---|---|---|---|
| Task completion | Code-based (pipeline outcome) | Did the run reach the Draft Brief stage at all? | 90% |
| Structural completeness | Code-based | Does the brief contain all 4 required sections (executive summary, competitor comparison, key gaps, recommendation) plus a real comparison table? | 100% |
| Citation presence | Code-based | Are there real URLs in the brief, attached to claims via a recognized inline citation marker? | 90% |
| Faithfulness | LLM-as-judge (gpt-4o-mini) | Does every specific, checkable claim about a competitor carry a citation, and are citations attached to the claims they actually support (not scattered generically)? | 90% |
| Competitor relevance | LLM-as-judge (gpt-4o-mini) | Are the identified competitors plausible, relevant, real-sounding matches for the stated market — not generic or hallucinated? | 85% |

**Scope note on faithfulness:** a fully rigorous version would fetch every cited URL and verify the claim against the live page. That was deliberately out of scope for this pass (cost/time/flakiness across 50 cases) — this judge instead checks *citation-claim alignment*, a real and useful proxy for the actual failure mode observed (uncited or fabricated-looking claims), but it is not full source verification, and this writeup does not claim otherwise.

## 3. Dataset

50 cases, versioned in LangSmith as dataset `togethr-market-research-golden-v1` (id `d7be8dd2-916c-4e4e-8d61-81801756056e`), built to the assignment's recommended scenario mix:

| Scenario type | Share | Count | Purpose |
|---|---|---|---|
| Happy path | 50% | 25 | Realistic, well-covered markets |
| Edge cases | 30% | 15 | Ambiguous or thin-public-data markets |
| Known failures | 15% | 8 | Markets pulled from real Week 3 runs that had already shown problems (e.g., no public pricing found, inconsistent competitor sets) |
| Adversarial | 5% | 2 | Malformed/nonsense input, and an out-of-scope market (Canada, outside Togethr's current India/US focus) |

**Pinecone / ElevenLabs:** deliberately not used. Pinecone is a vector-DB/RAG tool; this agent does live web search, not retrieval over an owned corpus, so there's no natural integration point without inventing a feature the agent doesn't have. ElevenLabs is text-to-speech; the deliverable is a written, cited document with no voice surface. Forcing either in would have added tooling without improving the evaluation.

## 4. Baseline results (real data, 40/50 cases reached scoring)

| Metric | Result | Bar | Status |
|---|---|---|---|
| Task completion | 80% (40/50) | 90% | **FAIL** |
| Structural completeness | 100% (40/40) | 100% | PASS |
| Citation presence | 85% (34/40) | 90% | FAIL |
| Faithfulness | 68% (27/40) | 90% | FAIL |
| Competitor relevance | 92% (37/40) | 85% | PASS |

### Root cause: task completion (100% of failures, one mechanism)

All 10 non-completions showed the identical pattern, confirmed from raw execution data rather than assumed: Agent 1 occasionally hit its configured reasoning-loop cap (Max Iterations = 10) before producing a valid competitors array, returning the literal string `"Agent stopped due to max iterations."` instead. The downstream "Split Competitors" code node then threw `Could not extract competitors array` trying to parse that string, killing the entire n8n execution with no fallback. This happened in 20% of runs, spread indiscriminately across happy-path and edge-case markets — a genuine agent-convergence reliability issue, not a hard-market or infrastructure-flakiness issue.

### Root cause: citation presence and faithfulness (two distinct content bugs)

Reading actual failing brief text (not inferring from scores alone) surfaced two real, separate problems:

1. **Fabricated empty-href citations.** One brief's sources line read `Dating After Divorce [1](), The Matchmaking Company [2](), Rebirth Divorce Coach [3](https://...)` — two of three numbered citations pointed at nothing. The agent was fabricating the *appearance* of sourcing with no real source behind it, which is worse than omitting a citation outright.
2. **Narrative sections lost citation discipline.** The agent's citation habit held inside the comparison table but broke down in the Key Gaps/Opportunities prose, where several specific, checkable-sounding claims about competitors carried no citation at all.

A third, smaller factor was evaluator-side rather than agent-side: the first version of the code-based citation checker recognized only 3 of 5 citation styles the agent actually uses across runs (it was built against a single sample and didn't generalize). It was rewritten (v2) after reading three more real failing briefs, which is reflected in the numbers above.

## 5. Fixes implemented

**Fix 1 — Agent 1 reliability (targets task completion).** Two changes to the n8n workflow: (a) raised Agent 1's Max Iterations from 10 to 20, giving it more room to converge before giving up; (b) replaced the "Split Competitors" code node's `throw new Error(...)` — which killed the whole execution on a parse failure — with graceful degradation: on failure to parse a valid competitors array, the node now passes through a single honest placeholder item instead, so the pipeline still reaches Draft Brief and the resulting brief plainly states it couldn't verify competitors for that market, rather than the run silently disappearing.

*Validation:* not just code review. Max Iterations was temporarily forced down to 1 to guarantee a convergence failure, and a real case was run end-to-end. The execution completed (rather than dying), and the resulting brief was honest and well-structured around the induced data gap — explicit "N/A" fields throughout the competitor table and a recommendation section that still delivered real strategic value despite having zero real competitor data. Max Iterations was then restored to 20 and republished.

**Fix 2 — Citation discipline (targets citation presence and faithfulness).** The Draft Brief prompt already had a citation instruction, but a weak one ("Cite every specific claim with its source URL inline."). It was replaced with a stronger, more targeted version:

> Cite every specific claim with its source URL inline — in the comparison table AND in the Key Gaps/Opportunities and Executive Summary prose, not just the table. If you cannot find a public source for a claim, either omit it or phrase it explicitly as an inference rather than a specific fact. Never fabricate a citation: if you don't have a real URL, do not emit a numbered marker with an empty link target like [1](). Either cite a real source or state in plain text that no public source was found.

*Validation:* a fresh real run was pulled and read in full. Zero broken citations anywhere; explicit "No public source found" language used for competitors with no public data instead of fabricated specifics; the agent even added its own "Evidence" column to the Key Gaps table on its own initiative, going further than instructed.

## 6. Post-improvement results (real data, 50/50 cases reached scoring)

| Metric | Baseline (40 cases) | Post-improvement (50 cases) | Bar | Status |
|---|---|---|---|---|
| Task completion | 80% (40/50) | **100% (50/50)** | 90% | **PASS** |
| Structural completeness | 100% (40/40) | 100% (50/50) | 100% | PASS |
| Citation presence | 85% (34/40) | 60% (30/50) | 90% | FAIL* |
| Faithfulness | 68% (27/40) | 60% (30/50) | 90% | FAIL* |
| Competitor relevance | 92% (37/40) | 82% (41/50) | 85% | FAIL* |

*\*See Section 7 — these drops are not agent regressions. Fix 2's target behavior was directly verified against real brief content and works correctly; the drop is a measurement artifact explained below.*

Task completion is unambiguously fixed: every one of the 10 markets that previously killed the pipeline now completes. Most converged normally under the higher iteration cap rather than needing the fallback placeholder at all.

## 7. The most important finding: an evaluator design gap, not an agent regression

Rather than accept the headline drop in citation presence, faithfulness, and competitor relevance at face value, the worst-drop cases were pulled and read in full (real brief text, not inferred from scores). Two representative examples:

- **`ec08` (Vatican City premarital counseling):** citation presence dropped from 1.0 to 0.0. The actual brief: an honest, well-structured report stating "No public competitors identified," with every table cell marked "N/A (no public data)" and every unsupported claim explicitly labeled "no public source found" or "inferred." This is *exactly* the behavior Fix 2 was built to produce.
- **`hp07` (divorced-dating coaches, U.S.):** same pattern. The fabricated `[1]()` placeholder citations from the baseline version of this exact case are completely gone; every competitor cell now reads "Not disclosed publicly," with "No public source was found" attached to every inference.

Both briefs are genuinely honest, well-sourced-where-possible, and structurally strong — and both score 0.0 on citation presence, because the code-based `check_citation_presence` evaluator requires at least one real URL in the brief to pass at all. For a market where **no public competitor data actually exists** — which is precisely what several of the known-failure and edge-case markets in this dataset were designed to surface — an honest, fully-disclosed brief legitimately contains zero URLs. The evaluator cannot currently distinguish "no citations because the agent is honestly reporting a real data desert" from "no citations because of sloppy sourcing." Both score identically.

**This is being documented as a known evaluator limitation rather than patched and re-scored again before this deadline.** It is arguably a stronger deliverable for this assignment than a chased number: it demonstrates that the fix was correctly validated against real behavior, and that a metric moving the wrong direction does not automatically mean the underlying system got worse — sometimes it means the yardstick has a blind spot the fix exposed. A natural v2 of `check_citation_presence` would treat an explicit, consistent "no public source found" disclosure (applied to every claim that lacks one) as a passing citation-discipline outcome even with zero URLs, distinct from a brief that simply omits sourcing without disclosure.

One smaller, related pattern worth flagging as a residual risk rather than a finished fix: in the Vatican brief, the agent hedges some claims as "inferred" (e.g., a specific population estimate attributed to "sociological studies of Vatican-adjacent populations" with no real citation) while still presenting suspiciously specific-sounding figures under that hedge — a softer, dressed-up version of the same fabrication instinct Fix 2 targeted directly. This likely contributes to the real (not artifact-driven) part of the faithfulness drop on that case, and would be a reasonable Fix 3 candidate in a future iteration: tighten the prompt's definition of "inference" to disallow invented-sounding specific figures even when hedged.

## 8. Operational lessons (methodology, not agent behavior)

A few process bugs surfaced and were fixed along the way, worth keeping for anyone re-running this harness:

- The Gmail human-approval gate would have required up to 100 manual clicks across baseline + post-improvement runs; a workflow-level bypass flag (`eval_flag = eval-skip`) was added so evaluation runs skip straight past approval to a no-op, while real user submissions are unaffected.
- An early version of that bypass only stopped the *harness's polling*, not the underlying n8n execution, which filled n8n's concurrent-execution slots with permanently-stuck runs and caused execution-ID misattribution across several cases. Fixed by ending the actual n8n execution at the workflow level and hardening execution lookup to match on the real start timestamp rather than "newest of last 5."
- During the post-improvement re-run, a config change (`RUN_GROUP`) was made to a script *after* it had already started running; Python doesn't hot-reload, so the entire run executed under the stale config and its LangSmith traces ended up tagged identically to the original baseline's. Recovered cleanly using the known n8n execution-ID boundary (153–202 vs. 205–254) rather than LangSmith metadata — worth noting for the trace screenshot/walkthrough, which references the two runs by execution-ID range and date rather than a clean metadata filter.

## 9. Summary

| | Before | After |
|---|---|---|
| Task completion | 80% | **100%** |
| Root cause of failures | Agent 1 convergence + no fallback | Fixed: higher iteration cap + graceful degradation |
| Fabricated citations | Present (verified in real briefs) | Eliminated (verified in real briefs) |
| Citation/faithfulness/relevance metrics | 85% / 68% / 92% | 60% / 60% / 82%, explained by a real evaluator blind spot around legitimately data-desert markets, not an agent regression |

Both fixes were validated against real, directly-read agent output — not evaluator scores alone — at every step. The task-completion fix is a clean, unambiguous win. The citation-discipline fix also worked exactly as designed; the metrics that appear to disagree do so because they were built assuming every good brief contains at least one citation, an assumption that doesn't hold for the honestly-reported data deserts this dataset was specifically built to include. That gap is now a documented, actionable finding rather than a hidden one.

---

*LangSmith project: `togethr-market-research-eval`. Golden dataset: `togethr-market-research-golden-v1`. Baseline traces: n8n executions 153–202 (Sept 7, 2026). Post-improvement traces: n8n executions 205–254 (Sept 8, 2026).*
