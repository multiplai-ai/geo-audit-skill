# Frameworks Index

Distilled, vertical-agnostic frameworks synthesized from the `articles/` and `transcripts/` corpus. These are the canonical reference docs that future skills (`/geo/audit`, `/geo/share-of-answers`, etc.) hook into.

**Status:** v1, written 2026-04-16 from 15 article summaries + 7 podcast transcripts. Each framework cites its source articles for traceability.

---

## The four frameworks

### [01 — AEO Playbook](01_aeo-playbook.md)
**What to DO.** The 7-step operational playbook (synthesized from Ethan Smith) + Aleyda Solis's 10-item checklist + the three core channels (landing pages, YouTube, Reddit) + the 5% framework + the Product Questions filter.

**Read this when:** building a new client GEO program, scoping an audit, deciding where to invest content effort.

**Feeds skills:** `/geo/audit`, `/geo/content-restructure`, `/geo/citation-network-mapper`.

### [02 — Citation Mechanics](02_citation-mechanics.md)
**How it WORKS.** The science (P < 0.0001, 1.2M citations analyzed). Source selection signals + passage extraction mechanics + the Five Content Characteristics + the citation-worthiness rubric.

**Read this when:** evaluating whether a piece of content is structured for AI citation, designing new content templates, building the audit scorecard.

**Feeds skills:** `/geo/audit`, `/geo/content-restructure`, `/geo/prompt-set-builder`.

### [03 — Measurement](03_measurement-framework.md)
**What to MEASURE.** Bucket A vs. Bucket B reporting + Share of Answers (the 4-dimension method) + the prompt test set sizing + the 5 fake-case-study warnings + the measurement maturity ladder.

**Read this when:** designing reporting for a client, defending a "this worked" claim, sizing the right level of measurement investment.

**Feeds skills:** `/geo/share-of-answers`, `/geo/prompt-set-builder`.

### [04 — SEO/GEO Integration & Guardrails](04_seo-geo-integration.md)
**What NOT to do.** SEO-as-foundation principle + the 5 high-risk tactics that will hurt SEO + the AI-content trap + attribution confusion + the SEO-positive/GEO-positive decision gate.

**Read this when:** evaluating any new tactic, reviewing vendor claims, sanity-checking a content strategy that "feels too clever."

**Feeds skills:** ALL skills — every recommendation must pass the SEO+/GEO+ gate.

---

## How frameworks relate to each other

```
                    ┌──────────────────────────┐
                    │ 04: SEO/GEO Guardrails   │  ← every action gated by this
                    │ (don't break SEO; avoid  │
                    │  AI-content trap; etc.)  │
                    └──────────────────────────┘
                                ▲
                                │ gates
                                │
        ┌───────────────────┐   │   ┌──────────────────────┐
        │ 01: Playbook      │   │   │ 02: Citation Mechanics│
        │ (the 7 steps,     │◄──┴──►│ (the 5 content        │
        │  channels, 5%     │       │  characteristics, ski │
        │  framework)       │       │  ramp, source signals)│
        └───────────────────┘       └──────────────────────┘
                  ▲                           ▲
                  │ informs                   │ informs
                  └────────────┬──────────────┘
                               │
                  ┌─────────────────────────┐
                  │ 03: Measurement         │
                  │ (Share of Answers, the  │
                  │  fake-CS warnings, the  │
                  │  maturity ladder)       │
                  └─────────────────────────┘
                         ▲
                         │
                  validates whether 01 + 02 actually worked
```

**Reading order for newcomers:**
1. Framework 04 first — understand the constraints
2. Framework 01 — what to do within those constraints
3. Framework 02 — why those tactics work (the design constraints)
4. Framework 03 — how to know it worked

---

## What's intentionally NOT in here

- **Vertical-specific application.** These frameworks are vertical-agnostic by design. VuMedi's specific application lives at `clients/vumedi/projects/FY2027 Growth Planning/geo-research/geo-optimization-plan.md`. Future client applications go in their respective entity dirs.
- **Tooling-specific implementation.** Profound / Peec.ai / ZipTie comparisons aren't here — they're a separate eval that should be redone every 6 months as the tooling market matures.
- **Tactical examples.** Where examples appear, they're illustrative. Specific tactics (e.g., specific Reddit subreddits to engage with, specific publication outreach lists) belong in client-specific playbooks.

---

## Maintenance

Update these frameworks when:
- A new flagship source publishes findings that contradict or extend existing claims
- A new tactic enters the corpus with controlled evidence (not vendor anecdote)
- A model update materially changes a citation mechanism (note version + date)
- Practitioner consensus shifts (e.g., once Mike King's Relevance Engineering doc lands, integrate into Framework 02)

When updating, preserve the source citations — every claim should remain traceable to a specific article or transcript.

## Provenance

v1 distilled 2026-04-16 by Claude. Source corpus seeded from a VuMedi FY27 research request that expanded into a reusable knowledge base.
