# extract_v1.py
# First pass — single structured prompt with confidence levels, ownership
# attribution, and evidence grounding. No category for risks or warnings yet.

import json
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.1:latest"

SYSTEM_PROMPT = """You are a meeting notes analyzer. Your job is to read meeting notes and produce a structured JSON output that distinguishes between firm commitments, vague follow-ups, and unresolved items.

Rules:
- Only extract things that require someone to DO something. Observations and status updates are not action items.
- If someone explicitly said they would do something, that's a FIRM commitment (confidence: "high").
- If something needs to happen but no one clearly volunteered, that's UNOWNED (confidence: "low", owner: null).
- If someone vaguely suggested they might do something or it's unclear, that's VAGUE (confidence: "medium").
- Always include the exact quote or paraphrase from the notes that supports each item in the "evidence" field.
- If an item has no clear owner, set "needs_clarification" to true.
- Capture anything unresolved or unclear in "open_questions".

Respond with ONLY valid JSON matching this exact schema, no other text:

{
  "summary": "2-3 sentence summary of what was discussed and decided",
  "action_items": [
    {
      "task": "clear description of what needs to be done",
      "owner": "person's name or null if unowned",
      "confidence": "high | medium | low",
      "needs_clarification": true/false,
      "evidence": "exact quote or close paraphrase from the notes"
    }
  ],
  "open_questions": [
    "anything that was raised but not resolved"
  ]
}"""


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


def resolve_model(preferred_model: str) -> str:
    """Pick a locally installed model if the preferred one is unavailable."""
    try:
        tags_response = requests.get("http://localhost:11434/api/tags", timeout=10)
        tags_response.raise_for_status()
        installed_models = [
            item.get("name", "")
            for item in tags_response.json().get("models", [])
            if item.get("name")
        ]
    except requests.RequestException:
        # Fall back to the configured model if we cannot inspect local tags.
        return preferred_model

    if preferred_model in installed_models:
        return preferred_model

    # Prefer the same base model if available under a different tag.
    base_name = preferred_model.split(":", 1)[0]
    for candidate in installed_models:
        if candidate.split(":", 1)[0] == base_name:
            return candidate

    # Otherwise use the first installed model.
    if installed_models:
        return installed_models[0]

    return preferred_model


def extract_action_items(meeting_notes: str) -> dict:
    """Send meeting notes to the LLM and parse structured output."""

    prompt = f"""{SYSTEM_PROMPT}

Meeting Notes:
{meeting_notes}

JSON Output:"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": resolve_model(MODEL),
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # low temp for consistent structured output
            },
        },
    )
    response.raise_for_status()

    raw = response.json()["response"].strip()

    # try to extract JSON if the model wraps it in markdown fences
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON: {e}")
        print(f"Raw response:\n{raw}")
        return {"error": "Failed to parse", "raw": raw}


def print_result(label: str, result: dict):
    """Pretty-print the structured output."""
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
        clarify = " [NEEDS CLARIFICATION]" if item.get("needs_clarification") else ""
        print(f"\n  {i}. {item.get('task', 'N/A')}")
        print(f"     Owner: {owner} | Confidence: {conf}{clarify}")
        print(f"     Evidence: \"{item.get('evidence', 'N/A')}\"")

    open_qs = result.get("open_questions", [])
    if open_qs:
        print(f"\nOpen Questions:")
        for q in open_qs:
            print(f"  - {q}")


def main():
    print("Running V1 extraction...\n")

    print("Processing Input A (Clean)...")
    result_a = extract_action_items(INPUT_A)
    print_result("INPUT A — Clean Notes", result_a)

    # save raw JSON for comparison later
    with open("output_v1_a.json", "w") as f:
        json.dump(result_a, f, indent=2)

    print("\n\nProcessing Input B (Messy)...")
    result_b = extract_action_items(INPUT_B)
    print_result("INPUT B — Messy Notes", result_b)

    with open("output_v1_b.json", "w") as f:
        json.dump(result_b, f, indent=2)

    print("\n\nDone. Outputs saved to output_v1_a.json and output_v1_b.json")


if __name__ == "__main__":
    main()
