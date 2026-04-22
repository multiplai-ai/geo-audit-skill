# Skill: /cmo/geo/prompt-set-builder

Generate a representative 50–200 prompt test set for measuring brand citation rate in generative engines (ChatGPT, Claude, Gemini, Perplexity). Output is a CSV that feeds directly into `/cmo/geo/share-of-answers`.

**Default scope:** B2B SaaS, mid-market→enterprise. Every prompt is tagged with one of 5 locked intent classes. The `shopping` class is enforced at ≥40% of the set so Goal B (shopping-intent share of voice) can be tracked separately from Goal A (overall mentions).

**Intent vocabulary (LOCKED — shared with `/cmo/geo/share-of-answers`):**
`shopping | comparative | informational | decision | recommendation`

## When to use

- Onboarding a new client to GEO measurement (no existing prompt set)
- Expanding a prompt set (new specialty, product line, or category)
- Refreshing after a major product or brand change
- Testing a single intent class in isolation

## Inputs (asked at intake)

| Input | Required? | Default |
|---|---|---|
| Vertical / category | Yes | — |
| ICP description (1–2 sentences) | Yes | — |
| Buyer segment | No | mid-market |
| GTM motion | No | sales-led |
| Stack context (3–5 tools the buyer runs) | No | — |
| Competitor list | No | Claude proposes 5–8; user picks 3–5 |
| Keyword CSV (GSC / Ahrefs / SEMrush export) | No | — |
| Target prompt count | No | 50 |
| Intent filter (single class) | No | all 5 |
| Shopping-intent floor | No | 40% |
| Client identifier (for output path) | Yes | — |

## Workflow

### 1. Intake

Ask the user the 11 intake questions above. Skip/default any they don't need. Do not generate anything before this step completes. If the user says "just pick sensible defaults," apply the B2B SaaS mid-market defaults and state them explicitly before generating.

### 2. Product Questions filter (Framework 01)

Before generating, assess whether the vertical surfaces products in AI answers:
- **High-visibility:** travel, commerce, B2B SaaS, devtools, HR tech → proceed
- **Mid-visibility:** healthcare, finance, legal tech → proceed, note caveat
- **Low-visibility:** news, current events, general lifestyle → **warn the user**: AEO may be the wrong tool here

Record the filter result — it goes into the generation report and the per-prompt `expected_product_visibility` column.

### 3. Competitor shortlist (if none provided)

If no competitor list provided, propose 5–8 well-known vendors in the category, wait for user to pick 3–5. Do not pick silently — vendor naming biases the entire set.

### 4. Generate prompts across the 5 locked classes

Target distribution for a 50-prompt set (tune proportionally for other counts):

| Class | Target count | Target % |
|---|---|---|
| shopping | ~22 | ~44% (≥40% floor) |
| comparative | ~8 | ~16% |
| informational | ~7 | ~14% |
| decision | ~7 | ~14% |
| recommendation | ~6 | ~12% |

**Shopping (≥40% floor — primary input to Goal B):**
- "Best [category] for [segment]"
- "[Vendor A] vs [Vendor B] vs [Vendor C]"
- "Alternatives to [Incumbent]"
- "[Category] pricing" / "How much does [category] cost for a 500-person company"
- "Best [category] that integrates with [stack tool]"
- "Top-rated [category] on G2" / "[Category] reviews for mid-market"

**Comparative:**
- "How does [X] differ from [Y]?"
- "[Category] vs [adjacent category]"

**Informational:**
- "What is [category]?" / "How does [category] work?"
- "What are the five pillars of [category]?"

**Decision:**
- "When should a company adopt [category]?"
- "Do we need [category] if we already have [adjacent tool]?"

**Recommendation:**
- "What [category] should a Series B SaaS company use?"
- "Best [category] for a 3-person data team"

**Stack context:** if provided, ensure 3+ shopping prompts include integration phrasing ("integrates with Snowflake and dbt").

**Keyword CSV:** if provided, pull the top ~20 keywords as topic seeds. Rewrite each into a conversational prompt and assign it to the most natural intent class. Don't use raw search strings — they look like SEO keywords, not AI queries.

### 5. Priority scoring

Baseline by class, then override per-prompt where justified:

| Class | Default priority |
|---|---|
| shopping | high |
| comparative | high |
| decision | medium |
| recommendation | medium |
| informational | low |

Downgrade a shopping prompt to medium if it's unlikely to surface products (e.g., esoteric stack integration). Upgrade an informational prompt to medium if it's a top-of-funnel entry point for the category.

### 6. Validate distribution

- **Hard enforce:** shopping class ≥ floor (default 40%). If short, generate more shopping prompts before export.
- **Hard enforce:** all 5 classes have ≥1 prompt.
- **Soft warn:** any non-shopping class >50% of set. Note in report but don't block (user may intentionally want a focused study).

### 7. Export

- CSV: `clients/<client>/geo/prompts/<vertical>_<YYYY-MM-DD>.csv` (or `research/geo-aeo/prompt-sets/<vertical>_template.csv` for shared templates)
- Generation report: same directory, `generation_report.md`
- Validate with the tool: `python3 tools/geo_prompt_export.py <csv_path>`. If the validator exits non-zero, fix and re-export. Do not hand a broken CSV to the user.

### 8. Surface in chat

- Distribution table (% by class)
- Product Questions filter result
- 5 sample prompts across classes
- File paths (CSV + report)
- Handoff line: "Feed this CSV into `/cmo/geo/share-of-answers` when you're ready for a baseline run."

## Output schema (CSV)

```csv
prompt_id,prompt_text,intent_type,topic,priority,expected_product_visibility,notes
P001,"Best data observability platform for enterprise data teams",shopping,category-best,high,high,"Primary buyer-intent prompt"
P002,"Monte Carlo vs Datadog vs Bigeye",shopping,vendor-comparison,high,high,"Shortlist comparison — expect product surfacing"
```

**Columns:**
- `prompt_id` — `P001`, `P002`, ... zero-padded to 3 digits
- `prompt_text` — quoted; conversational phrasing, not keyword-ese
- `intent_type` — one of `shopping | comparative | informational | decision | recommendation` (locked)
- `topic` — short slug (e.g. `category-best`, `vendor-comparison`, `integration-intent`, `category-education`, `buyer-timing`)
- `priority` — `high | medium | low`
- `expected_product_visibility` — `high | med | low` — from the Product Questions filter
- `notes` — one-line free text

**Schema lock:** first 5 columns match the input schema `/cmo/geo/share-of-answers` expects. Columns 6–7 are additive metadata; the downstream skill ignores them.

## Acceptance criteria

- [ ] Generates target prompt count ±10%
- [ ] All 5 intent classes have ≥1 prompt
- [ ] Shopping class meets floor (default ≥40%)
- [ ] Output CSV validates with `tools/geo_prompt_export.py` (exit 0)
- [ ] B2B SaaS defaults applied unless user overrides (segment, GTM motion)
- [ ] Product Questions filter check surfaced to user before generation
- [ ] Generation report written alongside CSV
- [ ] Skill is interactive — never generates without intake completing

## Generation report template

Save as `generation_report.md` in the same directory as the CSV:

```markdown
# Prompt set generation report

**Vertical:** <vertical>
**Client:** <client>
**Date:** <YYYY-MM-DD>
**Prompt count:** <N>

## Intake
- Buyer segment: ...
- GTM motion: ...
- Stack: ...
- Competitors: ...
- Keyword CSV: yes / no
- Shopping floor: N%

## Product Questions filter
<high | mid | low> visibility — <reasoning>

## Distribution

| Intent class | Count | % | vs target | Priority mix |
|---|---|---|---|---|
| shopping | ... | ... | ... | ... |
| ... | | | | |

Shopping-intent floor: met (N% ≥ 40%) / FAILED (N% < 40%)
Soft 50% cap: respected / `<class>` at N%

## Coverage notes
- What's strong
- What's thin / what was excluded and why
- Suggested follow-up prompt sets

## Sample prompts
- shopping: "..."
- comparative: "..."
- informational: "..."
- decision: "..."
- recommendation: "..."
```

## Storage

- **Client work:** `clients/<client>/geo/prompts/<vertical>_<YYYY-MM-DD>.csv`
- **Shared templates:** `research/geo-aeo/prompt-sets/<vertical>_template.csv`
- **MultiplAI:** `brands/multiplai/geo/prompts/<vertical>_<YYYY-MM-DD>.csv`

## Out of scope (deferred to V2)

- Auto-pull from GSC / SEMrush / Ahrefs APIs (V1 accepts a manual CSV)
- Voice-of-customer mining from support tickets or call transcripts
- Multilingual prompt generation
- Automated A/B variant testing

## References

- `research/geo-aeo/skills/02_prompt-set-builder.md` — full spec
- `research/geo-aeo/frameworks/01_aeo-playbook.md` — question types, Product Questions filter
- `research/geo-aeo/frameworks/03_measurement-framework.md` — prompt count sizing (50/200/1000), 4 measurement dimensions
- `research/geo-aeo/skills/01_share-of-answers.md` — downstream consumer of this CSV
- `tools/geo_prompt_export.py` — validator
