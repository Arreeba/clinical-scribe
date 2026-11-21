Frozen on 2026-11-10 before the held-out run (scripts 5 and 9).
Whisper: small model, no medicine hint, language en.
Agent: FDA-derived vocabulary (data/drug_list.json), min_score 0.65, top_k 3,
       confirmed fixes reapplied automatically (auto_apply_confirmed = true).
Notes: Groq openai/gpt-oss-120b, temperature 0, reasoning_effort low,
       strict JSON schema, prompt and checks as in frozen/note_generation.py
       and frozen/note_pipeline.py.
Dev result: 57 of 58 checklist facts, 0 invented statements, 0 false flags.
Before the held-out run: copy frozen/corrections.json back over
data/corrections.json, and run the agent in "test" mode (applies saved
fixes only).