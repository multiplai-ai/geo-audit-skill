# Skill: /cmo/geo/content-restructure

Rewrite a single page (URL or local markdown) in the structured-briefing format from Framework 02 — front-loaded answer, Q&A H2s, entity richness, definitive language, chunk independence — while preserving voice, named entities, numbers, and factual accuracy.

Operationalizes Framework 02's citation mechanics and Framework 01's Step 4 (content structure for citation). Uses skill `#3 /cmo/geo/audit` for pre/post scoring so the rubric is consistent across the suite.

**Default scope:** B2B SaaS companies selling to mid-market and enterprise buyers. Also works for regulated verticals (medical / legal / financial) — the skill auto-detects YMYL content and raises a hard pause before any claim is rewritten.

**This is the most complex skill in the suite.** Go slow. Never execute a rewrite without operator approval at the checkpoint. Never add facts that are not in the source.

## When to use

- Restructuring top 10–100 pages on a client site (run page by page; batch via shell loop)
- Single-page rework — e.g., a key landing page underperforming on Framework 02 signals
- Templating a new content format — rewrite one exemplar, then humans replicate the pattern
- Treated-vs-control experiments — rewrite a subset, leave the rest untouched, measure citation lift after 4+ weeks

## Inputs (asked at intake)

| Input | Required? | Source / default |
|---|---|---|
| Source (URL or local `.md` / `.html` path) | Yes | User |
| Client identifier (for output path) | Yes | User |
| Voice profile path | Yes | `brand/voice-synthesis.md` (personal) or client-specific path (e.g., `clients/<client>/brand/voice.md`) |
| Target persona | No | Inherits from voice profile |
| Preserve sections | No | User flags any section that must NOT be changed (legal disclaimer, regulatory copy, schema markup, etc.) |
| Length budget | No | ≤120% of source word count (soft); 150% hard fail; 50% floor |
| Constraints | No | Regulatory rules, brand do/don't, compliance language |

## Workflow

### Stage 0 — Intake + source load

- [ ] 1. Confirm: source, client, voice profile path, any preserve sections
- [ ] 2. Load source via `geo_restructure_diff.py load_source()` semantics — URL fetched, local file read; content extracted to clean text
- [ ] 3. Set the output directory: `.tmp/geo/content-restructure/<slug>/` for working files

### Stage 1 — Pre-audit + fact extraction + YMYL gate

Run all three in parallel — they are independent, and the operator sees them together.

```bash
# Pre-audit (uses /cmo/geo/audit's rubric — no re-implementation)
python3 tools/geo_audit.py --url <source-url> --output .tmp/geo/content-restructure/<slug>/pre-audit/

# Facts: numbers, entities, quoted claims the rewrite must preserve
python3 tools/geo_restructure_diff.py extract-facts \
    --source <source> --output .tmp/geo/content-restructure/<slug>/

# YMYL classification — exit 10 if medical / legal / financial
python3 tools/geo_restructure_diff.py detect-ymyl \
    --source <source> --output .tmp/geo/content-restructure/<slug>/
```

**YMYL gate (HARD PAUSE):** if `detect-ymyl` exits 10, stop and say in chat:

> This content is flagged as YMYL — top category: `<medical|legal|financial>` at `X%` term density. Restructure will rearrange existing claims but **not add, modify, or soften any clinical / legal / financial claim**. Confirm before proceeding. If any claim needs to change, that is a content edit, not a restructure — route to the subject-matter expert first.

Wait for explicit confirmation. If unavailable, treat as go-ahead only if the operator is the SME.

### Stage 2 — Voice load

Read the voice profile at the path from intake. Extract:
- Hard-no anti-patterns (always enforced)
- Voice-specific DOs/DON'Ts (may be Hanna's Emily-audit DOs or a client's style guide)
- Sample passages from the source itself — these reveal the original voice's actual register, sentence length, and technical tone, which must survive the restructure

Also load `.claude/commands/cmo/content/writing.md` for the universal **AI-tell anti-patterns** list (lines 471–481). These kill any voice, not just Hanna's — enforce them on every rewrite regardless of target.

### Stage 3 — Identify the implied page question

Extract the source's H1 and intro (first 150 words). What single question is this page trying to answer? Write it as a literal user query.

If the source serves multiple distinct questions, pick the primary one (highest-value intent — usually the shopping-intent variant). Flag the others for a separate page; do not try to fix multi-intent bloat in the rewrite itself.

### Stage 4 — Generate the restructure plan

Draft a structured plan document. Do not write any section copy yet except the first-150-word front-load preview.

**Plan must include:**

1. **Pre-audit scorecard** — copy from `pre-audit/*.md`
2. **Implied page question** — the literal user query
3. **Proposed new H1** — definitive form (not question form for H1)
4. **Proposed H2 set** — `old → new` mapping table. Target ≥60% of H2s in question form per Framework 02 Signal 2
5. **Draft first 150 words** — the front-loaded answer. This is the only copy drafted at plan stage; it shows how the voice will land
6. **Section-by-section transformation plan** — for each source section, note: keep as-is / rewrite opener for definitiveness / merge with X / split / delete / new section. One-liner per section
7. **Length budget projection** — current word count vs target (≤120%)
8. **Entities + numbers table** — everything `extract-facts` pulled. Mark any that will be dropped with explicit rationale (e.g., "drop '2017 — background context no longer relevant; no replacement claim")
9. **Preserve-flagged sections** — quote them verbatim and mark "UNCHANGED"
10. **YMYL flag** — if set, repeat the clinical-accuracy constraint

### Stage 5 — Checkpoint (GATE — NON-NEGOTIABLE)

Post the plan in chat. Wait for the operator's explicit response:
- **"go"** / **"approved"** → execute
- **"change X"** → revise plan, repost, wait again
- **"stop"** → write plan to `<slug>_plan.md` and exit cleanly

Do NOT proceed to execution without explicit approval. The rewrite burns cycles — a bad plan reviewed at this gate saves more than a bad rewrite caught at post-audit.

### Stage 6 — Execute the rewrite

Write the rewrite as `<slug>_restructured.md`. Rules:

**Structural:**
- H1 in definitive form
- ≥60% of H2s in question form (target 100% where natural)
- First 30% of content answers the implied question directly (definitional "X is Y" pattern)
- Each H2 section is self-contained — remove "as mentioned above", "this", "these" cross-refs
- Front-load each paragraph: high-info sentence in the middle or early, not buried

**Claims and facts:**
- Preserve every entity from the facts list (case-insensitive substring match counts)
- Preserve every number from the facts list verbatim (`44.2%` stays `44.2%`, not "about 44%")
- Do NOT introduce any new number. If a claim needs quantification, leave it unquantified
- For YMYL content: do NOT modify any clinical / legal / financial claim. Restructure the prose *around* the claim; the claim itself is inviolable
- Preserve-flagged sections go in unchanged

**Voice:**
- Universal anti-patterns (`writing.md:471-481`) — zero tolerance
- No em-dashes (grep-verifiable)
- No filler phrases ("when it comes to", "in today's landscape", "it's important to note")
- No perfectly parallel bullet lists
- No rhetorical-question chains after em-dashes
- Match the source's register — a clinical page stays clinical; a marketing page keeps its energy

**Length:**
- Target ≤120% of source word count
- If running long during execution, tighten in real time — do not emit over the soft ceiling and ask later
- Hard fail at 150% — if the rewrite needs that much, the plan was wrong; back up

**Inline change markers** — use `<!-- REWRITTEN: <short note> -->` ONLY for structural or claim-level changes:
- New or substantially reworded H2
- Section-level restructures (merges, splits, reorders)
- Section deletions (marker at the previous heading boundary)
- Any passage where a claim's phrasing changed, even if the fact stayed the same

Do NOT mark sentence-level cosmetic edits inline (hedging → definitive, filler removal, readability polish). Those go in `<slug>_changes.md` only.

### Stage 7 — Post-audit + validation report

```bash
python3 tools/geo_restructure_diff.py diff-report \
    --source <source> \
    --rewrite .tmp/geo/content-restructure/<slug>/<slug>_restructured.md \
    --output .tmp/geo/content-restructure/<slug>/
```

This writes `<slug>_audit_diff.md` with:
- Verdict (PASS / PASS WITH CAVEATS / BELOW TARGET / FAIL)
- Pre/post overall scores + per-signal delta table
- Length-budget status
- Number preservation — dropped and **added** (added = potential hallucination)
- Entity preservation rate
- Quoted claims from source (for manual paraphrase-drift check)
- YMYL status
- Voice markers diff (em-dashes, hedging, filler, parentheticals, sentence-starter variety, avg sentence length)
- Section mapping (source H2 → rewrite H2 with word overlap)

Tool exit codes:
- **0** — PASS (net ≥+15, no regressions, no added numbers, length in budget)
- **1** — BELOW TARGET (net <+15 or has signal regressions) — revise before shipping
- **2** — FAIL (added numbers = potential hallucination, or length out of hard bounds) — stop and fix

### Stage 8 — Voice gate (before declaring done)

Run BOTH:

**Universal AI-tell gate (always):**
- [ ] Zero em-dashes (post count from `audit_diff.md` voice markers table)
- [ ] No filler phrases (post count = 0)
- [ ] No "It was missing something critical" / "What I found surprised me" teasers
- [ ] No perfect parallel bullet lists
- [ ] No rhetorical-question chains after em-dashes
- [ ] No spec-sheet before/after comparison formatting in personal posts

**Voice-specific gate (conditional on the voice profile):**

IF voice profile = `brand/voice-synthesis.md` (Hanna's personal voice):
- Run the full Pre-Publish Voice Audit from `.claude/commands/cmo/content/writing.md:774-828` — Emily DOs/DON'Ts, Step 2 scorecard, report "X/10 DOs hit, Y DON'Ts triggered" in chat
- Required: parentheticals ≥4, at least one named framework, a recurring villain/shorthand, tension-driven opener, warmth in corrective lines

ELSE (client content with its own voice):
- Run a **voice-consistency diff**: compare sentence length distribution, first/second/third person balance, technical register (clinical vs conversational), and hedging frequency between the source and the rewrite
- If the rewrite changes the source's voice profile by >25% on any axis, flag in chat and hold before delivering
- Do NOT apply Hanna's Emily DOs to client content — a medical content page doesn't get parenthetical asides just because the rubric says so

Post the voice gate result in chat alongside the post-audit verdict.

### Stage 9 — Write changes rationale

Write `<slug>_changes.md`:
- Section-by-section: what changed, why (cite Framework 02 principle), what was preserved
- Voice-preservation notes
- Open questions flagged for human reviewer (e.g., "I changed 'might' to 'is' in paragraph 3 — verify clinical accuracy")
- Explicit list of anything from the facts table that was dropped and why

### Stage 10 — Surface summary in chat

Post inline:

> **Restructure complete — `<slug>`**
>
> - **Audit:** pre `X`/100 → post `Y`/100 (**net +Z**)
> - **Regressions:** `<list or "none">`
> - **Preservation:** `E`% entities, `N` numbers dropped, **`A` numbers added (hallucination check required if >0)**
> - **Length:** `W` words (`R`x of source)
> - **Voice gate:** `<pass/fail + short detail>`
> - **YMYL:** `<flagged + category | not flagged>`
>
> **Files:**
> - `<slug>_restructured.md` — rewrite ready for review
> - `<slug>_audit_diff.md` — validation report
> - `<slug>_changes.md` — section-by-section rationale
>
> **Next:** operator reviews rewrite. If approved, move to `clients/<client>/content/<slug>.md` or the client's CMS. Do NOT auto-publish.

## Output

### Files produced

| File | Purpose |
|---|---|
| `pre-audit/<slug>_audit.md` | Baseline Framework 02 scorecard |
| `facts.json` | Numbers, entities, quoted claims from source (preservation target) |
| `ymyl_report.json` | YMYL classification output |
| `<slug>_plan.md` | Restructure plan (written at checkpoint; archived whether approved or not) |
| `<slug>_restructured.md` | The rewrite, ready for CMS paste after review |
| `<slug>_audit_diff.md` | Pre/post scorecard + preservation + voice + length + section mapping |
| `<slug>_changes.md` | Section-by-section rationale + open questions for reviewer |

### Storage

- Working files: `.tmp/geo/content-restructure/<slug>/` (disposable)
- Approved rewrite → operator moves to `clients/<client>/content/<slug>.md` or the CMS

## Acceptance criteria for "done"

- [ ] Pre-audit run and baseline scorecard saved
- [ ] Facts extracted (numbers + entities + quoted claims) and shown at checkpoint
- [ ] YMYL gate triggered for medical/legal/financial content with explicit operator confirmation before execution
- [ ] Restructure plan posted; operator-approved before execution (no silent execution)
- [ ] Post-audit shows net ≥+15 points on Framework 02 overall score
- [ ] No signal regresses post-rewrite (any regression flagged in chat)
- [ ] Zero added numbers in rewrite (or every addition explicitly justified and acknowledged by operator)
- [ ] Entity preservation rate ≥90% (or dropped entities explicitly justified)
- [ ] Length within budget (50% floor, 120% soft ceiling, 150% hard fail)
- [ ] Voice gate passes — universal AI-tells (always) + voice-specific (conditional on profile)
- [ ] First 30% of rewrite directly answers the implied page question
- [ ] ≥60% of H2s in question form
- [ ] Preserve-flagged sections are unchanged (byte-for-byte)
- [ ] SEO signals preserved — canonical tags, internal links, schema markup documented in changes.md for the CMS paste step (the rewrite is markdown; the CMS render must re-apply these)
- [ ] All outputs in the right directories

## CLI cheat sheet

```bash
# Stage 1: pre-audit
python3 tools/geo_audit.py --url https://example.com/page --output .tmp/geo/content-restructure/slug/pre-audit/

# Stage 1: facts
python3 tools/geo_restructure_diff.py extract-facts \
    --source https://example.com/page \
    --output .tmp/geo/content-restructure/slug/

# Stage 1: YMYL gate (exit 10 = YMYL detected)
python3 tools/geo_restructure_diff.py detect-ymyl \
    --source https://example.com/page \
    --output .tmp/geo/content-restructure/slug/

# Stage 7: post-audit + preservation + voice + length + section map
python3 tools/geo_restructure_diff.py diff-report \
    --source https://example.com/page \
    --rewrite .tmp/geo/content-restructure/slug/slug_restructured.md \
    --output .tmp/geo/content-restructure/slug/

# Local markdown input (also supported)
python3 tools/geo_restructure_diff.py extract-facts \
    --source clients/acme/content/old-page.md \
    --output .tmp/geo/content-restructure/old-page/
```

## Out of scope (deferred to V2)

- **Auto-publishing to CMS** — V1 ends with a markdown draft for human review; publishing is a separate workflow
- **Multi-page batch restructure** — V1 is one page at a time; batch via shell loop if needed. A dedicated batch mode is V2
- **A/B variant generation** — V2 (generate 2-3 rewrites for split testing)
- **Image / asset suggestions** — V2 (e.g., "add a diagram of X here for chunk independence")
- **Translation / localization** — V2
- **Schema markup generation** — V2; V1 documents existing schema in changes.md for manual re-application
- **Automated voice-profile loader** — V1 reads a single file path; a registry that auto-picks the right profile for a client is V2
- **SEO signal re-application to the rewrite** — V1 produces markdown; canonical / internal links / schema must be re-applied by the CMS step

## Risks + operating notes

- **Voice drift is the #1 risk.** The structured-briefing format can sound robotic if applied mechanically. Voice gate is the primary defense; operator checkpoint is the secondary
- **Clinical / factual hallucination.** For YMYL content, the hard rule is: restructure prose around claims; never modify claims themselves. The number-preservation check catches most of this; paraphrase-drift on quoted claims is the operator's last-mile review
- **SEO regression.** Markdown drafts don't carry canonical tags or internal links. The CMS paste step must re-apply these — `changes.md` enumerates what was on the source so nothing drops
- **Over-fitting to AI.** Pages restructured for AI can feel weird to humans. Read the rewrite out loud at least once before approval
- **Entity drop on short-word matches.** The preservation check does case-insensitive substring + head-fallback. If you see a dropped entity that's actually preserved (e.g., "Honeycomb Inc." → "Honeycomb"), it's a false positive — verify manually, don't rewrite to satisfy the tool

## References

- `research/geo-aeo/skills/06_content-restructure.md` — original spec
- `research/geo-aeo/frameworks/02_citation-mechanics.md` — the rewrite spec (5 content characteristics, Ski Ramp, chunk independence)
- `research/geo-aeo/frameworks/01_aeo-playbook.md` — where this fits in the 7-step playbook (Step 4)
- `research/geo-aeo/frameworks/04_seo-geo-integration.md` — don't-break-SEO gate + 5 high-risk tactics
- `brand/voice-synthesis.md` — Hanna's personal voice profile
- `.claude/commands/cmo/content/writing.md:471-481` — universal AI-tell anti-patterns
- `.claude/commands/cmo/content/writing.md:774-828` — Pre-Publish Voice Audit (Hanna-specific)
- `tools/geo_audit.py` — pre/post scoring engine (`audit_url`, `audit_html`)
- `tools/geo_restructure_diff.py` — facts extraction, YMYL gate, diff-report
- Upstream: `/cmo/geo/audit` — uses the same Framework 02 rubric
- Downstream: `/cmo/geo/share-of-answers` rerun 4+ weeks after publish to measure citation lift (Framework 01 Step 7)
