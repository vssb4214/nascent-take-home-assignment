# extract_v2.py
# Second pass — prompt-level fixes for the stuff V1 got wrong:
#   - added risk/warning as a category (sarah's design slip was getting dropped)
#   - told the model that unowned work is still an action item, not just an open question
#   - added a few-shot example to anchor behavior
#   - pushed for summaries that actually tell you something useful

import json
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.1:latest"

SYSTEM_PROMPT = """You are a meeting notes analyzer. Your job is to read meeting notes and produce structured JSON that a team can act on without re-reading the original notes.

CATEGORIES — every extractable item falls into one of these:
1. FIRM COMMITMENT: Someone explicitly said they will do a specific thing. (confidence: "high")
2. VAGUE FOLLOW-UP: Something needs to happen and someone loosely volunteered, but it's not a clear commitment. (confidence: "medium")
3. UNOWNED WORK: Something clearly needs to happen but nobody claimed it. This is STILL an action item — set owner to null, confidence to "low", and needs_clarification to true. Do NOT only put it in open_questions.
4. RISK/WARNING: Someone flagged a potential problem or delay. This is an action item too — the task is to confirm or address the risk. If no one owns the follow-up, treat it as unowned.

RULES:
- Every item MUST include an "evidence" field with the exact quote or close paraphrase from the notes.
- If something is unowned, it appears as BOTH an action_item AND in open_questions.
- Risks and warnings are action items, not just observations. Someone needs to confirm or address them.
- The summary should be 2-3 sentences that capture: what was decided, what's at risk, and what's still unresolved. A good summary means someone who skipped the meeting knows exactly where things stand.

EXAMPLE:

Meeting Notes:
- Jake said he'll send the proposal to the client by Thursday
- Maria mentioned the API might have rate limiting issues but hasn't confirmed
- We need someone to update the docs before release

JSON Output:
{
  "summary": "Jake committed to sending the client proposal by Thursday. Maria flagged potential API rate limiting issues but hasn't confirmed yet. Documentation updates before release are still unowned.",
  "action_items": [
    {
      "task": "Send the proposal to the client by Thursday",
      "owner": "Jake",
      "confidence": "high",
      "needs_clarification": false,
      "evidence": "Jake said he'll send the proposal to the client by Thursday"
    },
    {
      "task": "Confirm whether the API has rate limiting issues",
      "owner": "Maria",
      "confidence": "medium",
      "needs_clarification": true,
      "evidence": "Maria mentioned the API might have rate limiting issues but hasn't confirmed"
    },
    {
      "task": "Update the docs before release",
      "owner": null,
      "confidence": "low",
      "needs_clarification": true,
      "evidence": "We need someone to update the docs before release"
    }
  ],
  "open_questions": [
    "Who is responsible for updating the docs before release?",
    "Does the API actually have rate limiting issues?"
  ]
}

Now analyze the following meeting notes. Respond with ONLY valid JSON, no other text."""

# same test inputs

INPUT_A = """- We talked about the Q2 launch timeline
- Sarah mentioned design might slip by a week
- Someone needs to follow up with the vendor about pricing
- Alex will check with finance on budget approval
- Not sure who is owning the landing page yet"""

INPUT_B = """ok so the main thing was Q2 launch timing. sarah brought up that
design is behind, sounds like maybe a week? she didn't say it's
definitely slipping but it felt like a heads up. we talked about
the vendor situation for a while — pricing is still open and
someone said they'd follow up but i honestly don't remember who.
alex said he's got the budget thing, he's gonna check with
finance. oh and the landing page came up again, i think everyone
assumed someone else was handling it. nobody actually said "i'll
do it" though."""


def resolve_model(preferred: str) -> str:
    """Check what's actually installed in ollama and fall back if needed."""
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=10)
        resp.raise_for_status()
        installed = [m["name"] for m in resp.json().get("models", []) if m.get("name")]
    except requests.RequestException:
        return preferred

    if preferred in installed:
        return preferred

    base = preferred.split(":")[0]
    for name in installed:
        if name.split(":")[0] == base:
            return name

    return installed[0] if installed else preferred


def extract_action_items(notes: str) -> dict:
    """Send notes to ollama, parse and return structured JSON."""
    prompt = f"""{SYSTEM_PROMPT}

Meeting Notes:
{notes}

JSON Output:"""

    resp = requests.post(OLLAMA_URL, json={
        "model": resolve_model(MODEL),
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    })
    resp.raise_for_status()
    raw = resp.json()["response"].strip()

    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"JSON parse failed: {e}")
        print(f"Raw output:\n{raw}")
        return {"error": "parse_failed", "raw": raw}


def print_result(label: str, result: dict):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")

    if "error" in result:
        print(f"Error: {result['error']}")
        print(f"Raw: {result.get('raw', 'N/A')}")
        return

    print(f"\nSummary:\n  {result.get('summary', 'N/A')}")
    print(f"\nAction Items:")

    for i, item in enumerate(result.get("action_items", []), 1):
        owner = item.get("owner") or "UNOWNED"
        conf = item.get("confidence", "?")
        flag = " [NEEDS CLARIFICATION]" if item.get("needs_clarification") else ""
        print(f"\n  {i}. {item.get('task', 'N/A')}")
        print(f"     Owner: {owner} | Confidence: {conf}{flag}")
        print(f"     Evidence: \"{item.get('evidence', 'N/A')}\"")

    open_qs = result.get("open_questions", [])
    if open_qs:
        print(f"\nOpen Questions:")
        for q in open_qs:
            print(f"  - {q}")


def main():
    print("Running V2...\n")

    for label, notes in [("INPUT A (Clean)", INPUT_A), ("INPUT B (Messy)", INPUT_B)]:
        print(f"Processing {label}...")
        result = extract_action_items(notes)
        print_result(label, result)

        tag = "a" if "Clean" in label else "b"
        with open(f"output_v2_{tag}.json", "w") as f:
            json.dump(result, f, indent=2)

    print("\n\nDone.")


if __name__ == "__main__":
    main()