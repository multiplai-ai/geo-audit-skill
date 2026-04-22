# GEO/AEO Skill Suite — `/cmo/geo/`

Six production skills + one deferred spec that together handle the end-to-end GEO (Generative Engine Optimization) / AEO (Answer Engine Optimization) workflow for a B2B SaaS client: build the prompt set, measure current share of answers, audit the site, plan the work with a revenue case, map the citation network, and restructure the priority pages.

**Default scope:** B2B SaaS companies selling to mid-market and enterprise buyers.

**Two performance goals tracked across the suite:**
- **Goal A — Mentions:** brand citation rate in generative engine answers (share of voice)
- **Goal B — Shopping-intent share:** brand citations on shopping-intent prompts (pipeline metric)

## The 6 live skills (+ 1 reshaped)

| # | Skill | What it does | Needs |
|---|---|---|---|
| 1 | [`/cmo/geo/prompt-set-builder`](prompt-set-builder.md) | Generate a 50-prompt test set across shopping / comparative / informational / decision / recommendation intent for a vertical | Vertical label, brand CSV, optional keyword CSV |
| 2 | [`/cmo/geo/share-of-answers`](share-of-answers.md) | Run the prompt set through ChatGPT + Claude + Gemini + Perplexity (web search on). Output runs.csv + per-surface share + competitive gap | Prompt set CSV, brands CSV, AI API keys |
| 3 | [`/cmo/geo/audit`](audit.md) | Stage 0 novice intake (GSC, GA4, Ahrefs, robots.txt, llms.txt, AirOps) → Stage 1 per-URL technical scoring (Framework 02 rubric) → Stage 2 unified diagnostic.md | Domain, priority URLs, intake data |
| 4 | [`/cmo/geo/plan`](plan.md) | Synthesize SoA + audit outputs into a prioritized initiative list (ICE-scored, SEO/GEO-tagged) with revenue model + eng cards + exec one-pager + Gamma deck | Audit dir + SoA dir + business inputs |
| 5 | [`/cmo/geo/citation-network-mapper`](citation-network-mapper.md) | Map which domains AI engines cite in a vertical. 3 ingestion modes (SoA runs / Profound import / fresh run). Output citation network + ranked earned-mention targets | SoA runs OR Profound CSV OR prompt set |
| 6 | _(transcript-ingest, reshaped)_ | Deferred — research-corpus ingest was deprioritized; reshaped into `/cmo/content/video-react` (content suite, tracked in Linear) | — |
| 7 | [`/cmo/geo/content-restructure`](content-restructure.md) | Rewrite a single URL or markdown page in Framework 02 structured-briefing format (front-loaded answer, Q&A H2s, entity richness, definitive openers). Voice-preserved, fact-preserved, YMYL-aware, operator-checkpoint gated | Source URL/file, voice profile path |

## Suggested invocation patterns

### New client onboarding (end-to-end)

```
/cmo/geo/prompt-set-builder    # build the 50-prompt test set for the vertical
/cmo/geo/share-of-answers      # establish Goal A + Goal B baseline (pick slice to control cost)
/cmo/geo/audit                 # pull intake data, score priority URLs, produce diagnostic.md
/cmo/geo/citation-network-mapper  # optional — map where AI cites in the vertical (reuses SoA runs, free)
/cmo/geo/plan                  # synthesize outputs → initiatives + revenue model + exec deck
```

Terminal deliverable: exec-ready plan + business case + Gamma deck. Uses ~$2-10 of API spend for a 50-prompt SoA run.

### Existing client quarterly re-audit

```
/cmo/geo/share-of-answers   # rerun the same prompt set (trend lines)
/cmo/geo/audit              # re-score priority URLs (compare to last audit)
/cmo/geo/plan               # re-plan initiatives against current deltas
```

### Single-page rework

```
/cmo/geo/audit                  # if you don't already have a baseline score for the URL
/cmo/geo/content-restructure    # operator-gated rewrite with full preservation + voice gate
```

Per-page rewrite ends with a markdown draft in `.tmp/geo/content-restructure/<slug>/`. Human review + CMS paste; no auto-publish in V1.

## Output storage conventions

- **Reusable corpus:** `research/geo-aeo/<subdir>/` (frameworks, articles, transcripts, prompt-set templates)
- **Client-specific outputs:** `clients/<client>/geo/<skill-name>/<YYYY-MM-DD>/`
- **MultiplAI / personal:** `brands/multiplai/geo/<skill-name>/<YYYY-MM-DD>/`
- **Temporary working files:** `.tmp/geo/<skill-name>/`

## Shared conventions

- Skills in `.claude/commands/cmo/geo/<name>.md`
- Companion tools in `tools/geo_<name>.py`
- All tools CLI-callable with `argparse`; errors to stderr; exit 0 success, 2 setup error, higher codes for tool-specific semantics (e.g., 10 = YMYL detected in `geo_restructure_diff.py`)
- Tools import each other as libraries where rubric consistency matters (e.g., `geo_restructure_diff.py` calls `geo_audit.audit_html()` so the rubric is single-sourced)

## Framework references

Every skill reads from the shared framework library:

- `research/geo-aeo/frameworks/01_aeo-playbook.md` — 7-step operational playbook (Ethan Smith / Aleyda Solis synthesis)
- `research/geo-aeo/frameworks/02_citation-mechanics.md` — the why-AI-cites-what research (Kevin Indig 1.2M-citation analysis, Ski Ramp, 5 content characteristics, entity density targets)
- `research/geo-aeo/frameworks/03_measurement-framework.md` — Goal A / Goal B definitions, attribution discipline, fake-case-study warnings
- `research/geo-aeo/frameworks/04_seo-geo-integration.md` — don't-break-SEO gate, 5 high-risk tactics list, SEO+/GEO+ decision matrix

## API / dependency budget

- **AI API keys required** (for skill #2 and optional LLM categorization in #5): Anthropic, OpenAI, Google, Perplexity. Keys live in `.env`.
- **Zero paid SEO tools** for V1 (no Profound, Peec.ai, ZipTie). Every skill has a clean upgrade path to those when subscribed.
- **Python deps** (via `pip install --user`): `anthropic`, `openai`, `google-genai`, `requests`, `beautifulsoup4`, `readability-lxml`, `textstat`, `tldextract`, `markdown`, `python-dotenv`.

## Build history

See `research/geo-aeo/skills/_build-plan.md` for the full per-skill build log — what was built, tested, locked-in design decisions, and V2 deferrals for each of the 7 skills.

## Not covered here (V2 candidates)

- **GEO observability dashboard** — automated weekly rollup of SoA + citation-network trends. Defer until ≥3 weeks of live data from a real client.
- **Sentiment analysis on AI citations** — being cited negatively is worse than not being cited. Additive to skill #2.
- **Schema / structured-data generator** — useful but lower frequency than the 7 above.
- **Cross-skill orchestrator (`/cmo/geo/full-program`)** — runs 1 → 2 → 3 → 5 → 4 in sequence for new-client onboarding as a single command. Skill #4 already synthesizes audit + SoA outputs, so the orchestrator is mostly handoff automation.
- **Automated publishing** — skill #7 ends with markdown drafts; CMS push (Ghost / Webflow / Contentful / Wordpress) is its own workflow.
