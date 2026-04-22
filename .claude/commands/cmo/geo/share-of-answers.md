# Skill: /cmo/geo/share-of-answers

Run a prompt set against ChatGPT, Claude, Gemini, and Perplexity. Detect citations of the user's brand (and competitors). Output a trend-able CSV + exec-readable summary report.

This is the foundational measurement skill — Stage 1 of the measurement maturity ladder (Framework 03). Every other GEO skill assumes this baseline exists.

**Two performance goals reported separately in every output:**
- **Goal A — Mentions:** % of answers where brand is cited across the full prompt set (share of voice / brand awareness)
- **Goal B — Shopping-intent share:** % of answers where brand is cited on `shopping`-intent prompts (best-of, vs/alternatives, pricing, reviews, integrations) — the direct pipeline metric for B2B SaaS

**Intent vocabulary (LOCKED — shared with `/cmo/geo/prompt-set-builder`):**
`shopping | comparative | informational | decision | recommendation`

## When to use

- Establishing a GEO baseline for a new client
- Weekly / monthly recurring measurement
- Validating whether a content rework moved citations (treated vs. control)
- Pre/post analysis for any GEO tactic
- Competitive monitoring of share against a fixed peer set

## Inputs (asked at intake)

| Input | Required? | Source / default |
|---|---|---|
| Prompt set CSV | Yes | Output of `/cmo/geo/prompt-set-builder`, or any CSV matching the locked schema |
| Brands CSV (primary + competitors) | Yes | User provides (or skill generates a template via `--init-brands`) |
| Client identifier (for output path) | Yes | User |
| Surfaces to query | No | All 4 (anthropic, openai, google, perplexity) |
| Runs per prompt | No | 3 (handles AI response stochasticity) |
| Citation classifier mode | Yes — **ASK** | A: positional heuristic (default, fast/free) **or** B: LLM-as-judge (slower, ~$0.50/100 rows, ~95% accurate) |
| Cost ceiling (USD) | No | $10 |

## Workflow

### 1. Intake

Confirm the 4 inputs above. Then **explicitly ask**:

> Citation classifier — pick one:
> - **(A) Positional heuristic** — fast, free, ~80% accurate. Brand is "primary" if cited in the first paragraph or first 3 list items.
> - **(B) LLM-as-judge** — slower, ~$0.50 / 100 rows, ~95% accurate. Claude Haiku reads each response and classifies primary/secondary/none.

Default to A unless the user picks B. Note the choice in the run log.

### 2. Pre-flight cost estimate

Run the tool with intake values. The tool prints an estimated cost breakdown by surface and a total. The tool aborts if the estimate exceeds `--max-cost`. If under the ceiling, the tool asks for confirmation before hitting any paid API.

### 3. Run

Tool fires calls in parallel across the 4 surfaces (sequential within each surface to respect per-provider rate limits). Web search is enabled on all 4 providers — without it the measurement isn't meaningful. Each prompt is run N times per surface (default 3).

### 4. Output

Tool writes 3 files to the output directory:
1. `runs.csv` — one row per (prompt × surface × run), with citation status, position, and competitor citations
2. `summary.md` — exec-readable Goal A + Goal B TL;DR, intent-class breakout, competitive table, win/lose lists, surface gaps, and the required gating warnings
3. `trends.csv` — append-only one-row-per-run-date with per-surface and overall shares (both total and shopping-intent only) for week-over-week trending

### 5. Surface the summary

Read `summary.md` and post the **Goal A** and **Goal B** TL;DR tables inline in chat. Don't summarize the gating warnings — they exist precisely so they're read in full when the report is opened.

## Outputs

### Storage

- Client work: `clients/<client>/geo/share-of-answers/<YYYY-MM-DD>/`
- MultiplAI / personal: `brands/multiplai/geo/share-of-answers/<YYYY-MM-DD>/`

### File schemas

**`runs.csv`** — one row per (prompt × surface × run):
```
run_id, timestamp, prompt_id, intent_type, ai_surface, run_number,
response_text, citation_urls, brand_cited, brand_position, competitor_citations
```
- `intent_type` — propagated from the prompt CSV (locked vocab); required so Goal A vs. Goal B can be split
- `brand_cited` — `none | secondary | primary | error`
- `brand_position` — 1-N if cited (where the brand first appears in the response)
- `competitor_citations` — pipe-separated list

**`brands.csv`** (input):
```
role,name,aliases,domain
primary,Monte Carlo,"Monte Carlo Data|MonteCarlo.io",montecarlodata.com
competitor,Datadog,,datadoghq.com
competitor,Bigeye,,bigeye.com
```
- `role` — `primary` (exactly one row) or `competitor` (any number)
- `aliases` — pipe-separated alternates; matched after normalization (lowercase, punctuation/whitespace stripped, common TLDs dropped)
- `domain` — bare domain (no scheme, no path)

**`trends.csv`** — append-only:
```
run_date, anthropic_share, anthropic_shopping_share, openai_share, openai_shopping_share,
google_share, google_shopping_share, perplexity_share, perplexity_shopping_share,
overall_share, overall_shopping_share
```

## Acceptance criteria for "done"

- [ ] User has a valid prompts CSV (Skill #1 output, or hand-built matching the schema)
- [ ] User has a valid brands.csv (or has run `--init-brands` to scaffold one)
- [ ] All 4 API keys present in `.env`: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `PERPLEXITY_API_KEY`
- [ ] Citation classifier choice (A or B) explicitly captured at intake
- [ ] Cost preflight shown and confirmed before paid API calls fire
- [ ] All 3 outputs written: `runs.csv`, `summary.md`, `trends.csv`
- [ ] `summary.md` Goal A + Goal B tables surfaced inline in chat
- [ ] Run log mentions: surfaces queried, runs/prompt, classifier mode, total elapsed, total cost (estimated)

## Implementation notes

### Companion tool: YES — `tools/geo_share_of_answers.py`

Skill is a thin orchestration layer; tool does all heavy lifting (API calls, citation parsing, CSV/MD generation).

### Provider models (defaults — overridable via `--<provider>-model`)

| Surface | Model | Web search method |
|---|---|---|
| Anthropic | `claude-sonnet-4-5` | `web_search_20250305` tool, max 3 uses/call |
| OpenAI | `gpt-4o` | Responses API + `web_search` tool |
| Google | `gemini-2.5-flash` | `google_search` grounding |
| Perplexity | `sonar-pro` | built into the model |

### Citation parsing — provider-specific

| Surface | Where citations live |
|---|---|
| Anthropic | `web_search_tool_result` blocks → each result has `.url` |
| OpenAI | message annotations → `annotation.url` (we strip query strings — OpenAI appends `?utm_source=openai`) |
| Google | grounding_metadata → `chunk.web.title` is the source domain (not `.uri` — that's a Vertex redirect) |
| Perplexity | top-level `citations` or `search_results` array on the response JSON |

### Brand fuzzy matching

Normalization: lowercase → strip TLDs (`.com`, `.io`, `.ai`, `.co`, `.net`, `.org`, `.app`, `.dev`, `.so`, `.inc`) → strip non-alphanumerics. Brand "Monte Carlo" matches `monte carlo`, `MonteCarlo`, `monte-carlo`, `montecarlo.com`. Aliases extend this set explicitly when normalization isn't enough.

### Primary vs. secondary heuristic (option A)

Brand is **primary** if any of:
1. Cited within first 600 characters of the response
2. Appears in any of the first 3 list items (lines starting with `*`, `-`, digit+`.`, or digit+`)`)
3. Is the first cited domain in `citation_urls`

Else **secondary** if cited anywhere; else **none**.

### LLM-as-judge (option B)

Each response sent to `claude-haiku-4-5-20251001` with a strict JSON-output system prompt. Falls back to positional heuristic on parse error or API failure.

### Concurrency model

ThreadPoolExecutor with `max_workers = len(surfaces)` (default 4). Each provider runs all its prompts × runs sequentially in its own thread (respects per-provider rate limits). Default 0.5s sleep between calls within a provider — overridable with `--sleep-between`.

### Cost preflight

Per-call rough estimate: 200 input + 800 output tokens × pricing per provider, plus a flat per-call web-search surcharge for providers that bill it separately. Preflight prints the breakdown by surface, the total, and the call count. Aborts if total > `--max-cost`. Asks for confirmation otherwise (unless `--no-confirm`).

### Error handling

Per the spec: one failed AI doesn't kill the run. Each provider call is wrapped — failures emit `[ERROR]` in `response_text`, `brand_cited="error"`, and the row still appears in `runs.csv` so failures are visible in the data, not silently dropped.

## Required gating language

Every `summary.md` ends with the 5 fake-case-study warnings (Framework 03) and the SEO/GEO investment gate (Framework 04). These are not optional — they exist to discipline how the data is interpreted. Don't strip them, don't summarize them when surfacing the report inline.

## CLI cheat sheet

```bash
# Generate brands template
python3 tools/geo_share_of_answers.py --init-brands clients/acme/geo/brands.csv

# Quick test (5 prompts, 1 run, no confirmation)
python3 tools/geo_share_of_answers.py \
    --prompts research/geo-aeo/prompt-sets/data-observability_template.csv \
    --brands  clients/acme/geo/brands.csv \
    --output  .tmp/geo/test/ \
    --limit 5 --runs-per-prompt 1 --no-confirm

# Production baseline (full set, 3 runs, confirmation gate)
python3 tools/geo_share_of_answers.py \
    --prompts clients/acme/geo/prompts.csv \
    --brands  clients/acme/geo/brands.csv \
    --output  clients/acme/geo/share-of-answers/2026-04-16/ \
    --runs-per-prompt 3

# Use LLM-as-judge instead of positional heuristic
python3 tools/geo_share_of_answers.py ... --judge

# Skip a surface (e.g. if a key is rate-limited)
python3 tools/geo_share_of_answers.py ... --surfaces anthropic,google,perplexity
```

## Out of scope (deferred to V2)

- Automated scheduled runs — wrap with launchd once weekly cadence is proven manually
- Sentiment analysis on citations (positive vs. negative mention)
- Web UI / dashboard
- Historical re-running for trend backfill (runs are forward-only by design)
- Citation screenshot capture for client deliverables

## Open questions

- **Cross-surface weighting in a single SoA number** — should ChatGPT count more than Claude (usage volume)? Current report treats all surfaces equally; flag if exec asks for a weighted aggregate.
- **AI Mode (Google) coverage gap** — `gemini-2.5-flash` API is a proxy for what users see in Google AI Mode but not identical. Document in summary if Google numbers diverge wildly from other surfaces.
- **Perplexity API stability** — newer API; document any model deprecation notices in `_build-plan.md` so the suite stays current.

## References

- Spec: `research/geo-aeo/skills/01_share-of-answers.md`
- Framework 03 (Measurement): `research/geo-aeo/frameworks/03_measurement-framework.md`
- Framework 04 (SEO/GEO Integration): `research/geo-aeo/frameworks/04_seo-geo-integration.md`
- Tool: `tools/geo_share_of_answers.py`
- Upstream skill: `/cmo/geo/prompt-set-builder` → produces the prompt CSV input
