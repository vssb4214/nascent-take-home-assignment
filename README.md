# Meeting Notes → Action Items

Take-home assignment for Nascent's Agentic Ops internship. The goal: take a broken "meeting notes → action items" system and make it actually useful.

## How to run

Requires [Ollama](https://ollama.com) running locally and Python 3.10+.

```bash
pip install requests
ollama pull llama3.1
```

Each version runs standalone:

```bash
cd v1 && python extract_v1.py
cd v2 && python extract_v2.py
cd v3 && python extract_v3.py
```

Outputs are saved as JSON files in each version's folder.

## Walkthrough video

A quick project walkthrough is included here:

- [Watch the walkthrough (`walkthrough-demo.mp4`)](walkthrough-demo.mp4)

## What's here

```
v1/          — structured prompt with confidence levels and evidence
v2/          — better prompt: risk/warning category, few-shot example
v3/          — same prompt + post-processing guardrails
WRITEUP.md   — full analysis: diagnosis, redesign, iteration, before/after
```

See [WRITEUP.md](WRITEUP.md) for the detailed breakdown.
