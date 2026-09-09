"""
LLM-as-judge evaluators for the Draft Brief output: faithfulness and
competitor relevance (the two metrics the eval plan designates as LLM-judged
rather than code-based).

SCOPE NOTE on faithfulness: a fully rigorous faithfulness check would fetch
each cited URL and verify the claim against the live page content. That's a
real stretch goal, not this version -- fetching ~3-5 URLs per case x 40 cases
adds meaningful time, cost, and flakiness (paywalls, bot-blocking, dead
links) for a course deadline. This version's faithfulness judge instead
checks *citation-claim alignment*: does every specific, checkable claim
(a price, a stat, a named feature) carry a citation marker, and does nothing
read as fabricated/overly-precise without one. This is a real, useful, and
honest proxy -- it catches the actual failure mode we observed in Phase 0
(uncited claims, mismatched citations) -- but it is not full source
verification, and the project writeup should say so plainly rather than
overclaim rigor it doesn't have.

Requires OPENAI_API_KEY in .env. If it's not set, both judges raise a clear
RuntimeError rather than failing silently or fabricating a score.
"""

import os
import json
import re
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LLM_JUDGE_MODEL = os.environ.get("LLM_JUDGE_MODEL", "gpt-4o-mini")

_client = None


def _get_client():
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not set -- add it to .env to run the LLM-as-judge "
                "evaluators (judge_faithfulness / judge_competitor_relevance). Code-based "
                "evaluators (evaluators.py) don't need this and can run without it."
            )
        from openai import OpenAI
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def _call_judge(system_prompt: str, user_prompt: str) -> dict:
    client = _get_client()
    response = client.chat.completions.create(
        model=LLM_JUDGE_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fall back to pulling the first {...} blob out of the response.
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise RuntimeError(f"Judge did not return valid JSON: {raw!r}")


FAITHFULNESS_SYSTEM_PROMPT = """You are a strict fact-checking judge reviewing a competitor \
research brief for citation discipline -- NOT for whether the underlying facts are true \
(vou cannot verify live web pages), but for whether every specific, checkable claim ABOUT A \
COMPETITOR (a price, a percentage, a named feature, a market-size figure, a direct quote) \
carries a citation, and whether citations are attached to the claims they actually support \
rather than scattered generically.

IMPORTANT SCOPE NOTE: only evaluate factual claims made ABOUT THE COMPETITORS being profiled \
(their pricing, positioning, features, target personas, etc.), typically found in sections \
like a competitor comparison table or key-gaps analysis. Do NOT penalize the brief's own \
forward-looking strategic recommendations, projections, or estimates about Togethr itself \
(e.g. a projected revenue target, an expected conversion-rate lift, a go-to-market timeline) \
-- those are the brief author's own strategic judgment, not claims requiring external \
citation, and should be ignored entirely for this score.

IMPORTANT FORMAT NOTE: citation markers can appear in several different styles across \
different briefs -- do not penalize a brief just because it doesn't use one specific style. \
All of the following count as valid citation markers: a markdown footnote like [^label], a \
bracketed marker like [1] or 【source1】, a directly embedded URL, a bracketed raw URL like \
【https://example.com】, an angle-bracket-wrapped URL like <https://example.com>, or a \
numbered markdown link like [1](https://example.com). Judge only whether SOME such marker \
is present and reasonably attached to the claim -- not which specific style is used. The \
ONE exception: a numbered citation with an EMPTY link target, like [1](), is NOT a valid \
citation -- it is a fabricated citation placeholder with no real source behind it, and a \
claim carrying only that kind of marker should be treated as effectively uncited.

Score from 1 (many uncited or mismatched competitor-related claims) to 5 (essentially every \
specific competitor-related claim is properly cited, citations are attached to the right \
claims). Respond ONLY with a JSON object: {"score": <1-5 integer>, "uncited_claims": [<short \
quotes of competitor-related claims lacking a citation, if any -- do not include Togethr's \
own strategic recommendations here>], "rationale": "<one or two sentences>"}"""

COMPETITOR_RELEVANCE_SYSTEM_PROMPT = """You are a judge assessing whether the competitors \
identified in a market research brief are actually plausible, relevant competitors for the \
stated target market and company -- not generic, off-topic, or clearly hallucinated \
companies.

Score from 1 (competitors are irrelevant, generic, or implausible for this market) to 5 \
(all listed competitors are clearly relevant, real-sounding, and appropriately matched to \
the stated market and company). Respond ONLY with a JSON object: \
{"score": <1-5 integer>, "questionable_competitors": [<names, if any, that seem irrelevant \
or implausible>], "rationale": "<one or two sentences>"}"""


def judge_faithfulness(brief_text: str, pass_threshold: int = 4) -> dict:
    user_prompt = f"BRIEF TO REVIEW:\n\n{brief_text}"
    result = _call_judge(FAITHFULNESS_SYSTEM_PROMPT, user_prompt)
    score = int(result.get("score", 0))
    return {
        "passed": score >= pass_threshold,
        "score": score / 5.0,
        "details": result,
    }


def judge_competitor_relevance(
    brief_text: str, market: str, company_description: str, pass_threshold: int = 4
) -> dict:
    user_prompt = (
        f"TARGET MARKET: {market}\n"
        f"COMPANY: {company_description}\n\n"
        f"BRIEF TO REVIEW:\n\n{brief_text}"
    )
    result = _call_judge(COMPETITOR_RELEVANCE_SYSTEM_PROMPT, user_prompt)
    score = int(result.get("score", 0))
    return {
        "passed": score >= pass_threshold,
        "score": score / 5.0,
        "details": result,
    }


if __name__ == "__main__":
    import sys
    from evaluators import extract_brief_text

    path = sys.argv[1] if len(sys.argv) > 1 else "sample_brief_hp01.txt"
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    text = extract_brief_text(raw)

    print("=== Faithfulness (citation-claim alignment) ===")
    print(json.dumps(judge_faithfulness(text), indent=2))

    print("\n=== Competitor relevance ===")
    market = sys.argv[2] if len(sys.argv) > 2 else "UK marriage counselling market"
    company = sys.argv[3] if len(sys.argv) > 3 else "Togethr: a relationship-navigation platform."
    print(json.dumps(judge_competitor_relevance(text, market, company), indent=2))
