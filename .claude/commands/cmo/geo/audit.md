# Skill: /cmo/geo/audit

Audit a site's current GEO (Generative Engine Optimization) state. Walks a non-expert operator through pulling data from every relevant source, runs a technical citation-worthiness audit on priority URLs, and synthesizes findings into a diagnostic that feeds `/cmo/geo/plan`.

**Default scope:** B2B SaaS companies selling to mid-market and enterprise buyers.

**Two performance goals assessed:**
- **Goal A — Mentions:** brand mentions in AI answers (share of voice)
- **Goal B — Shopping-intent share:** brand citations on shopping-intent prompts (pipeline metric)

**Three stages:**
- **Stage 0 — Strategic Intake:** novice-friendly walkthrough to pull data from 6 sources
- **Stage 1 — Technical Page Audit:** per-URL citation-worthiness scoring via `tools/geo_audit.py`
- **Stage 2 — Synthesis:** unified diagnostic combining intake data + per-page findings

## When to use

- Onboarding a new client to GEO — establishing the full baseline before any optimization work
- Annual or quarterly re-audit after a major site overhaul, rebrand, or content migration
- When `/cmo/geo/share-of-answers` shows weak citation rates and you need to diagnose why
- Before building a `/cmo/geo/plan` — the plan skill expects this diagnostic as input
- When a client asks "how AI-ready is our site?" and you need a structured answer

## Inputs (asked at intake)

| Input | Required? | Default |
|---|---|---|
| Client identifier (for output path) | Yes | — |
| Primary domain | Yes | — |
| Competitor domains (3–5) | No | Claude proposes from category; user confirms |
| GSC export (queries + pages CSVs) | Stage 0 | User pulls manually with guided instructions |
| GA4 landing pages CSV | Stage 0 | User pulls manually with guided instructions |
| Ahrefs/Semrush top pages CSV(s) | Stage 0 | User pulls manually with guided instructions |
| Priority URLs (10–20) | No | Auto-selected from GSC + GA4 data in Stage 0 |
| AirOps brand kit ID | No | Auto-detected via `list_brand_kits` if available |
| Existing SoA `runs.csv` | No | Cross-referenced if available; not required |

## Workflow

### Stage 0 — Strategic Intake

This stage assumes the operator has never done SEO or AEO before. Every instruction includes click-by-click guidance. Work through each data source in order. After each, confirm receipt or mark as skipped.

---

#### Source 1: Google Search Console — 90-day Performance export

**What it gives us:** Which queries send organic traffic today, which pages rank for what, CTR baseline. This is the ground truth for what Google already associates with the site.

**How to pull it (click-by-click):**

- [ ] 1. Open [search.google.com/search-console](https://search.google.com/search-console) in your browser
- [ ] 2. In the top-left dropdown, select the property (domain) you want to audit. If you see both `http://` and `https://` versions, pick the `https://` one. If you see a "Domain" property, prefer that — it covers all subdomains.
- [ ] 3. In the left sidebar, click **Performance** → **Search results**
- [ ] 4. At the top of the chart, you'll see date range filters. Click the date range and select **Last 3 months**
- [ ] 5. Make sure all 4 metrics are toggled ON above the chart: **Total clicks**, **Total impressions**, **Average CTR**, **Average position** (click each colored box to toggle)
- [ ] 6. Below the chart you'll see a table. It defaults to the **Queries** tab.
   - Click **Export** (top-right of the table, icon looks like a download arrow) → **Download CSV**
   - Save the file as `gsc-queries-90d.csv`
- [ ] 7. Now click the **Pages** tab in that same table
   - Click **Export** → **Download CSV**
   - Save as `gsc-pages-90d.csv`
- [ ] 8. Share both CSV files here

**If you don't have GSC access:** Tell me and we'll skip this source. We can partially reconstruct from Ahrefs/Semrush data, but CTR baseline will be missing.

---

#### Source 2: Google Analytics 4 — Landing Pages export

**What it gives us:** Which pages drive engaged sessions and conversions. This is the baseline for Goal B — we need to know which pages actually generate pipeline today.

**How to pull it (click-by-click):**

- [ ] 1. Open [analytics.google.com](https://analytics.google.com)
- [ ] 2. Make sure you're in the correct GA4 property (check the property name in the top-left)
- [ ] 3. In the left sidebar, click **Reports**
- [ ] 4. Click **Engagement** → **Landing page** (sometimes listed as "Pages and screens" — look for the one that shows landing page paths)
- [ ] 5. In the top-right corner of the report, click the date range. Set it to **Last 90 days** (custom range or use the preset if available). Click **Apply**.
- [ ] 6. If you have conversion events set up (e.g., `generate_lead`, `sign_up`, `purchase`), check that the conversions column is visible. If not, click the pencil icon to customize the report and add it.
- [ ] 7. Set rows to show at least 50 (bottom of the table, "Show rows" dropdown)
- [ ] 8. Click the **Share** icon (top-right, looks like a share/export symbol) → **Download file** → **Download CSV**
- [ ] 9. Save as `ga4-landing-pages-90d.csv`
- [ ] 10. Share the CSV here

**If you don't have GA4 access:** Tell me. We'll use GSC pages data as a proxy, but conversion attribution will be missing from the diagnostic.

---

#### Source 3: Ahrefs or Semrush — Top Pages + Competitor Top Pages

**What it gives us:** Keyword rankings beyond what GSC shows (GSC caps at 1000 rows), plus competitor page data for shopping-intent terms. This is how we find the gaps.

**How to pull it (Ahrefs — click-by-click):**

- [ ] 1. Open [app.ahrefs.com](https://app.ahrefs.com)
- [ ] 2. Paste the client's domain into the **Site Explorer** search bar and hit Enter
- [ ] 3. In the left sidebar, click **Top pages** (under "Organic search")
- [ ] 4. You'll see a table of pages ranked by estimated organic traffic. Click **Export** (top-right) → **CSV** → **Full export** (not "Top 1,000")
- [ ] 5. Save as `ahrefs-top-pages-<domain>.csv` (e.g., `ahrefs-top-pages-acme.csv`)
- [ ] 6. **Repeat for each competitor domain** — paste competitor domain into Site Explorer → Top pages → Export
   - Save each as `ahrefs-top-pages-<competitor>.csv`
- [ ] 7. Share all CSV files here

**Semrush alternative:**
- [ ] Open Semrush → Domain Overview → paste domain → Organic Research → Pages tab → Export
- [ ] Save as `semrush-top-pages-<domain>.csv`

**If you don't have Ahrefs or Semrush access:** Tell me. We'll work with GSC data only, but competitor gap analysis will be limited.

---

#### Source 4: robots.txt + llms.txt inspection

**What it gives us:** Whether the site is letting AI crawlers in. If GPTBot, ClaudeBot, or PerplexityBot are blocked, the site is actively preventing AI citation — that's a Stage 1 finding with immediate action.

**How this works:** I'll fetch these automatically. You just need to confirm.

- [ ] 1. I'll check `https://<domain>/robots.txt` — looking for rules about:
   - `GPTBot` (OpenAI's crawler)
   - `ClaudeBot` (Anthropic's crawler)
   - `PerplexityBot` (Perplexity's crawler)
   - `Googlebot-Extended` (Google's AI training crawler — distinct from Googlebot)
   - `CCBot` (Common Crawl — feeds many AI training sets)
- [ ] 2. I'll check `https://<domain>/llms.txt` — a newer convention where sites provide AI-friendly site maps
   - If 404: that's fine, most sites don't have this yet. It goes in the recommendations.
- [ ] 3. I'll report what I find. You confirm if it matches your understanding.

**What "good" looks like:**
- `GPTBot`, `ClaudeBot`, `PerplexityBot` are NOT blocked (no `Disallow: /` rules for them)
- `llms.txt` exists with key pages listed (bonus, not required)
- No blanket `User-agent: * / Disallow: /` that blocks everything

---

#### Source 5: AirOps AEO brand kit (if enabled)

**What it gives us:** Existing prompt performance data, citation tracking, and AI visibility scores from AirOps' AEO platform. If the client has this, it's the richest single source.

**How this works:** I'll check automatically using AirOps MCP tools.

- [ ] 1. I'll call `list_brand_kits` to find brand kits with `aeo_enabled: true`
- [ ] 2. If a matching brand kit exists, I'll pull:
   - `get_insights_settings` — AEO configuration, tracked competitors, persona list
   - `list_aeo_prompts` — prompts being tracked
   - `list_aeo_citations` — where the brand is being cited
   - `list_pages` — pages being monitored with AI visibility scores
- [ ] 3. I'll summarize what's available and cross-reference with the other sources

**If no AirOps brand kit exists:** Totally fine. We skip this source. The audit works without it — AirOps data is additive.

---

#### Source 6: Priority URL selection

**What it gives us:** The 10–20 pages that matter most for GEO. Stage 1 audits these pages individually.

**If you already have a list of priority URLs:** Share them and we'll use those.

**If you don't have a list:** I'll build one from the data we just collected:

- [ ] 1. **Top 10 landing pages by conversions** from GA4 (Goal B — these pages generate pipeline)
- [ ] 2. **Top 10 pages by clicks on shopping-intent queries** from GSC (queries containing "best," "vs," "alternative," "pricing," "review," "compare," "top," "tools for")
- [ ] 3. **Pages ranking for category keywords** from Ahrefs/Semrush (head terms the brand should own)
- [ ] 4. **Deduplicate** the union of those three lists
- [ ] 5. Present the final 10–20 URL list for your approval before proceeding to Stage 1

---

#### Data inventory checkpoint

After completing all 6 sources, I'll produce `data-inventory.md` summarizing:

| Source | Status | File(s) | Notes |
|---|---|---|---|
| GSC Performance | Pulled / Skipped | `gsc-queries-90d.csv`, `gsc-pages-90d.csv` | — |
| GA4 Landing Pages | Pulled / Skipped | `ga4-landing-pages-90d.csv` | — |
| Ahrefs/Semrush | Pulled / Skipped | `ahrefs-top-pages-*.csv` | — |
| robots.txt / llms.txt | Checked | — | Inline findings |
| AirOps AEO | Pulled / Skipped / N/A | — | Brand kit ID if applicable |
| Priority URLs | Confirmed | — | N URLs selected |

**Gate:** Stage 1 does not start until you've confirmed the priority URL list. If we have zero usable data sources, I'll flag that the audit can't produce a meaningful diagnostic and recommend what access to get first.

---

### Stage 1 — Technical Page Audit

For each priority URL, run `tools/geo_audit.py`. The tool handles:

1. **Technical checks:**
   - robots.txt / meta robots: is the page crawlable by AI bots?
   - Server-side rendering (SSR) vs. client-side only: can crawlers see the content?
   - Schema.org structured data: `FAQPage`, `HowTo`, `Product`, `Organization`, `Article`, `BreadcrumbList`
   - Canonical URL: is it self-referencing? Any conflicts?
   - `noindex` / `nofollow` directives
   - Page load performance (if measurable)
   - `llms.txt` inclusion: is this page listed?

2. **Content scoring against Framework 02's 8-signal citation-worthiness rubric:**
   - Structural clarity (headings, lists, logical flow)
   - Factual density (statistics, named entities, specific claims)
   - Source attribution (links to primary sources, named studies)
   - Freshness signals (dates, recency markers, "updated" timestamps)
   - Unique value (proprietary data, original research, expert quotes)
   - Entity completeness (does the page establish who/what the brand is?)
   - Comparative positioning (does it naturally address "vs" and "alternative" queries?)
   - Answer-readiness (can an AI extract a clean, citable answer from this page?)

3. **High-risk tactic detection per Framework 04:**
   - Keyword stuffing patterns
   - Hidden text / cloaking signals
   - Doorway page indicators
   - Thin content with aggressive internal linking
   - Any tactic flagged as `[GEO+ but SEO-]` that could trigger penalties

4. **Per-URL scorecard output:**
   - Overall citation-worthiness score (0–100)
   - Individual signal scores
   - Prioritized fix list with each recommendation labeled:
     - `[SEO+/GEO+]` — helps both traditional search and AI citation (do first)
     - `[GEO+ only]` — helps AI citation, neutral for SEO
     - `[GEO+ but SEO-]` — helps AI citation but may hurt SEO (proceed with caution, requires explicit approval)

### Stage 2 — Synthesis

Combine Stage 0 data + Stage 1 per-page findings into `diagnostic.md`:

1. **Executive summary** — 3–5 bullet current-state assessment against the two goals

2. **Goal A baseline + gap analysis:**
   - Current mention rate (from AirOps or SoA data if available; "unmeasured" if not)
   - Content coverage: how many of the category's key topics does the site have pages for?
   - Citation-worthiness distribution: how many priority pages score above/below the threshold?

3. **Goal B baseline + gap analysis:**
   - Current shopping-intent share (from AirOps or SoA data if available)
   - Conversion page citation-readiness: are the pages that generate pipeline also citable?
   - Competitor citation dominance: who shows up on shopping-intent queries?

4. **Top 10 shopping-intent queries where competitors dominate** — pulled from GSC + Ahrefs data, cross-referenced with SoA runs.csv if available

5. **Per-page scorecard roll-up:**
   - Summary table: URL | Score | Top 3 issues | Quick wins
   - Pages grouped by tier: Ready (80+), Needs work (50–79), Not citable (<50)

6. **Priority-ranked findings list:**
   - Each finding tagged with goal relevance (A, B, or both)
   - Each finding tagged with effort level (quick win / medium / heavy lift)
   - Findings are observations and gaps — NOT initiatives. Initiatives come from `/cmo/geo/plan`.

7. **Required gating language:** The diagnostic ends with the SEO/GEO investment gate (Framework 04) and the 5 fake-case-study warnings (Framework 03). These are non-negotiable — they discipline interpretation.

### Cross-reference with Share of Answers (optional)

If the user has previously run `/cmo/geo/share-of-answers` and has a `runs.csv`:

- [ ] Ask: "Have you run `/cmo/geo/share-of-answers` yet? If so, share the `runs.csv` path."
- [ ] For each audited URL: check if it appears in any SoA citation URLs
- [ ] Enrich the diagnostic: pages that ARE cited get a "currently cited by [surface]" flag; pages that AREN'T cited despite high traffic get a "citation gap" flag
- [ ] This is additive — the audit produces a complete diagnostic with or without SoA data

## Output

### Files produced

| File | Purpose |
|---|---|
| `data-inventory.md` | Stage 0 checkpoint — which sources were pulled, which were skipped |
| `page-scorecards/` | Stage 1 — one markdown file per audited URL with full scorecard |
| `diagnostic.md` | Stage 2 — unified diagnostic combining all findings |

### Storage

`clients/<client>/geo/audit/<YYYY-MM-DD>/`

All input CSVs the user provides should also be saved to this directory for reproducibility.

## Acceptance criteria for "done"

- [ ] Stage 0: all 6 data sources addressed (pulled or explicitly skipped with reason)
- [ ] Stage 0: `data-inventory.md` written with source status table
- [ ] Stage 0: priority URL list confirmed by user before Stage 1 begins
- [ ] Stage 1: `tools/geo_audit.py` run on every priority URL
- [ ] Stage 1: per-URL scorecards written with citation-worthiness scores and labeled recommendations
- [ ] Stage 1: no high-risk `[GEO+ but SEO-]` tactics recommended without explicit user approval
- [ ] Stage 2: `diagnostic.md` includes all 7 sections (exec summary through gating language)
- [ ] Stage 2: every finding tagged with goal relevance (A/B/both) and effort level
- [ ] Stage 2: findings are observations — NOT initiatives (those come from `/cmo/geo/plan`)
- [ ] Stage 2: gating warnings from Framework 03 + Framework 04 included verbatim
- [ ] If SoA `runs.csv` provided: cross-reference completed, citation gaps flagged
- [ ] All outputs saved to `clients/<client>/geo/audit/<YYYY-MM-DD>/`

## CLI cheat sheet

```bash
# Run Stage 1 technical audit on a single URL
python3 tools/geo_audit.py --url https://example.com/page --output .tmp/geo/test/

# Run Stage 1 on a list of priority URLs
python3 tools/geo_audit.py \
    --urls clients/acme/geo/audit/2026-04-17/priority-urls.txt \
    --output clients/acme/geo/audit/2026-04-17/page-scorecards/

# Run with competitor comparison
python3 tools/geo_audit.py \
    --urls clients/acme/geo/audit/2026-04-17/priority-urls.txt \
    --competitors "competitor1.com,competitor2.com,competitor3.com" \
    --output clients/acme/geo/audit/2026-04-17/page-scorecards/
```

## Out of scope (deferred to V2)

- Automated GSC / GA4 API data pulls (V1 requires manual CSV export)
- Automated Ahrefs / Semrush API integration
- Continuous monitoring / scheduled re-audits (wrap with launchd once cadence is proven)
- Competitor page-level audits (V1 audits the client's pages; competitor data is for gap analysis only)
- AI-generated fix implementations (the audit identifies problems; fixes are a separate workflow)

## References

- `research/geo-aeo/frameworks/02_citation-mechanics.md` — the citation-worthiness rubric (8 signals)
- `research/geo-aeo/frameworks/04_seo-geo-integration.md` — SEO/GEO investment gate + high-risk tactic list
- `research/geo-aeo/frameworks/01_aeo-playbook.md` — operational context + Product Questions filter
- `research/geo-aeo/frameworks/03_measurement-framework.md` — Goal A / Goal B definitions + gating warnings
- `tools/geo_audit.py` — companion scoring tool for Stage 1
- Upstream skill: `/cmo/geo/share-of-answers` → optional `runs.csv` for citation cross-reference
- Downstream skill: `/cmo/geo/plan` → consumes `diagnostic.md` to build the optimization plan
