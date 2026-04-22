# Framework 03 — Measurement

**Scope:** What to measure to know if GEO/AEO is working. Architecture, metrics, and the strategic reframing required when traffic and pipeline decouple.

**Out of scope:** Operational playbook (→ Framework 01), citation mechanics (→ Framework 02).

**Primary sources:** Ethan Smith — `articles/04_lennys_ethan-smith-aeo-playbook.md`, `articles/02_graphite_aeo-is-the-new-seo.md`. Kevin Indig — `articles/09_growth-memo_great-decoupling.md`. Aleyda Solis — `articles/10_aleyda_ai-search-checklist.md`.

---

## The strategic reframe (start here)

**Traffic and pipeline no longer correlate.** AI interfaces answer queries without sending users to sites — the click→traffic→pipeline chain is broken.

Evidence:
- One client: 32% traffic growth + 75% signup growth over 6 months (2.3x faster pipeline than traffic)
- Informational queries answered inside AI Mode generate "nearly zero" external clicks
- Short-head keyword demand grew only 1.2% YoY, forecasted to decline 0.74%

Reframe required:
- **Stop** leading exec conversations with sessions, impressions, rankings
- **Start** reporting brand lift, pipeline influence %, LLM visibility rates
- The metric stack must measure *being mentioned* and *being chosen*, not just *being clicked*

> "Traffic was never the point. It was just the easiest thing to measure." — Indig & Johnson

---

## Two-bucket reporting architecture

Inherited from Hanna's bucketed reporting principle. Same structure works for GEO/AEO.

### Bucket A — Health & Trend (exec audience)
High-level, aggregated, directional. Not for debugging.

| Metric | Definition | Source |
|---|---|---|
| **Share of Answers** | % of fixed prompt set where brand appears as a citation, weekly trend | Manual or Profound/Peec/ZipTie |
| **AI-referred sessions → conversion** | AI-source GA4 traffic + downstream conversion rate | GA4 referral channel |
| **AI-referred business outcome** | Revenue / signups / minutes-watched attributable to AI source | GA4 + product analytics |
| **Competitive share** | Your citations vs. top 3 competitors per topic | Same prompt set as Share of Answers |

### Bucket B — Diagnostics & Experimentation (operator audience)
Decomposed driver metrics for "what moved" and "what to do next."

| Metric | Definition | Use |
|---|---|---|
| **Question-level citation presence** | Per-prompt: cited yes/no, position (primary/secondary/tertiary) | Identify which question types you win/lose |
| **Page-level citation rate** | Per-URL: % of test prompts where this URL appears | Identify which pages are working |
| **Surface-level share** | ChatGPT vs. Claude vs. Gemini vs. Perplexity citations | Each AI behaves differently — diagnose surface gaps |
| **Treated vs. control** | Citation rate on restructured pages vs. matched control pages | Validate whether content rework actually moved citations |
| **Funnel decomposition** | AI impression → citation click → page view → conversion event | Find leaks at each step |

---

## Share of Answers — the canonical primary metric

Ethan Smith's framework. Track across **four dimensions simultaneously**:

### Dimension 1: Multiple surfaces
Don't measure ChatGPT alone. Run the same prompts across ChatGPT, Perplexity, Gemini, Claude. Citation patterns differ meaningfully.

### Dimension 2: Question variations
A topic ≠ a question. For each topic, test dozens of intent-aligned questions. Example for one topic:
- "What is X?"
- "How does X work?"
- "When is X used?"
- "What are the alternatives to X?"
- "What is the best X for [persona]?"
- etc.

Citation behavior varies wildly across question types. Aggregate to topic level for exec reporting; keep question level for operator diagnostics.

### Dimension 3: Multiple runs
AI responses are stochastic. Test the same prompt 3-5x in a session to capture variance. Report median + range, not single-shot.

### Dimension 4: Citation presence
Track three states per prompt:
- **Cited as primary** — your domain is the main reference
- **Cited as secondary/tertiary** — your domain is one of several mentioned
- **Not cited** — your domain doesn't appear

Don't conflate primary and secondary citations. Primary = recommendation; secondary = corroboration. Different conversion implications.

---

## Building the prompt test set

A defensible Share-of-Answers measurement requires a representative prompt set. Recommended sizing:

| Scope | Prompt count | Rationale |
|---|---|---|
| Single specialty / category MVP | 50 | Enough for directional read; fits in 1-2 hours of manual testing |
| Standard ongoing tracking | 200 (40 × 5 specialties) | Covers core verticals; weekly cadence feasible with 1-2 hr operator time |
| Comprehensive | 1000+ | Requires automation tooling (Profound, Peec.ai, ZipTie) |

**How to source prompts:**
1. Internal search/SEO data — what queries do users actually run on your site?
2. Sales/CS conversation mining — what do prospects ask before buying?
3. Customer interviews — what would they ask ChatGPT?
4. Competitor paid search keywords — what queries do they spend on (signals high-intent)
5. AI itself — ask Claude/ChatGPT to generate the top 50 questions in a category, then sanity-check

---

## The five fake-case-study warnings (Ethan Smith)

Required gating discipline before believing any "this worked" claim — your own or a vendor's.

### 1. Misattribution
LLM usage is growing organically. AI-referred traffic going up doesn't mean *your optimization* moved it. **Required control:** test/control group on a fixed prompt set, not absolute traffic numbers.

### 2. Relative vs. absolute
Percentages mean nothing without base. "200% growth in AI-referred traffic" from 50 sessions to 150 sessions is noise. **Required:** report absolute numbers AND % of overall site traffic. Target floor: 5%+ of site traffic for AEO to matter at exec level.

### 3. Vanity metrics
Question impressions, ranking position, citation count — these don't matter without conversion impact. **Required:** every metric in Bucket A must connect to a business outcome (signup, purchase, minute watched, MQL).

### 4. Brand reputation bias
Vendor case studies featuring big-name clients aren't proof. Big brands have pre-existing authority that shows up in AI regardless of vendor work. **Required:** case studies must include controls or pre/post comparisons with isolation.

### 5. Reproduction
Single experiment results aren't reliable. **Required:** rerun winning tactics in a different segment / vertical / time period before declaring a tactic valid.

---

## The four components of "Brand Strength" in AI search (Indig)

Used as evaluation lens for whether your brand is positioned to win citations:

1. **Topical authority** — conceptual map dominance, not keyword coverage. Does AI understand you cover this entire topic?
2. **ICP alignment** — buyer-specific answers; relevance > volume. Does your content speak to the actual person asking?
3. **Third-party validation** — citations from category sources outweigh high-DA links. Are you mentioned in the *right* places?
4. **Positioning clarity** — LLMs must recognize what your brand represents. Vague positioning gets skipped.

**Diagnostic question:** for each of the 4 components, score your brand 1-5 in the verticals you care about. Anything ≤2 is a foundation gap that GEO tactics can't fix.

---

## Measurement maturity ladder

Suggested staged rollout — don't skip stages. Each builds the credibility for the next.

| Stage | Time | What you measure | Tooling |
|---|---|---|---|
| **0 — Baseline** | Week 1 | Manual run of 50-prompt set across 4 AIs; document citation presence | Google Sheet |
| **1 — Trend** | Weeks 2-12 | Same prompt set, weekly cadence; trend Share of Answers | Google Sheet → Tableau view |
| **2 — Diagnostic** | Months 3-6 | Treated vs. control pages; surface-level share; question-level diagnostics | Same + tagged GA4 channels |
| **3 — Business attribution** | Months 4+ | AI-referred sessions → conversion; competitor share | GA4 + product analytics |
| **4 — Automated continuous** | Month 6+ | Daily/weekly automated prompt runs; sentiment analysis | Profound / Peec.ai / ZipTie ($$$) |

**Don't skip to Stage 4 with vendor tooling before having Stage 1 baseline data.** The tooling market is nascent and noisy. Manual baselines are your defense against vendor BS (warning #4).

---

## How to apply this framework (for skills)

- **`/geo/share-of-answers`** — automate Stage 1 + 2 of the maturity ladder. Inputs: brand name, prompt set CSV, target AIs. Outputs: weekly run CSV with citation status per prompt × AI; rolling Share of Answers number.
- **`/geo/prompt-set-builder`** — generate a defensible 50-200 prompt test set from ICP + vertical + competitor data. Output: CSV ready for `/geo/share-of-answers`.
- **Universal:** any skill claiming "this moved X" must invoke the 5 fake-case-study warnings as a checklist gating final output.

---

## Open questions

- Cross-AI weighting in a single Share-of-Answers number — should ChatGPT count more than Claude? Probably yes (usage volume), but how much?
- Sentiment vs. presence — being cited *negatively* is worse than not being cited. Current measurement focuses on presence. Need sentiment overlay.
- Long-term metric stability — as AI providers add defensive measures (per Framework 02), historical Share-of-Answers data may not be comparable across model versions. Suggest annotating measurement runs with model version IDs where available.
