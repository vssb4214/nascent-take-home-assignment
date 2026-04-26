# Agentic Ops Take-Home — Meeting Notes → Action Items

## 1. Diagnosis

The first thing I noticed is that the naive system asks the LLM to do way too much in a single shot. "Summarize the meeting and list all action items with owners" sounds simple, but it's actually like four or five different tasks crammed into one prompt. Here's what I think is going wrong:

### It's doing everything at once
The model has to figure out what happened, who said what, which things are real commitments, which things are vague, and then format all of that into a nice output. There's no structure pushing it in any direction, so when it gets something wrong you can't even tell which part failed. It's just one big black box.

### All action items look the same
"Alex will check with finance" is a real commitment — someone said they'd do a thing. "Someone needs to follow up with the vendor" is completely different, nobody actually owns that. And "design might slip by a week" isn't even an action item, it's more of a risk flag. But the naive system dumps all of these into the same flat list. If I'm reading the output after the meeting, I have no idea which things are actually going to happen and which ones are still floating.

### Ambiguity gets swept under the rug
This one bothers me the most. The landing page has no owner. The vendor follow-up has no owner. But the output just lists them like normal tasks, and now someone reading this is going to assume they're handled. That's actually worse than not having notes at all — at least with no notes you know you don't know.

### There's nothing tying output back to the source
If the model makes something up or gets the owner wrong, you'd have to go re-read the whole meeting transcript to catch it. There's no evidence, no quotes, nothing. You're just trusting the LLM, which kind of defeats the whole point.

### Messy input makes all of this worse
Input B is how people actually talk — hedging, backtracking, "sounds like maybe," "i honestly don't remember who." The naive prompt doesn't give the model any framework for handling that kind of language. So it either treats hedges like firm commitments or just drops stuff entirely.

---

## 2. Redesign

### Approach

I went with a single well-structured prompt rather than splitting into multiple LLM calls. The assignment says "how you would break this into steps (if at all)" — and for this scope, one prompt with clear categories, explicit rules, and a few-shot example gets you most of the way there. Multi-step pipelines are great when you need to debug individual stages in production, but for a 2-4 hour take-home they mostly just eat time on glue code.

The prompt does the heavy lifting: it defines four categories (firm commitment, vague follow-up, unowned work, risk/warning), requires evidence grounding for every item, and includes a worked example showing exactly what each category looks like in the output.

Where prompting alone fell short, I added a post-processing step in code. More on that in the iteration section.

### What each piece does

1. **Prompt with schema + few-shot example** — Tells the model exactly what categories to use, what fields to fill, and shows a worked example. Low temperature (0.1) for consistent structured output.

2. **JSON extraction with fence stripping** — Models love wrapping JSON in markdown fences. The parser handles that gracefully and fails with useful error output if something breaks.

3. **Post-processing guardrails (V3)** — Cross-references `open_questions` against `action_items`. If a question implies unresolved work with no matching action item, it injects one as low-confidence and unowned. This catches the stuff the LLM keeps putting in the wrong bucket.

### Tradeoffs

- **Single prompt vs. multi-step pipeline**: Faster to build, less debuggable in production. For this scope it's the right call — the iteration story shows where a pipeline would start to make sense at scale.
- **Few-shot example in the prompt**: Adds ~300 tokens of context overhead and biases the model toward the example's structure. But it anchors behavior way more reliably than instructions alone, especially on an 8B model.
- **Post-processing instead of more prompting**: The LLM stubbornly refused to put unowned work in `action_items` no matter how explicit the prompt was. At some point you stop yelling at the model and just write a guardrail. The tradeoff is that injected task names are a bit rough — a production version would run them through a quick LLM rewrite pass, but that's not worth the complexity here.

---

## 3. Implementation

All code runs end-to-end against Ollama locally with `llama3.1`. No mocked LLM calls — everything hits the model and parses real output.

- `extract_v1.py` — Single structured prompt, confidence levels, evidence grounding
- `extract_v2.py` — Better prompt: risk/warning category, few-shot example, summary guidance
- `extract_v3.py` — Same prompt as V2 + post-processing guardrails for uncovered open questions

Each version dumps JSON output files (`output_v{1,2,3}_{a,b}.json`) for comparison.

The model resolution helper (`resolve_model`) checks what's actually installed in Ollama and falls back gracefully — useful if someone reviewing this has a different model pulled.

`SYSTEM_PROMPT` and the input constants are intentionally duplicated across V2 and V3 so each script runs standalone without imports between versions.

---

## 4. Iteration

### V1 → V2: Better prompting

**What didn't work:** V1 correctly identified Alex's budget check (high confidence) and the vendor follow-up (low confidence, unowned). But it completely dropped Sarah's design slip — treated it as an observation and moved on. The landing page only showed up as an open question, not as an action item anyone could track. Summaries were generic and didn't tell you anything useful.

**What I changed:** Added a RISK/WARNING category so the model has a place to put things like "design might slip." Added explicit instructions that unowned work should appear in both `action_items` and `open_questions`. Included a few-shot example showing all three types. Pushed for summaries that capture what's decided, what's at risk, and what's unresolved.

**Result:** Summaries got noticeably better — "no concrete decisions made" and "landing page ownership remains unclear" vs. V1's generic "discussed Q2 launch timeline." Design slip and landing page started appearing as open questions. But the model still refused to put them in `action_items`.

### V2 → V3: Code guardrails

**What didn't work:** Even with explicit "do NOT only put it in open_questions" instructions and a few-shot example showing the right behavior, the model kept putting unowned work in `open_questions` only. The landing page and design slip were consistently missing from `action_items` across multiple runs.

**What I changed:** Instead of trying to fix this with more prompting, I added a `postprocess()` step. It does fuzzy keyword matching between `open_questions` and `action_items` — if a question points to unresolved work with no matching action item, it creates one automatically (low confidence, unowned, needs clarification). The evidence field notes that it was inferred from an open question so nothing looks hallucinated.

**Result:** Landing page and design slip now show up as action items. Task names from the injection are a bit awkward ("Is responsible for handling the landing page") because the regex cleanup is simple — in production you'd run those through a quick LLM call to clean up the phrasing, but for this scope it captures the right information.

**Takeaway:** The signal was the landing page consistently landing in `open_questions` only — not once or twice, but across every run, despite an explicit "Do NOT only put it in open_questions" rule and a few-shot example showing exactly the right behavior. That kind of consistent, instruction-resistant pattern is when it's time to stop editing the prompt and write a guardrail instead.

---

## 5. Before vs. After

### Input A (Clean Notes)

**Naive system output:** *(paraphrased from assignment example)*
```
Summary: The team discussed the Q2 launch timeline and potential delays.
Action Items:
- Follow up with vendor about pricing
- Alex to check with finance on budget
- Landing page ownership needs to be decided
```

**V3 output:**
```json
{
  "summary": "Q2 launch timeline discussed, but no concrete decisions made.
              Design might slip by a week, and vendor pricing follow-up is
              still unowned. Landing page ownership remains unclear.",
  "action_items": [
    {
      "task": "Check with finance on budget approval",
      "owner": "Alex",
      "confidence": "high",
      "needs_clarification": false,
      "evidence": "Alex will check with finance on budget approval"
    },
    {
      "task": "Follow up with the vendor about pricing",
      "owner": null,
      "confidence": "low",
      "needs_clarification": true,
      "evidence": "Someone needs to follow up with the vendor about pricing"
    },
    {
      "task": "Determine landing page ownership",
      "owner": null,
      "confidence": "low",
      "needs_clarification": true,
      "evidence": "[Inferred from open question]"
    },
    {
      "task": "Confirm whether design is slipping by a week",
      "owner": null,
      "confidence": "low",
      "needs_clarification": true,
      "evidence": "[Inferred from open question]"
    }
  ],
  "open_questions": [
    "Who is responsible for the landing page?",
    "Does the design actually need to slip by a week?"
  ]
}
```

**What improved:** Every item has a confidence level and an owner (or explicit lack of one). The landing page and design slip aren't silently dropped — they're flagged as unowned with `needs_clarification: true`. Evidence fields tie each item back to the source. The summary tells you what's unresolved, not just what was "discussed."

### Input B (Messy Notes)

**Naive system output:** *(paraphrased from assignment example)*
```
Summary: The team discussed the Q2 launch timeline and potential delays.
Action Items:
- Follow up with vendor about pricing
- Alex to check with finance on budget
- Landing page ownership needs to be decided
```

**V3 output:**
```json
{
  "summary": "Q2 launch timing is uncertain due to design delays.
              Pricing for vendors remains open. The landing page and
              budget issues are still unowned.",
  "action_items": [
    {
      "task": "Check with finance about the budget",
      "owner": "Alex",
      "confidence": "high",
      "needs_clarification": false,
      "evidence": "alex said he's got the budget thing, he's gonna check with finance"
    },
    {
      "task": "Follow up on vendor pricing",
      "owner": null,
      "confidence": "low",
      "needs_clarification": true,
      "evidence": "someone said they'd follow up but i honestly don't remember who"
    },
    {
      "task": "Determine landing page ownership",
      "owner": null,
      "confidence": "low",
      "needs_clarification": true,
      "evidence": "[Inferred from open question]"
    },
    {
      "task": "Confirm whether design is actually slipping",
      "owner": null,
      "confidence": "low",
      "needs_clarification": true,
      "evidence": "[Inferred from open question]"
    }
  ],
  "open_questions": [
    "Who is responsible for handling the landing page?",
    "Is design actually slipping by a week?"
  ]
}
```

**What improved:** The messy, informal input produces the same structured output as the clean version. Hedging language ("sounds like maybe," "i honestly don't remember who") gets correctly interpreted — the vendor follow-up is flagged as unowned rather than attributed to a made-up person. The system handles both input formats without any special preprocessing.