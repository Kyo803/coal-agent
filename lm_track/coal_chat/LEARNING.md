# Coal — Independent Learning & Curiosity (Phase 2)

Coal now learns on its own. It is **not told what to study**: an intrinsic
drive (dopamine) picks topics from a curiosity graph, discovers its own
sources, ingests them, forms questions, rehearses (self-quiz), synthesizes
its own understanding, and tracks mastery + mood over time.

## Package

```
learning/
  paths.py          ~/.coal/learning persistence (json/jsonl)
  llm.py            small-model calls (Ollama coaln-3b; guarded/offline-safe)
  embed.py          safe RAG/embedder access (Ollama else tfidf, no ST download)
  guardrails.py     scheme/robots/rate/content gate + source trust scoring
  sources.py        discovers Wikipedia / arXiv / Gutenberg / GitHub material
  ingest.py         fetch -> chunk -> embed (shared RAG) + notes
  notes.py          durable source-tagged notes (notes.jsonl)
  planner.py        topic -> subtopics + questions
  assess.py         coverage / mastery / gaps
  rehearse.py       active recall + self-scoring
  synthesize.py     distils notes into its own understanding
  curriculum.py     prerequisite ordering
  loop.py           the learning cycle + seeding + stats
  curiosity/
    graph.py        topics, mastery, edges, frontier (curiosity.json)
    drive.py        intrinsic reward = novelty + proximity + competence + interest + surprise
    mood.py         eagerness/boredom state (mood.json)
    questions.py    self-question generation (LLM + fallback templates)
    tension.py      contradictions + surprise (the "itch")
    plans.py        short/mid/long horizons (plan.json)
```

State lives under `~/.coal/learning/` (`curiosity.json`, `mood.json`,
`plan.json`, `notes.jsonl`, `journal.jsonl`, `rate.json`). Learned material
is ingested into the **same RAG index** the chat uses, so it is immediately
answerable via `search_docs`.

## Cycle (`learning.loop.cycle`)

1. **pick** a topic from the frontier (`drive.rank` + `mood`)
2. **plan** it (subtopics + questions) with the small model
3. **discover** sources (Wikipedia/arXiv/GitHub) and **ingest** → RAG + notes
4. **rehearse** — answer its own questions from learned context; self-score
5. **synthesize** a distilled, structured understanding
6. **update** mastery + open subtopics in the graph; compute **surprise**
7. **mood** updates (excitement/boredom/urge) and journal the cycle

## Tools (category `learning`)

`learn_cycle`, `learn_topic`, `learn_stats`, `learn_report`, `learn_url`,
`learn_ask` — registered in `tools/specs.py`; enabled in permissions; the
`learning` trigger fires on "curiosity / teach yourself / research / study".

## CLI

```
python coal.py --learn-stats                 # print graph + mood + plan
python coal.py --learn                        # one autonomous cycle
python coal.py --learn "hash tables"          # force a topic
python coal.py --learn "x" --no-network       # offline (no web sources)
```

## Config (`config.json` -> `learning`)

`model` (coaln-3b), `ollama_url`, `num_ctx`, `allow_network`,
`source_kinds` (encyclopedia/paper/repo), `idle_cycles`, `night_cycles`,
`max_pages_per_cycle`, `seed_topics`.

## Guardrails

http/https only; `robots.txt` honoured; per-host rate limiting; blocked
domains (piracy/adult/malware) and terms; source trust scoring. Short
currents are explicit: it cannot study illicit content.

## Safety / offline behavior

- If Ollama is down, everything falls back to heuristics + a tfidf
  embedder, so cycles never hang. (`COAL_LEARN_NO_LLM=1` forces offline.)
- Network failures just yield zero sources; the drive moves on.

## Verified

`test_learning.py` — 25 checks (graph, mood, drive, planner, cycle,
assess, curriculum, guardrails) all pass. Live: an online cycle for
"binary search tree" discovered 2 sources, ingested 3 chunks, raised
mastery and mood; content was searchable via RAG.

## Still to come (Phase 6)

Wiring the cycle into an always-on idle/night scheduler (so it truly runs
*unprompted*) lives in `governance/` (Phase 6).
