# GEO Audit Skill

A Claude Code skill suite for auditing URLs for generative search (GEO/AEO) visibility. Scores pages for AI citation-worthiness, checks whether they actually surface in ChatGPT, Claude, Gemini, and Perplexity, and hands you a prioritized fix list.

Built for startup marketing leads without a $1-2k/mo GEO tracking tool. Free for subscribers to [Marketer in the Loop](https://mktrintheloop.com).

---

## What's in this repo

Six skills covering the end-to-end GEO workflow:

| Skill | Purpose |
|---|---|
| `audit` | Score any URL for citation-worthiness. Flag technical issues. Output prioritized fix list. |
| `prompt-set-builder` | Generate a 50-prompt test set for your vertical (shopping / comparative / informational / decision / recommendation intent). |
| `share-of-answers` | Run the prompt set through ChatGPT + Claude + Gemini + Perplexity. Baseline your AI visibility. |
| `plan` | Synthesize audit + share-of-answers into a prioritized initiative list with revenue model. |
| `citation-network-mapper` | Map which domains AI engines cite in your vertical. Find earned-mention targets. |
| `content-restructure` | Rewrite any URL in structured-briefing format. Voice-preserved, fact-preserved. |

Each skill has a companion Python tool that does the deterministic work. Claude handles the reasoning.

---

## Quick install (5 minutes)

### 1. Copy the files

Clone this repo, then copy the contents into your own Claude Code workspace:

```bash
git clone https://github.com/multiplai-ai/geo-audit-skill.git
cd geo-audit-skill

# Copy the skills, tools, and frameworks into your own workspace
cp -r .claude/commands/cmo/geo/ /path/to/your/workspace/.claude/commands/cmo/
cp tools/geo_*.py /path/to/your/workspace/tools/
cp -r research/geo-aeo/ /path/to/your/workspace/research/
```

The skills reference each other (and the frameworks) with relative paths. Keeping the directory structure intact lets drop-in install work without editing path references.

### 2. Install Python dependencies

```bash
pip install --user anthropic openai google-genai requests beautifulsoup4 readability-lxml textstat tldextract markdown python-dotenv
```

### 3. Add API keys to `.env`

```
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
PERPLEXITY_API_KEY=...
```

You can skip any keys you don't have. The skills adapt to available engines.

### 4. Run your first audit

```bash
python3 tools/geo_audit.py --url https://your-domain.com/your-page --output .tmp/geo/test/
```

You'll get a scorecard in `.tmp/geo/test/` in about 3-5 minutes. Total API cost per run: ~$2-5.

---

## How to use it (daily practice)

1. **Pick one URL a day.** Start with your highest-converting pages. Those lose the most when they're not AI-citable.
2. **Run the audit.** Read the scorecard top to bottom.
3. **Ship the `[SEO+/GEO+]` fixes immediately.** They lift both traditional rankings and AI citations. Zero downside.
4. **Hold the `[GEO+ but SEO-]` fixes for a review.** They can trade SEO for AI visibility. Sometimes the right call, sometimes not. Never ship these without a second set of eyes.
5. **Log the scores weekly.** Within 4-6 weeks you'll have baseline data to bring to the tooling conversation.

Compound habit, not silver bullet. One page a day beats a quarterly audit nobody reads.

---

## Suggested invocation patterns

### New engagement onboarding (end-to-end)

```
/cmo/geo/prompt-set-builder       # build the 50-prompt test set
/cmo/geo/share-of-answers         # establish baseline AI visibility
/cmo/geo/audit                    # pull intake data, score priority URLs
/cmo/geo/citation-network-mapper  # map where AI cites in your vertical
/cmo/geo/plan                     # synthesize → initiatives + revenue model
```

Terminal deliverable: exec-ready plan + business case. Uses ~$2-10 of API spend for a 50-prompt run.

### Quarterly re-audit

```
/cmo/geo/share-of-answers   # rerun the same prompt set
/cmo/geo/audit              # re-score priority URLs
/cmo/geo/plan               # re-plan against current deltas
```

### Single-page rework

```
/cmo/geo/audit                  # get a baseline score for the URL
/cmo/geo/content-restructure    # operator-gated rewrite with voice preservation
```

---

## The research behind it

Two recent pieces shaped how these skills work. Both worth reading whether you run the skills or not.

**Kevin Indig (Growth Memo):** [The Science of How AI Picks Its Sources](https://www.growth-memo.com/p/the-science-of-how-ai-picks-its-sources). A 1.2M-citation analysis of what AI engines actually quote and why. The 8 citation-worthiness signals in the audit scorecard come directly from this work. Statistical confidence P<0.0001.

**Ethan Smith (Graphite):** [Demystifying Randomness in AI](https://graphite.io/five-percent/demystifying-randomness-in-ai). The reason a single prompt run lies to you. AI answers have high variance, so `share-of-answers` runs multiple prompts per query to smooth the noise. If you only read one thing before using this, read this one.

Full framework library is in [`research/geo-aeo/frameworks/`](research/geo-aeo/frameworks/).

---

## Who this is for

The marketing lead at a startup who:

- doesn't have an SEO person on the team
- doesn't have $1-2k/mo in budget for Profound, Ahrefs, or Semrush
- is still getting asked about AI search visibility in every board prep
- needs to do the basics daily while building the case for bigger investment

If you have enterprise tool budget, buy Profound. It's better. This isn't that.

This is for the person who needs to collect the data that proves the budget is worth it, before they get the budget.

---

## One skill is a good start. 47 is a system.

Paid subscribers to [Marketer in the Loop](https://mktrintheloop.com) get access to this skill and 47 others via the MultiplAI MCP server. Strategy, content, creative direction, distribution, and ops. All orchestrated through Claude Code, Claude Desktop, or Cowork.

It's the same skill stack used to run strategy for agency clients. Free subscribers get one skill a week. Paid subscribers get the whole library.

[Get access to all 47 skills →](https://multiplai.co/skills)

---

## FAQ

**Do I need Claude Code to use these skills?**
The `.md` skill files are designed for Claude Code orchestration, but the Python tools run standalone. You can call `python3 tools/geo_audit.py --url ...` from any terminal and get the same scorecard output.

**How is this different from running prompts manually in ChatGPT?**
Three things: (1) It runs across four engines, not one. (2) It runs multiple prompts per query to handle answer randomness. (3) It cross-references prompt results with a technical + citation-worthiness audit of the URL itself, so you get *why* you're not showing up, not just *whether*.

**Does it work on competitor URLs?**
Yes. Run your top 5 pages, then run a competitor's equivalents. The delta is your to-do list.

**What do the fix labels mean?**
- `[SEO+/GEO+]` — helps both traditional search and AI citation. Ship first.
- `[GEO+ only]` — helps AI citation, neutral for SEO. Safe.
- `[GEO+ but SEO-]` — helps AI citation but may hurt SEO. Proceed with caution. Requires explicit approval.

**What about Google penalties?**
The `[GEO+ but SEO-]` label exists specifically to flag the small set of tactics that trade SEO for AI visibility, so you can make an informed call rather than ship something risky by accident. Follow the labels and you're safe.

---

## License

MIT. Use it, modify it, ship it.

---

*Built by Hanna Huffman at [MultiplAI Growth Systems](https://multiplai.co). Questions? Reply to any [Marketer in the Loop](https://mktrintheloop.com) email.*
