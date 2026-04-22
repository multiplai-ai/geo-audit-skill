# Framework 01 — The AEO Playbook

**Scope:** What to actually DO to get cited by ChatGPT, Claude, Gemini, Perplexity, and AI Overviews. Operational steps, vertical-agnostic.

**Out of scope:** Research mechanics (→ Framework 02), measurement (→ Framework 03), guardrails (→ Framework 04).

**Primary sources:** Ethan Smith (Graphite) — `articles/04_lennys_ethan-smith-aeo-playbook.md`, `articles/02_graphite_aeo-is-the-new-seo.md`, `transcripts/01_lennys_ultimate-guide-aeo.md`. Aleyda Solis — `articles/10_aleyda_ai-search-checklist.md`.

---

## The 7-Step Operational Playbook (synthesized from Ethan Smith)

### Step 1 — Build only authentic, original content
**Don't:** Generate content with AI. Detection is 99.4% accurate; AI systems deprioritize derivative material; Google's Scaled Content Abuse policy actively penalizes it.

**Do:** Use AI for research, structure suggestions, and drafting *assistance*. Final published content must reflect a human voice, original data, or proprietary insight.

**Why:** AI models that train on AI-generated content collapse (peer-reviewed phenomenon). LLMs and search engines have learned to filter recursive content.

### Step 2 — Concentrate effort on three core channels
1. **Landing pages** — comprehensive, authoritative pages answering specific questions your audience asks AI
2. **YouTube videos** — heavily cited by AI; provides credibility signals; transcripts are crawlable text
3. **Reddit** — authentic participation; solve real problems; never spam

These three account for the bulk of practical AEO citation opportunities. Other surfaces (Quora, Substack, partner blogs) are secondary.

### Step 3 — Optimize the help center
The single most underutilized AEO surface. Help-center content directly answers product-specific questions users ask AI ("how do I do X with Y?"). When restructured for citation (Q&A format, definitive language), it becomes "the highest-ROI investment" per Smith.

### Step 4 — Structure content for citation
See Framework 02 for the underlying mechanics. Operational checklist:
- **Quotable sections** — discrete, independently valuable claims
- **Originality markers** — proprietary research, unique perspectives, specific examples
- **Authority signals** — credible sources, data, established expertise
- **On-site context** — content lives on your domain (not just third-party)
- **Q&A format** — H2s as physician/buyer questions; paragraphs as direct answers
- **Front-loaded** — first 30% of content gets ~44% of citations

### Step 5 — Build off-site presence
- Contribute to industry publications
- Authentic engagement on Reddit, Quora, niche forums
- Publish on partner blogs / co-authored content
- Earn citations from established media outlets in your category

The principle: most AI answers aggregate citations from multiple sources. Even if your domain isn't cited directly, being mentioned on cited domains creates indirect visibility.

### Step 6 — Track Share of Voice
See Framework 03 for full measurement architecture. Operational minimum:
- Weekly monitoring across ChatGPT, Claude, Gemini, Perplexity
- Citation frequency + positioning (primary vs. tertiary mention)
- Keyword/prompt-level tracking
- Conversion rate analysis from AEO traffic vs. baseline

### Step 7 — Run controlled experiments
- Treated pages vs. untreated control pages (4-week minimum read)
- Test which structures get cited most in your vertical
- Compare conversion rates by source
- Document which channels (Reddit/YouTube/landing pages) drive most citations
- Iterate based on data, not vendor case studies

---

## The Three Core Channels — Tactical Detail

### Reddit
**Authenticity is non-negotiable.** Don't promote your product directly — solve real problems. When users ask questions where your solution genuinely fits, provide helpful context that naturally includes your product.

**Anti-patterns:** Automated posting, fake comments, drive-by promotion. Filtered by Reddit AND by AI systems.

**Why it works:** Reddit threads rank highly in Google (which feeds AI retrieval), and AI systems treat Reddit as a high-trust authentic-voice signal.

### YouTube
- Produce videos demonstrating expertise
- Auto-generated transcripts get crawled — clean transcripts (manual or post-edited) get crawled BETTER
- Title + description with searchable, question-format text
- Topic clarity: "How to X" / "What is Y" videos outperform brand-generic videos

### Landing pages
- One question (or tightly-clustered set of related questions) per page
- Front-loaded direct answer in first 150 words
- 5-8 H2s in question format
- Self-contained sections (chunk-level retrieval — see Framework 02)
- Author/Organization schema; date + last-updated visible
- Comprehensive but not bloated — 500-2,000 words for focused pages; longer only for category guides

---

## The 5% Framework (where impact concentrates)

Ethan Smith's framing: most SEO/AEO work drives minimal impact. The 5% that drives outsized returns is identified through:
1. **Generate ideas** — research trends, interview practitioners, analyze competitor data
2. **Test & evaluate** — controlled experiments with test/control groups
3. **Reproduce** — validate findings across iterations before adopting

Avoid: spending equal effort across all tactics. Concentrate on the few that prove themselves.

---

## The Product Questions Filter

Not all queries surface products in AI answers:
- **High product-presence verticals:** travel, commerce, tech (>50% of queries show products)
- **Low product-presence verticals:** food, news, current events (<50%)
- **Healthcare specifically:** mid-range; depends heavily on whether the query is informational vs. recommendation-seeking

**Implication:** Before investing in AEO for a vertical, sample 50 queries across ChatGPT/Claude/Gemini/Perplexity to confirm products/services appear in answers at all. If they don't, AEO is the wrong tool for that surface.

---

## Aleyda's 10-Item Checklist (operational layer)

Use as a pre-launch checklist for any GEO program:

1. **Audience research** — which AI platforms drive your traffic; conversational query patterns; brand sentiment in AI answers
2. **AI crawlability** — robots.txt allows GPTBot, ClaudeBot, PerplexityBot, Googlebot-Extended; SSR; no noindex on valuable pages; descriptive internal links
3. **Topical breadth + depth** — hub-and-spoke architecture; pillar + cluster pages
4. **Chunk-level retrieval** — one idea per section; self-contained passages; clear H2/H3
5. **Answer synthesis** — direct concise summaries before details; natural Q&A; structured data
6. **Citation-worthiness** — verifiable facts linked to authorities; author credentials + dates; Author/Organization schema
7. **Authoritativeness** — original research; industry coverage; reputable third-party mentions
8. **Multi-modal** — images via clean HTML (not JS-lazy); descriptive alt + captions; HTML tables (not images of tables)
9. **Personalization-resilient** — multiple intents per topic; localized schema; persona-segmented sections
10. **Performance monitoring** — track AI bot crawl patterns, prompt-level citation, sentiment, AI-source referral traffic

---

## How to apply this framework (for skills)

- **`/geo/audit`** — score a URL against Steps 4 + Aleyda's items 2-8. Output: pass/fail per criterion + prioritized fix list.
- **`/geo/content-restructure`** — apply Step 4 + Framework 02's mechanics to rewrite a page. Preserve voice; restructure form.
- **`/geo/citation-network-mapper`** — execute Step 5 systematically: identify the 20-30 domains AI cites for a vertical, then build a target list.
- **Universal:** every skill should reference Step 1 (no AI-generated final content) and Step 7 (require control group framing for any "this works" claim).

---

## Open questions / gaps in this framework

- Vertical-specific weighting — which steps matter more in healthcare vs. SaaS vs. e-commerce? Academic GEO paper notes domain-specific variation but doesn't quantify across verticals.
- Help-center optimization specifics — Smith claims it's the highest-ROI move but specific tactical detail is thin in current corpus. Worth a deeper transcript mine.
- Reddit + compliance-restricted verticals (healthcare, finance) — how authentic participation works when employees can't openly identify themselves.
