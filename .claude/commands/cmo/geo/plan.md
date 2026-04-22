# Skill: /cmo/geo/plan

Synthesize outputs from `/cmo/geo/share-of-answers` and `/cmo/geo/audit` into a prioritized GEO optimization plan with eng-handoff cards, a revenue impact model, an exec pitch one-pager, and a Gamma exec deck.

This is the Phase 1 terminal deliverable — closes the loop from measurement to action and translates the plan into business value for CMO / CFO / CEO sponsorship.

**Default scope:** B2B SaaS companies selling to mid-market and enterprise buyers.

**Two performance goals tracked separately in all outputs:**
- **Goal A — Mentions:** increase brand citation rate in generative engine answers (share of voice)
- **Goal B — Shopping-intent share + pipeline:** increase qualified inbound from shopping-intent queries → pipeline → revenue

## When to use

- After running share-of-answers + audit on a client — produces the 90-day plan + business case
- Quarterly re-plan — re-scoring initiatives against current data
- Pre-budgeting exercise — producing the business case for GEO investment
- After a major product launch, repositioning, or ICP shift that changes the target prompt set

## Inputs (asked at intake)

| Input | Required? | Source |
|---|---|---|
| Audit output directory | Yes | Output of `/cmo/geo/audit` (contains `diagnostic.md`, page scorecards, `data-inventory.md`) |
| SoA output directory | Yes | Output of `/cmo/geo/share-of-answers` (contains `runs.csv`, `summary.md`, `trends.csv`) |
| Citation-network map | No | Output of `/cmo/geo/citation-network-mapper` if available (Phase 2 skill) |
| Client name | Yes | User |
| Segment | Yes | `mid-market` \| `enterprise` \| `both` |
| GTM motion | Yes | `PLG` \| `sales-led` \| `hybrid` |
| Business inputs | Yes | ACV, win rate, conversion rates, organic traffic (B2B SaaS defaults offered) |

## Workflow

### Step 1 — Load + extract baselines

Run the companion tool to parse audit + SoA outputs into structured baselines:

```bash
python3 tools/geo_plan.py extract-baselines \
    --audit-dir <audit-output-dir> \
    --soa-dir <soa-output-dir> \
    --output <plan-output-dir>
```

This produces `baselines.json` with Goal A share, Goal B share, competitor shares, audit score distribution, and common issues.

Then read the full diagnostic context:
- Read `diagnostic.md` from the audit directory (the full synthesis, not just scores)
- Read `summary.md` from the SoA directory (win/lose/gap analysis)
- If citation-network-mapper output exists, read that too

### Step 2 — Clarify business context

Ask the user for business inputs. Present B2B SaaS segment defaults and let them accept or override:

> I need a few business inputs to build the revenue model. Here are **mid-market B2B SaaS defaults** — accept or override each:
>
> | Parameter | Default | Your value? |
> |---|---|---|
> | ACV | $30,000 | |
> | Visitor → MQL | 2.5% | |
> | MQL → SQL | 20% | |
> | SQL → Closed-won | 25% | |
> | Sales cycle | 2 months | |
> | Annual organic traffic | (required — no default) | |
>
> Also confirm: **GTM motion** — PLG / sales-led / hybrid?

For enterprise segment, show enterprise defaults instead ($150K ACV, 0.75% V→MQL, 30% MQL→SQL, 20% SQL→close, 9-month cycle).

To see all defaults programmatically: `python3 tools/geo_plan.py show-defaults`

### Step 3 — Cluster findings into initiatives

Read the baselines, diagnostic, and SoA summary. Group related findings into **5–12 initiatives** (hard cap at 12 — prevents plan sprawl).

Clustering guidance:
- Group by the page-level or site-level change required, not by the individual signal
- Example: if 8 pages fail `first_30_answer` AND `qa_h2s`, that's one initiative ("Restructure priority pages for citation-readiness"), not two
- Reference Framework 01's 7-step playbook for initiative taxonomy:
  - Content restructuring (Steps 3–4)
  - Technical access (robots.txt, llms.txt, SSR)
  - Schema/structured data
  - Off-site presence (Step 5)
  - Help center optimization (Step 3)
  - New content creation (gap filling)
  - Measurement setup (Step 6–7)

### Step 4 — Score each initiative (ICE)

For each initiative:

- **Impact** (1–10): modeled lift on Goal A or Goal B
  - 8–10: directly addresses a top-3 common issue across priority pages, or closes a competitive gap on shopping-intent queries
  - 5–7: addresses a secondary issue, or targets informational/comparative queries
  - 1–4: nice-to-have, marginal expected lift
- **Confidence** (1–10): strength of evidence
  - 8–10: supported by Framework 02 citation mechanics research (P < 0.0001) AND confirmed in audit data
  - 5–7: supported by framework research but not yet confirmed in this client's data
  - 1–4: hypothesis based on general best practice, no direct evidence
- **Effort** (1–10, inverse): 10 = trivial, 1 = months of work
  - 8–10: content-only edit, no engineering, < 1 day
  - 5–7: content + schema or config changes, 1–2 weeks
  - 1–4: architecture changes, SSR, major site restructuring

**ICE score** = (Impact × Confidence) / Effort × 10

### Step 5 — Tag SEO/GEO gate (Framework 04)

Every initiative gets one of three labels:

- **`[SEO+/GEO+]`** — helps both traditional search and AI citation. **Prioritize these.**
- **`[GEO+ only]`** — helps AI citation, neutral for SEO. Safe to implement.
- **`[GEO+ but SEO-]`** — helps AI citation but may hurt SEO. **Flag and deprioritize. Never recommend.**

Check each initiative against Framework 04's 5 high-risk tactics:
1. Rapid AI content scaling → never recommend
2. Artificial content refreshing → never recommend
3. Self-promotional listicles → never recommend
4. Prompt injection → never recommend
5. Excessive comparison pages → flag if present

If an initiative would trigger any of these, either redesign it to be SEO-safe or explicitly defer it with rationale.

### Step 6 — Write initiatives.json

Write the initiatives to a JSON file the companion tool can consume:

```json
{
  "initiatives": [
    {
      "id": "I01",
      "name": "Front-load direct answers on priority pages",
      "description": "Restructure top 10 landing pages to place direct, definitional answers in the first 30% of content. AI citation research shows the first 30% gets 44.2% of all citations (Framework 02).",
      "goal": "B",
      "seo_geo_tag": "SEO+/GEO+",
      "ice_impact": 8,
      "ice_confidence": 8,
      "ice_effort": 8,
      "projected_lift_pct": 15.0,
      "phase": "30-day",
      "effort_size": "M",
      "role_needed": "content writer",
      "audit_findings": ["8/15 pages score <70 on first_30_answer"],
      "dependencies": [],
      "context": "Framework 02: first 30% of content = 44.2% of citations",
      "steps": [
        "Identify the implied question each page answers (from H1 or page title)",
        "Write a direct 1-2 sentence answer to that question",
        "Place the answer in the first paragraph, before any background context",
        "Ensure the answer uses 'X is Y' definitional structure (Framework 02: 36.2% vs 20.2% citation rate)",
        "Re-run geo_audit.py on the updated page to confirm first_30_answer score ≥70"
      ],
      "acceptance_criteria": [
        "All 10 pages have direct answer in first 150 words",
        "first_30_answer score ≥70 on re-audit",
        "No change to existing internal links or canonical tags"
      ],
      "technical_requirements": [
        "URLs: [list from audit priority URLs]",
        "Content-only changes — no engineering needed",
        "Preserve existing schema.org markup"
      ]
    }
  ]
}
```

Save to `<plan-output-dir>/initiatives.json`.

**Required fields per initiative:** `id`, `name`, `goal` (A/B/BOTH), `seo_geo_tag`, `ice_impact`, `ice_confidence`, `ice_effort`, `projected_lift_pct`

**Optional but recommended:** `description`, `phase`, `effort_size`, `role_needed`, `audit_findings`, `dependencies`, `context`, `steps`, `acceptance_criteria`, `technical_requirements`

### Step 7 — Run revenue model

Run the companion tool to compute revenue projections:

```bash
python3 tools/geo_plan.py build-plan \
    --initiatives <plan-output-dir>/initiatives.json \
    --baselines <plan-output-dir>/baselines.json \
    --output <plan-output-dir> \
    --client "<Client Name>" \
    --segment mid-market \
    --acv <acv> \
    --visitor-to-mql <rate> \
    --mql-to-sql <rate> \
    --sql-to-close <rate> \
    --sales-cycle-months <months> \
    --annual-organic-traffic <traffic>
```

This produces:
- `revenue-model.csv` — editable spreadsheet with per-initiative projections
- `revenue-model.md` — readable version with assumptions + sensitivity analysis
- `eng-cards/` — scaffolded eng-handoff cards (one per initiative)
- `exec-one-pager.md` — scaffolded exec pitch
- `business-case.md` — scaffolded business case appendix

### Step 8 — Write plan.md

Write the main plan document. Structure:

```markdown
# GEO Optimization Plan — [Client Name]

**Date:** YYYY-MM-DD
**Segment:** mid-market | enterprise
**GTM:** PLG | sales-led | hybrid

## Executive Summary
<!-- 3-5 bullets: what's broken, what we'll fix, expected outcome, the ask -->

## Current State Baselines

### Goal A — Mentions (share of voice)
<!-- From baselines.json: overall share, by-surface breakdown, competitive position -->

### Goal B — Shopping-Intent Share (pipeline metric)
<!-- From baselines.json: shopping share, by-surface breakdown, competitive position -->

### Content Citation-Readiness
<!-- From baselines.json: audit avg score, distribution, common issues -->

## Initiative List

| # | Initiative | Goal | SEO/GEO | ICE | Phase | Lift | Annual Rev (mid) |
|---|---|---|---|---|---|---|---|
<!-- One row per initiative, ICE-sorted descending -->

## Recommended Sequence (30/60/90-day)

### Phase 1 — Days 1-30: Quick Wins
<!-- List initiatives. Gate: what must be true to proceed -->

### Phase 2 — Days 31-60: Medium Effort
<!-- List initiatives. Gate: what must be true to proceed -->

### Phase 3 — Days 61-90: Heavy Lifts + Measurement
<!-- List initiatives. Gate: program review -->

## Required Gating Language

**SEO/GEO Integration Gate (Framework 04):**
Every recommendation in this plan has been tagged with an SEO/GEO label.
No `[GEO+ but SEO-]` tactics are recommended. All initiatives are either
`[SEO+/GEO+]` (helps both) or `[GEO+ only]` (helps AI citation, neutral for SEO).

Do NOT implement any tactic that falls into the 5 high-risk categories
(Framework 04): rapid AI content scaling, artificial refreshing,
self-promotional listicles, prompt injection, excessive comparison pages.

**Attribution Discipline (Framework 03):**
Revenue projections use an assisted attribution model with a 50% haircut.
Every dollar figure traces to explicit assumptions in revenue-model.csv.
Do not present mid-confidence numbers as forecasts — they are modeled estimates.
```

### Step 9 — Fill in eng-handoff cards

The tool scaffolded `eng-cards/<ID>_<slug>.md` files with the structure. Fill in:
- **Context** — why this matters, in plain English. No GEO jargon without a 1-line definition inline.
- **What to do** — specific, unambiguous instructions. Written for someone who has never done GEO/AEO.
- **Why** — link back to audit finding + Framework 02/04 research
- **Acceptance criteria** — checkboxes a reviewer can sign off on
- **Technical requirements** — URLs, files, pages affected
- **References** — specific framework sections in `research/geo-aeo/`

Every card must be readable by a junior marketer or engineering team member with zero GEO background.

### Step 10 — Fill in exec one-pager + business case

Fill in the scaffolded `exec-one-pager.md`:
- **The Ask** — dollar investment + headcount + time commitment
- **Why Now** — 2-3 bullets grounded in research corpus data:
  - AI search volume up 26% since ChatGPT launch; Google's share dropped 89% → 71%
  - Competitors [names] cited at [X]% on shopping-intent queries vs. client's [Y]%
  - Traffic and pipeline have decoupled (Framework 03) — clicks ≠ pipeline anymore
- **Risks If We Don't Act** — competitor citation dominance, pipeline decay, category-narrative capture

Fill in the scaffolded `business-case.md`:
- **Timeline + staffing** — per-phase resource requirements
- **Comparable benchmarks** — cite from research corpus (Graphite: 32% traffic + 75% signup growth)
- **FAQ** — fill in each answer with plan-specific numbers

**Exec one-pager must be ≤1 page, zero jargon without inline definition.**

### Step 11 — Generate Gamma exec deck

Generate a ≤10 slide exec deck from the exec one-pager content using Gamma MCP.

Deck structure:
1. Title + client + date
2. The ask (investment + timeline)
3. The return (projected annual revenue, mid-confidence band)
4. Current state — Goal A baseline
5. Current state — Goal B baseline
6. Why now (2-3 market-shift bullets)
7. Top 3 initiatives
8. 30/60/90-day phasing
9. Risks of inaction
10. Next steps / decision requested

Use the exec one-pager content verbatim — same numbers, same narrative, no drift.

Call `mcp__claude_ai_Gamma__generate` with:
- `inputText`: the complete exec one-pager content, reformatted as slide content
- `format`: `"presentation"`
- `numCards`: 10
- `textOptions.audience`: `"executives"`
- `textOptions.tone`: `"professional"`

**If Gamma MCP is unavailable at runtime:** Fail loudly. Tell the user: "Gamma MCP is not connected — the exec deck is a required V1 output. Connect Gamma and re-run, or invoke this step manually." Do NOT silently skip the deck.

Share the Gamma URL with the user. Note that the deck can be customized in the Gamma editor — the skill does not re-generate decks for edits.

### Step 12 — Surface summary in chat

Post the key numbers inline:

> **Plan complete for [Client Name]**
>
> - **Goal A baseline:** X% mention share → target Y%
> - **Goal B baseline:** X% shopping-intent share → target Y%
> - **Initiatives:** N (ICE-sorted, phased 30/60/90)
> - **Projected annual revenue:** $X (mid) | $Y–$Z range
> - **Top 3:** [names]
>
> All outputs saved to `<plan-output-dir>/`
> Gamma deck: [URL]

## Output

### Files produced

| File | Purpose |
|---|---|
| `baselines.json` | Extracted baselines from audit + SoA (Step 1) |
| `initiatives.json` | Claude-generated initiative list with ICE scores (Step 6) |
| `plan.md` | Main plan document — exec summary, initiative list, phasing (Step 8) |
| `eng-cards/<ID>_<slug>.md` | One eng-handoff card per initiative (Steps 7 + 9) |
| `revenue-model.csv` | Editable revenue model spreadsheet (Step 7) |
| `revenue-model.md` | Readable revenue model with assumptions + sensitivity (Step 7) |
| `exec-one-pager.md` | ≤1 page exec pitch (Steps 7 + 10) |
| `business-case.md` | Full business case appendix (Steps 7 + 10) |

### Storage

- Client work: `clients/<client>/geo/plan/<YYYY-MM-DD>/`
- MultiplAI / personal: `brands/multiplai/geo/plan/<YYYY-MM-DD>/`

## Acceptance criteria for "done"

- [ ] Every audit finding is addressed in an initiative OR explicitly deferred with rationale
- [ ] Every initiative has an eng-handoff card readable by someone with zero GEO background
- [ ] Revenue model cleanly separates Goal A (mentions) from Goal B (shopping-intent pipeline)
- [ ] Every dollar figure has a visible assumption traceable in revenue-model.csv — no hidden math
- [ ] No recommendation triggers any of Framework 04's 5 high-risk tactics
- [ ] Every initiative carries a Framework 04 SEO/GEO tag; `[GEO+ but SEO-]` items flagged and deprioritized, never recommended
- [ ] Exec one-pager ≤1 page, zero jargon without inline definition
- [ ] Initiative count ≤12
- [ ] Gamma deck generated via MCP; content matches exec one-pager (no narrative drift)
- [ ] All outputs saved to correct storage path

## CLI cheat sheet

```bash
# Show B2B SaaS segment defaults
python3 tools/geo_plan.py show-defaults

# Stage 1: Extract baselines from audit + SoA
python3 tools/geo_plan.py extract-baselines \
    --audit-dir clients/acme/geo/audit/2026-04-17/ \
    --soa-dir clients/acme/geo/share-of-answers/2026-04-16/ \
    --output clients/acme/geo/plan/2026-04-17/

# Stage 2: Build plan artifacts (after initiatives.json is written)
python3 tools/geo_plan.py build-plan \
    --initiatives clients/acme/geo/plan/2026-04-17/initiatives.json \
    --baselines clients/acme/geo/plan/2026-04-17/baselines.json \
    --output clients/acme/geo/plan/2026-04-17/ \
    --client "Acme Corp" --segment mid-market \
    --acv 35000 --annual-organic-traffic 120000

# Enterprise segment with overrides
python3 tools/geo_plan.py build-plan \
    --initiatives initiatives.json --baselines baselines.json \
    --output plan/ --client "BigCo" --segment enterprise \
    --acv 200000 --visitor-to-mql 0.005 --annual-organic-traffic 500000
```

## Out of scope (deferred to V2)

- Automated ticket creation (direct Linear/Jira push) — V1 eng cards are human-reviewed then copy/pasted
- Multi-client aggregate view (portfolio GEO ROI)
- Real CRM attribution integration — V1 uses user-provided assumptions
- Cross-initiative dependency graph visualization
- Auto-refresh of revenue model from live SoA trends
- Auto-regeneration of Gamma deck after edits — V1 generates once, user edits in Gamma editor

## References

- Spec: `research/geo-aeo/skills/07_plan.md`
- Framework 01 (AEO Playbook): `research/geo-aeo/frameworks/01_aeo-playbook.md`
- Framework 02 (Citation Mechanics): `research/geo-aeo/frameworks/02_citation-mechanics.md`
- Framework 03 (Measurement): `research/geo-aeo/frameworks/03_measurement-framework.md`
- Framework 04 (SEO/GEO Integration): `research/geo-aeo/frameworks/04_seo-geo-integration.md`
- Tool: `tools/geo_plan.py`
- Upstream: `/cmo/geo/share-of-answers` → `runs.csv`, `/cmo/geo/audit` → `diagnostic.md`
- Format reference: `clients/vumedi/projects/AEO Audit/01-exec-brief-roman.md` (pattern only, not content)
