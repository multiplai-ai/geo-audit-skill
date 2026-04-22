# Framework 02 — Citation Mechanics

**Scope:** The science of WHY AI systems cite some content over others. Used as design constraints for content production. Vertical-agnostic.

**Out of scope:** Operational playbook (→ Framework 01), measurement (→ Framework 03).

**Primary sources:** Kevin Indig — `articles/05_growth-memo_how-ai-pays-attention.md`, `articles/06_growth-memo_how-ai-picks-sources.md`, `articles/07_growth-memo_shorter-content-wins.md`, `articles/08_growth-memo_influence-ai-responses.md`. Academic — `articles/14_arxiv_geo-paper.md`. Statistical confidence: P-value < 0.0001 across Indig's 1.2M-citation analysis.

---

## The two questions citation mechanics answers

1. **Which pages does the AI retrieve?** (source selection — Framework 02a)
2. **Which passages within those pages does the AI cite?** (passage extraction — Framework 02b)

These are distinct mechanisms. Optimizing for one without the other leaves citation rate on the table.

---

## 02a — Source Selection (which pages get pulled)

### Signal 1: Google ranking still dominates retrieval
- Pages at Google #1 → cited by ChatGPT 43.2% of the time
- Pages beyond top 20 → 12.3%
- **3.5x advantage for #1 ranking**

But: ranking is necessary, not sufficient. AI retrieves ~6x more pages than it cites. 85% of retrieved pages go uncited.

**Design implication:** SEO is the foundation. Cannot win AEO with weak organic rankings. (See Framework 04 for the don't-break-SEO-to-win-GEO principle.)

### Signal 2: Domain concentration is high (but vertical-dependent)
- ~30 domains control 67% of citations within any topic
- Top 10 domains capture 46% of citations
- BUT: concentration varies by vertical

| Vertical | Top-10 share | Concentration |
|---|---|---|
| Education | 59.5% | High |
| Finance | (high — front-loaded data wins) | High |
| Crypto | (high — tech docs + comparison sites) | High |
| Healthcare | 13.0% | Low (most fragmented) |

**Design implication:** In high-concentration verticals, you must either be a top-10 domain or get cited by one. In low-concentration verticals (healthcare), there's room for new entrants.

### Signal 3: Length thresholds (vertical-specific)
- Pages >20K characters: average 10.18 citations
- Pages <500 characters: average 2.39 citations
- Dramatic jump between 5K-10K words (~2x increase)
- BUT: optimal length differs by vertical
  - **Finance** — peaks at 5K-10K then DROPS sharply (front-loaded data wins)
  - **Education** — rewards length consistently

**Note:** Indig's other study found 500-2K words wins for ChatGPT specifically. Reconcile: longer pages get cited more often *across many prompts*; shorter focused pages get cited more reliably *for a specific prompt*. Both are true. Strategic answer: **focused pages for specific intent + comprehensive guides for category-level breadth.**

### Signal 4: Citation breadth > raw citation count
- 67% of cited URLs appear in only one prompt
- Top 4.8% of URLs (cited 10+ times) are category-level guides addressing multiple query intents
- Evergreen pages covering "what is it," "how to choose," and "pricing" in one URL drive disproportionate reach

**Design implication:** Build BOTH — focused single-intent pages for direct match + category-level guides for breadth.

---

## 02b — Passage Extraction (which passages within a cited page get quoted)

### The "Ski Ramp" — positional weighting
- **First 30% of content = 44.2% of all citations**
- Middle 30-70% = 31.1%
- Final 33% = 24.7%

**Design implication:** Front-load conclusions. Don't bury the answer. Replace narrative-tension structure with structured-briefing structure.

### Within-paragraph behavior
- 53% of citations come from paragraph **midpoints** (not first sentence)
- 24.5% from first sentences; 22.5% from final
- AI seeks highest "information gain" regardless of sentence position

**Design implication:** Every paragraph should have a high-information sentence in the middle, not just at the start. Don't pad paragraph midpoints with throwaway transitions.

---

## The Five Content Characteristics That Drive Citation

These are the highest-confidence design constraints in the corpus. From Indig's 11,022-citation linguistic analysis.

### 1. Definitive language
- "X is Y" structure → **36.2% citation rate**
- Vague phrasing → **20.2%**
- Vector databases treat "is" as strong connective bridge for definitions

| Pattern | Use | Avoid |
|---|---|---|
| Definitional opening | "Demo automation is the process of..." | "In this fast-paced world..." |
| Direct attribution | "The PARTNER trial showed X" | "Studies have suggested that..." |
| Concrete claims | "TAVR is indicated when..." | "Many factors influence when to consider TAVR..." |

### 2. Conversational Q&A structure
- Text containing question marks → cited **2x more often** (18% vs 8.9%)
- 78.4% of question-based citations come from H2 headings
- Optimal pattern: H2 = user query; following paragraph = direct answer

| Pattern | Use | Avoid |
|---|---|---|
| H2 format | "When is TAVR indicated?" | "Indications for transcatheter aortic valve replacement" |
| First sentence | "TAVR is indicated for severe symptomatic aortic stenosis when..." | "There are several indications to consider..." |

### 3. Entity richness (proper noun density 20.6%)
- Heavily cited text contains proper nouns at **20.6% frequency**
- Standard English averages **5-8%**
- Specific entities reduce LLM perplexity; generic phrasing increases it

| Pattern | Use | Avoid |
|---|---|---|
| Specific names | "Salesforce, HubSpot, and Pipedrive" | "choose a good tool" |
| Trial / guideline IDs | "ACC/AHA 2020 guideline; PARTNER 3 trial" | "current guidelines suggest" |
| Drug brand + generic | "apixaban (Eliquis)" | "anticoagulation therapy" |

### 4. Balanced sentiment (subjectivity score ≈ 0.47)
- Sweet spot between pure objectivity (0.0) and pure opinion (1.0)
- Combines verifiable facts with analytical insight

| Pattern | Use | Avoid |
|---|---|---|
| Fact + analysis | "iPhone 15 features the A16 chip (fact); its low-light photography makes it superior for content creators (analysis)" | "iPhone 15 has the A16 chip" (pure fact) OR "iPhone 15 is the best phone" (pure opinion) |

### 5. Business-grade readability (Flesch-Kincaid Grade 16)
- College-level (Grade 16) outperforms academic density (Grade 19.1)
- Shorter, moderately-long sentences > winding constructions
- Subject-verb-object structures aid extraction

**Design implication:** Clinical accuracy without academic sentence length. Most medical journal abstracts are over-dense. Aim for the readability of a high-quality news explainer (Atlantic, Stat News).

---

## Chunk-Level Retrieval (from Aleyda Solis)

Each section must stand alone. AI extracts passages without surrounding context — if a paragraph requires the previous one to make sense, it loses citation eligibility.

| Pattern | ✅ Use | ❌ Avoid |
|---|---|---|
| Self-contained section | "What is technical SEO? Technical SEO refers to optimizing crawlability and indexability so search engines can effectively access content." | "Technical SEO covers many things. As mentioned earlier, this includes the things we'll discuss below." |

---

## What Doesn't Matter (or matters less than you think)

From Indig's research:
- **Domain authority** — no predictive value once query match is controlled for
- **Word count** as a standalone signal — secondary to query match
- **Heading density** as standalone signal — secondary
- **Coverage of "all" subtopics** — covering 100% of subtopics adds only 4.6 pp over covering none. Moderate coverage outperforms exhaustive.
- **Wikipedia is an outlier** — its scale + structural richness is unattainable; don't model your content on it

---

## The E-GEO Findings (cautionary)

From Columbia's E-GEO research (`articles/08_growth-memo_influence-ai-responses.md`):
- Length and verbosity are dominant levers
- Persuasive tone ("fluff") consistently boosts visibility — even without adding factual substance
- Strategic JSON formatting can manipulate rankings
- Optimization tactics achieved ~90% win rate against baseline in product-query tests

**Cautionary read:** these tactics work *now*, but the research itself notes they're fragile. Same model + minor stylistic tweak can rerank items bottom-to-top. Expect an arms race analogous to Google Panda/Penguin. **Don't build content strategy around manipulation tactics that won't survive the next model update.** Build around the durable signals (definitive language, entity richness, structured Q&A, on-page authority).

---

## Domain-specific variation (from academic GEO paper)

Aggarwal et al. validated:
- The black-box GEO framework boosts visibility up to 40%
- BUT: efficacy varies significantly across domains
- No universal optimization approach — must test per vertical

**Design implication:** Test in your vertical before assuming any tactic transfers. Healthcare and finance behave differently than commerce.

---

## How to apply this framework (for skills)

- **`/geo/audit`** — score a URL against the 5 Content Characteristics + Ski Ramp + Chunk Independence. Use rubric below.
- **`/geo/content-restructure`** — rewrite to maximize Definitive Language + Q&A H2s + Entity Density + Front-loading. Preserve voice; transform form.
- **`/geo/prompt-set-builder`** — use Q&A H2 format from this framework as the prompt template structure.

### Citation-worthiness rubric (proposed for `/geo/audit`)

| Signal | Pass criterion | Weight |
|---|---|---|
| First-30% answer | Direct answer to implied page question in first 30% of content | High |
| Q&A H2s | ≥60% of H2s in question form | High |
| Entity density | Proper nouns ≥15% of word count in body | High |
| Definitive openings | First sentence of each section uses "X is Y" or direct claim | Medium |
| Chunk independence | Each section comprehensible without surrounding context | High |
| Sentiment balance | No section is purely promotional or purely encyclopedic | Medium |
| Readability | Flesch-Kincaid Grade 14-17 | Low |
| Length match | 500-2K words for focused page; 5K+ for category guide | Medium |

---

## Open questions

- The 5 Content Characteristics are validated on Indig's general corpus — vertical-specific weights are unknown. A future study should re-run the analysis on healthcare-only or finance-only prompt sets.
- "Information gain" is operationalized loosely — what specifically makes a paragraph midpoint high-gain vs. low-gain? Worth deeper transcript mining and possibly a small experiment.
- Cross-LLM transfer — research is mostly ChatGPT-centric. Claude/Gemini/Perplexity may weight signals differently (E-GEO research suggests they do).
