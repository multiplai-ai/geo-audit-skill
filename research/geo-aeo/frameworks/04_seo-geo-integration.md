# Framework 04 — SEO/GEO Integration & Guardrails

**Scope:** How SEO and GEO relate, what NOT to do, and how to balance the two surfaces. Gating principles all GEO programs must respect.

**Out of scope:** Operational playbook (→ Framework 01), citation mechanics (→ Framework 02), measurement (→ Framework 03).

**Primary sources:** Lily Ray — `articles/12_lily-ray_geo-destroying-seo.md`. Aleyda Solis — `articles/11_aleyda_seo-vs-geo.md`. Ethan Smith — `articles/03_graphite_ai-is-much-bigger.md`, `articles/13_graphite_seo-ai-mag-podcast.md`. Ethan Smith on AI vs. human content — `articles/15_graphite_ai-vs-human-content.md`.

---

## The foundational principle (start here)

**SEO is GEO's foundation, not its competitor.**

Why:
- AI search uses RAG (Retrieval-Augmented Generation). Pulls from search indexes BEFORE generating responses.
- Google's index is the de facto retrieval foundation for most AI search traffic — including ChatGPT.
- Damaging SEO visibility destroys the foundation that determines whether AI surfaces retrieve your content at all.
- Britney Muller's framing: "Every URL you see in an LLM output comes from a search engine API."

**Practical translation:** breaking your Google rankings to "win at AI" is self-defeating. They are one integrated system, not two competing ones.

---

## The non-zero-sum reality

Common misconception: "AI is killing search." The data:
- Google's slice of search has shrunk (89% → 71% globally since 2023) — true
- BUT total search volume is up 26% since ChatGPT launched
- The pie grew, then was redivided. Google's absolute volume is roughly flat-to-up.

**Implication for resource allocation:** SEO and GEO are complementary channels. Investment in one shouldn't come from cannibalizing the other. Both deserve growth budget.

---

## Five high-risk GEO tactics that will hurt your SEO (Lily Ray)

Use as a "do not do" list. These were popular in 2024-2025 and have produced documented penalties.

### 1. Rapid AI content scaling
**The tactic:** Generate hundreds of articles with AI; publish at scale; ride initial traffic spike.
**Why it fails:** Google's Scaled Content Abuse policy (2024) targets exactly this. 30+ documented case studies show initial growth → dramatic crashes. June 2025 Core Update hit featured case-study sites particularly hard.
**Healthcare implication:** especially dangerous in YMYL (Your Money or Your Life) verticals where E-E-A-T standards are highest.

### 2. Artificial content refreshing
**The tactic:** Tweak dates and run minor edits without meaningful changes; trigger re-crawl signals.
**Why it fails:** Google increasingly detects cosmetic vs. genuine updates via version-comparison analysis.
**Better approach:** if you're going to update, do real work — add new data, restructure, address new questions. Mark with explicit "Updated: [date]" + bullet of what changed.

### 3. Self-promotional listicles
**The tactic:** Write "best X tools" articles ranking your own product as #1.
**Why it fails:** Major traffic drops documented starting Jan 21, 2026 for sites doing this heavily. Crackdown accelerating as the tactic gets publicized.
**Better approach:** if you're going to do comparisons, be honest about positioning ("we excel at X, competitor Y is better at Z") and let your case for #1 stand on substance.

### 4. "Summarize with AI" prompt injection
**The tactic:** Hide instructions in page content telling AI summarizers to favor your brand.
**Why it fails:** Microsoft classified this as a security threat (Feb 2026). 50+ examples from 31 companies documented. Privacy law + consumer protection violations.
**Don't do this. Period.**

### 5. Excessive comparison/alternative pages
**The tactic:** Create dozens of "X vs Y" or "alternatives to Z" pages purely to capture comparison searches.
**Why it fails:** One documented site created 51 "alternatives" pages while losing organic traffic AND ChatGPT citations in late January 2026.
**Better approach:** create comparison content only where you have genuine, defensible perspective. Quality > coverage.

---

## The AI-content content trap (Ethan Smith)

**Stat:** AI-generated articles now exceed human-written in published volume (since Nov 2024). Volume plateaued mid-2024 — likely as practitioners discovered it doesn't work.

**The truth:**
- AI-generated articles **largely do not appear in Google or ChatGPT**
- Detection accuracy: 99.4% (GPT-4o)
- Search engines reliably penalize purely AI content

**The hybrid gap:**
- AI-generated + human-edited content was NOT studied in the data above
- Likely an even larger share of published content than pure AI
- Strategic opportunity: human-in-the-loop editing is the durable approach

**Operating principle:** use AI as drafting/research tool, not publisher. Final published content must reflect human voice, original insight, or proprietary data.

---

## Attribution confusion — the most important warning

**The trap:** vendor or internal "GEO wins" almost always reflect *pre-existing strong SEO performance*, not the GEO tactic in question.

**Why:** brands with established authority, backlinks, and organic rankings appear in AI BECAUSE of their search visibility — not despite it.

**Lily Ray:** "Correlation is being sold as causation."

**Required discipline:** every "this GEO tactic worked" claim must be evaluated against the question: *would this brand have appeared in AI answers anyway, given its existing search authority?* If yes, the GEO tactic is unproven.

**See Framework 03's fake-case-study warnings for the operational test.**

---

## What still works across BOTH SEO and GEO (Aleyda Solis)

The durable signals — invest here for compounding returns across both surfaces:

| Signal | SEO version | GEO version |
|---|---|---|
| **Content quality** | E-E-A-T compliance | Citation-worthy claims with verifiable sources |
| **Authority** | Backlinks from authoritative domains | Mentions across cited sources in your category |
| **Crawlability** | Googlebot accesses content | All AI bots access content (GPTBot, ClaudeBot, etc.) + SSR for JS-heavy pages |
| **Original research** | Earns links | Earns citations |
| **Author credentials** | E-E-A-T signal | Trust signal for AI |
| **Structured data** | Rich results | Helps AI classification + extraction |

**Strategic implication:** for any content investment, ask "does this serve both SEO and GEO?" If yes, prioritize. If no, ask why.

---

## What's NEW for GEO (vs. SEO)

Genuinely new requirements not reducible to existing SEO discipline:

1. **AI bot access** — explicit allowance for non-Google crawlers (ClaudeBot, PerplexityBot, GPTBot, etc.) in robots.txt and at firewall level
2. **Stricter SSR requirement** — LLMs are less tolerant of JavaScript than Google's modern indexer
3. **Chunk-level structure** — content must be self-contained at the section level (not just at the page level) — see Framework 02
4. **Multi-surface measurement** — traditional rank tracking insufficient; need cross-AI Share of Answers — see Framework 03
5. **Brand recognition by entity** — LLMs need to recognize *what your brand represents*; vague positioning gets skipped where SEO might still rank you

---

## Decision framework: SEO vs. GEO investment

When deciding where to put effort, use this gate:

```
Is the action SEO-positive AND GEO-positive?
├── YES → invest first
├── NO, only one positive → invest if isolated; flag tradeoff
└── NEGATIVE for either → STOP. Reconsider.
```

**Examples:**
- Adding clean transcripts to YouTube videos → SEO+ AND GEO+ → invest
- Writing the "ultimate 10K-word guide" → SEO+ but GEO- (Indig: ultimate guides occupy unreliable middle tier) → reconsider; build focused 1.5K-word page instead
- Hiding LLM prompt injection in pages → potentially short-term GEO+, but SEO- (Google penalty risk) → stop
- Adding AI-generated content for volume → both negative → stop

---

## Compliance + trust guardrails (regulated verticals)

For YMYL / regulated verticals (healthcare, finance, legal):
- AI tactics that work in commerce/SaaS may not work — and may carry compliance risk
- Don't generate AI content that makes treatment, financial, or legal recommendations
- Flag privacy/compliance review for any tactic involving:
  - User-level behavior data exposed to AI optimization vendors
  - Hidden instructions or prompt injection (security risk per #4 above)
  - Third-party data scraping
- Required gate: every GEO tactic in a regulated vertical needs legal/compliance sign-off as part of QA

---

## How to apply this framework (for skills)

- **`/geo/audit`** — first pass should check the 5 high-risk tactics list (don't recommend changes that trigger any). Final output must include "SEO+/GEO+/SEO-/GEO-" labels per recommendation.
- **`/geo/content-restructure`** — preserve original SEO signals (canonical tags, internal links, structured data). Restructure form, not authority signals.
- **Universal:** every recommendation across all GEO skills must pass the SEO-positive/GEO-positive gate above. Add explicit warning if any tactic is SEO-neutral or SEO-negative.

---

## Open questions

- Vertical-specific decision rules — the "ultimate guide" tactic that hurts in some verticals helps in Education (per Indig). Need vertical-specific weighting in the decision framework.
- Compliance-friendly Reddit participation — how regulated-industry employees authentically participate without violating disclosure rules. Worth a dedicated playbook.
- Recovery timelines — sites that violated the high-risk tactics in 2024-2025 are now in penalty recovery. How long does recovery take? Lily Ray suggests "multiple years" but specifics are sparse in current corpus.
