#!/usr/bin/env python3
"""
Map the citation network for a vertical: which domains AI cites most often
when answering questions in a category, plus an earned-mention target list.

Operationalizes Framework 02's domain concentration findings + Framework 01's
off-site strategy step.

Three ingestion modes (pick one):
  1. --from-runs <runs.csv>       Reuse an existing /cmo/geo/share-of-answers
                                   runs.csv (FREE — no API calls)
  2. --from-profound <csv>         Import a Profound citation export
                                   (FREE — already paid via subscription)
  3. --prompts <csv>               Fresh run via SoA engine with adaptive
                                   sampling (PAID — cost gate enforced)

Outputs (written to --output dir):
  * citation_network.csv   one row per domain, aggregated metrics
  * earned_mentions.md     top-N targets with outreach angle + effort estimate
  * network_analysis.md    concentration metric, gap analysis, competitor view

Adaptive sampling (fresh-run mode only):
  Start at --runs-per-prompt (default 3). After each pass, compute the 95%
  Wilson score CI half-width for primary-brand visibility and each competitor.
  If any entity's half-width > --target-ci-half-width (default 6.0 pp),
  add 2 more runs/prompt. Cap at --max-runs-per-prompt (default 15).

Usage:
    # Reuse existing SoA run
    python3 tools/geo_citation_network.py \\
        --from-runs clients/acme/geo/share-of-answers/2026-04-10/runs.csv \\
        --brands   clients/acme/geo/brands.csv \\
        --output   clients/acme/geo/citation-network/observability_2026-04-17/ \\
        --vertical "data observability"

    # Fresh run (with cost gate)
    python3 tools/geo_citation_network.py \\
        --prompts  clients/acme/geo/prompts.csv \\
        --brands   clients/acme/geo/brands.csv \\
        --output   clients/acme/geo/citation-network/observability_2026-04-17/ \\
        --vertical "data observability"

Requires: anthropic, openai, google-genai, requests, python-dotenv, tldextract
"""
import argparse
import csv
import json
import math
import os
import re
import sys
import time
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

warnings.filterwarnings("ignore")

# Allow running as script from repo root OR from tools/ dir.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from geo_share_of_answers import (  # noqa: E402
    BrandSpec,
    Prompt,
    RunResult,
    SUPPORTED_SURFACES,
    DEFAULT_MODELS,
    PRICING,
    EST_INPUT_TOKENS,
    EST_OUTPUT_TOKENS,
    load_brands,
    load_prompts,
    normalize_text,
    brand_appears_in,
    brand_position_classify,
    detect_competitors,
    estimate_cost,
    run_suite,
    die,
    confirm,
)

try:
    import tldextract
except ImportError:
    print("ERROR: pip install --user tldextract", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Domain categorization — rule-based knowledge base
# ---------------------------------------------------------------------------

# Category values (locked vocabulary, referenced by downstream skills):
CATEGORIES = ["publisher", "society", "ugc", "aggregator", "vendor", "owned", "encyclopedia", "docs", "video", "unknown"]

# Domains whose subpath carries identity (e.g., reddit.com/r/cardiology is a
# meaningfully distinct target from reddit.com as a whole). For these, we
# preserve the first path segment pair ("r/cardiology") in the aggregated key.
SUBPATH_SIGNIFICANT = {"reddit.com", "stackexchange.com"}

# eTLD+1 → category map. Curated list; LLM fallback handles the long tail.
KNOWN_DOMAINS = {
    # Major publishers / trade press
    "medscape.com": "publisher",
    "searchengineland.com": "publisher",
    "searchenginejournal.com": "publisher",
    "techcrunch.com": "publisher",
    "theverge.com": "publisher",
    "wired.com": "publisher",
    "statnews.com": "publisher",
    "nytimes.com": "publisher",
    "wsj.com": "publisher",
    "forbes.com": "publisher",
    "bloomberg.com": "publisher",
    "cnbc.com": "publisher",
    "reuters.com": "publisher",
    "axios.com": "publisher",
    "theinformation.com": "publisher",
    "arstechnica.com": "publisher",
    "venturebeat.com": "publisher",
    "hbr.org": "publisher",
    "inc.com": "publisher",
    "fastcompany.com": "publisher",
    "businessinsider.com": "publisher",
    "economist.com": "publisher",
    "ft.com": "publisher",
    "nature.com": "publisher",
    "sciencedirect.com": "publisher",
    "acm.org": "publisher",
    "ieee.org": "publisher",
    "nejm.org": "publisher",
    "jamanetwork.com": "publisher",
    "thelancet.com": "publisher",
    "bmj.com": "publisher",
    "martechseries.com": "publisher",
    "cio.com": "publisher",
    "infoworld.com": "publisher",
    "zdnet.com": "publisher",
    "computerweekly.com": "publisher",
    "informationweek.com": "publisher",
    "theregister.com": "publisher",
    "thenewstack.io": "publisher",
    "infoq.com": "publisher",
    "readwrite.com": "publisher",
    "martech.org": "publisher",
    "adweek.com": "publisher",
    "marketingland.com": "publisher",
    "contentmarketinginstitute.com": "publisher",
    "hubspot.com": "publisher",
    "growthmarketingpro.com": "publisher",
    "lennysnewsletter.com": "publisher",
    "growthmemo.com": "publisher",
    # Society / official authority
    "acc.org": "society",
    "aha.org": "society",
    "ama-assn.org": "society",
    "heart.org": "society",
    "asco.org": "society",
    "cdc.gov": "society",
    "nih.gov": "society",
    "who.int": "society",
    "fda.gov": "society",
    "sec.gov": "society",
    "ftc.gov": "society",
    "europa.eu": "society",
    "nist.gov": "society",
    "w3.org": "society",
    "iso.org": "society",
    # UGC / community
    "reddit.com": "ugc",
    "quora.com": "ugc",
    "stackexchange.com": "ugc",
    "stackoverflow.com": "ugc",
    "ycombinator.com": "ugc",
    "news.ycombinator.com": "ugc",
    "medium.com": "ugc",
    "substack.com": "ugc",
    "dev.to": "ugc",
    "hashnode.com": "ugc",
    "indiehackers.com": "ugc",
    "linkedin.com": "ugc",
    "x.com": "ugc",
    "twitter.com": "ugc",
    "threads.net": "ugc",
    "bluesky.social": "ugc",
    "mastodon.social": "ugc",
    # Comparison / aggregator
    "g2.com": "aggregator",
    "capterra.com": "aggregator",
    "trustradius.com": "aggregator",
    "softwareadvice.com": "aggregator",
    "getapp.com": "aggregator",
    "producthunt.com": "aggregator",
    "gartner.com": "aggregator",
    "forrester.com": "aggregator",
    "idc.com": "aggregator",
    "stackshare.io": "aggregator",
    "alternativeto.net": "aggregator",
    "slant.co": "aggregator",
    "crozdesk.com": "aggregator",
    "goodfirms.co": "aggregator",
    "clutch.co": "aggregator",
    # Encyclopedia / reference
    "wikipedia.org": "encyclopedia",
    "britannica.com": "encyclopedia",
    "investopedia.com": "encyclopedia",
    # Docs / developer
    "github.com": "docs",
    "gitlab.com": "docs",
    "bitbucket.org": "docs",
    "docs.python.org": "docs",
    "developer.mozilla.org": "docs",
    "readthedocs.io": "docs",
    # Video
    "youtube.com": "video",
    "vimeo.com": "video",
    "tiktok.com": "video",
    "loom.com": "video",
}

# Regex patterns for long-tail categorization before LLM fallback
REGEX_RULES = [
    (re.compile(r"\.(gov|mil)$"), "society"),
    (re.compile(r"\.(edu|ac\.[a-z]{2})$"), "society"),
    (re.compile(r"(^|\.)wikipedia\.org$"), "encyclopedia"),
    (re.compile(r"(^|\.)stackexchange\.com$"), "ugc"),
    (re.compile(r"(^|\.)blogspot\.com$"), "ugc"),
    (re.compile(r"(^|\.)wordpress\.com$"), "ugc"),
    (re.compile(r"(^|\.)wix\.com$"), "ugc"),
    (re.compile(r"(^|\.)netlify\.app$"), "vendor"),
    (re.compile(r"(^|\.)vercel\.app$"), "vendor"),
]

# Outreach angle templates per category
OUTREACH_ANGLES = {
    "publisher": "Guest post / KOL byline; pitch exclusive data or original research",
    "society": "Standards contribution / working group / committee participation",
    "ugc": "Authentic community engagement; AMA / expert answers; no overt promo",
    "aggregator": "Free profile claim + customer reviews push; paid placement optional",
    "vendor": "Competitive — avoid direct pitch; pursue integration or co-marketing where possible",
    "owned": "Already yours — prioritize for citation-worthiness optimization via /cmo/geo/content-restructure",
    "encyclopedia": "Wikipedia: edit existing entries via independent sources (no paid edits); other refs: pitch citation via original data",
    "docs": "Contribute open-source code, documentation, or packages tagged for the category",
    "video": "Create or sponsor expert-led video content; YouTube SEO matters for citation",
    "unknown": "Manual research required — surface domain to operator for classification",
}

EFFORT_BY_CATEGORY = {
    "publisher": "M",
    "society": "L",
    "ugc": "S",
    "aggregator": "S",
    "vendor": "M",
    "owned": "S",
    "encyclopedia": "L",
    "docs": "M",
    "video": "M",
    "unknown": "S",
}

JUDGE_MODEL = "claude-haiku-4-5-20251001"

# Adaptive sampling defaults
DEFAULT_INITIAL_RUNS = 3
DEFAULT_STEP_RUNS = 2
DEFAULT_MAX_RUNS = 15
DEFAULT_CI_HALF_WIDTH_PP = 6.0
WILSON_Z = 1.96  # 95% CI


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CitationEvent:
    """One instance of a domain being cited in a response."""
    prompt_id: str
    topic: str
    intent_type: str
    surface: str
    run_number: int
    url: str
    domain_key: str      # aggregation key (eTLD+1 or eTLD+1 + first-path for SUBPATH_SIGNIFICANT)
    raw_domain: str      # eTLD+1 (for lookup in KNOWN_DOMAINS)
    position: int        # 1-indexed position within the response's citation list
    is_primary_position: bool  # top-3 citation in response


@dataclass
class DomainStats:
    domain_key: str
    raw_domain: str
    citation_count: int = 0
    topics: set = field(default_factory=set)
    prompts: set = field(default_factory=set)
    surfaces: set = field(default_factory=set)
    primary_citations: int = 0
    secondary_citations: int = 0
    category: str = "unknown"
    sample_urls: list = field(default_factory=list)  # up to 3, for LLM categorization


# ---------------------------------------------------------------------------
# Domain extraction
# ---------------------------------------------------------------------------

_tld_extractor = tldextract.TLDExtract(suffix_list_urls=None, cache_dir=None)


def extract_domain(url: str) -> tuple:
    """Return (aggregation_key, raw_etld1). Empty strings if unparseable."""
    if not url:
        return "", ""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        netloc = parsed.netloc.lower()
        if not netloc:
            return "", ""
        ext = _tld_extractor(netloc)
        if not ext.domain or not ext.suffix:
            return netloc, netloc
        etld1 = f"{ext.domain}.{ext.suffix}"
        if etld1 in SUBPATH_SIGNIFICANT:
            path = parsed.path.strip("/").split("/")
            if len(path) >= 2 and path[0] and path[1]:
                # e.g. reddit.com/r/cardiology
                return f"{etld1}/{path[0]}/{path[1]}", etld1
        return etld1, etld1
    except Exception:
        return "", ""


# ---------------------------------------------------------------------------
# Categorization — rule-based + LLM fallback
# ---------------------------------------------------------------------------


def categorize_rule_based(raw_domain: str, owned_domains: set, competitor_domains: set) -> Optional[str]:
    if not raw_domain:
        return None
    if raw_domain in owned_domains:
        return "owned"
    if raw_domain in competitor_domains:
        return "vendor"
    if raw_domain in KNOWN_DOMAINS:
        return KNOWN_DOMAINS[raw_domain]
    for pattern, cat in REGEX_RULES:
        if pattern.search(raw_domain):
            return cat
    return None


def categorize_via_llm(domain: str, sample_urls: list) -> str:
    """Claude Haiku classifies an unknown domain. Returns 'unknown' on error."""
    try:
        from anthropic import Anthropic
    except ImportError:
        return "unknown"
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    sys_prompt = (
        "You classify web domains into ONE of these categories for an AI-citation "
        "network map:\n"
        "  publisher   — news / trade publication / editorial site\n"
        "  society     — government, academic, standards body, medical society\n"
        "  ugc         — user-generated content (Reddit/Quora/Medium/forum)\n"
        "  aggregator  — review/comparison site (G2/Capterra/Gartner)\n"
        "  vendor      — product/SaaS company site (commercial offering)\n"
        "  encyclopedia — Wikipedia, Britannica, reference\n"
        "  docs        — developer docs / code repo / technical spec\n"
        "  video       — video-hosting platform\n"
        "  unknown     — cannot determine\n"
        'Respond ONLY as JSON: {"category": "<one of above>"}'
    )
    user_msg = f"Domain: {domain}\nSample URLs cited:\n" + "\n".join(sample_urls[:3])
    try:
        resp = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=100,
            system=sys_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        body = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        m = re.search(r"\{.*\}", body, re.DOTALL)
        if not m:
            return "unknown"
        parsed = json.loads(m.group(0))
        cat = parsed.get("category", "unknown").lower()
        return cat if cat in CATEGORIES else "unknown"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Citation extraction from runs
# ---------------------------------------------------------------------------


def citation_events_from_runs_csv(path: Path, prompt_topic_lookup: dict) -> list:
    """Parse a SoA runs.csv into per-citation events.

    prompt_topic_lookup: {prompt_id: topic_name} from the prompts CSV if
    available; otherwise empty and events will show topic=''.
    """
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    if not rows:
        die(f"runs.csv is empty: {path}")
    events = []
    for r in rows:
        if r.get("brand_cited") == "error":
            continue
        urls_field = r.get("citation_urls") or ""
        urls = [u.strip() for u in urls_field.split("|") if u.strip()]
        if not urls:
            continue
        topic = prompt_topic_lookup.get(r["prompt_id"], r.get("topic", ""))
        for idx, url in enumerate(urls, start=1):
            key, raw = extract_domain(url)
            if not key:
                continue
            events.append(CitationEvent(
                prompt_id=r["prompt_id"],
                topic=topic,
                intent_type=r.get("intent_type", ""),
                surface=r["ai_surface"],
                run_number=int(r.get("run_number") or 1),
                url=url,
                domain_key=key,
                raw_domain=raw,
                position=idx,
                is_primary_position=(idx <= 3),
            ))
    return events


def citation_events_from_profound_csv(path: Path) -> list:
    """Parse a Profound citation export.

    Expected schema (Profound's standard export, V1 supports the most common
    columns — rename headers via --profound-col-map if yours differ):
        prompt, topic, intent, platform (anthropic/openai/google/perplexity),
        citation_url, position

    Rows without a citation_url are skipped.
    """
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    if not rows:
        die(f"Profound export is empty: {path}")
    required = {"prompt", "citation_url", "platform"}
    missing = required - set(rows[0].keys())
    if missing:
        die(f"Profound CSV missing required columns: {sorted(missing)}")
    events = []
    for r in rows:
        url = (r.get("citation_url") or "").strip()
        if not url:
            continue
        key, raw = extract_domain(url)
        if not key:
            continue
        events.append(CitationEvent(
            prompt_id=r.get("prompt") or r.get("prompt_id") or "",
            topic=r.get("topic") or "",
            intent_type=r.get("intent") or r.get("intent_type") or "",
            surface=r.get("platform") or r.get("ai_surface") or "",
            run_number=int(r.get("run_number") or 1),
            url=url,
            domain_key=key,
            raw_domain=raw,
            position=int(r.get("position") or 1),
            is_primary_position=int(r.get("position") or 1) <= 3,
        ))
    return events


def citation_events_from_run_results(results: list, prompts_by_id: dict) -> list:
    """Convert in-memory RunResult list into citation events."""
    events = []
    for r in results:
        if r.error or not r.citation_urls:
            continue
        prompt = prompts_by_id.get(r.prompt_id)
        topic = prompt.topic if prompt else ""
        for idx, url in enumerate(r.citation_urls, start=1):
            key, raw = extract_domain(url)
            if not key:
                continue
            events.append(CitationEvent(
                prompt_id=r.prompt_id,
                topic=topic,
                intent_type=r.intent_type,
                surface=r.surface,
                run_number=r.run_number,
                url=url,
                domain_key=key,
                raw_domain=raw,
                position=idx,
                is_primary_position=(idx <= 3),
            ))
    return events


# ---------------------------------------------------------------------------
# Domain aggregation
# ---------------------------------------------------------------------------


def aggregate_domains(events: list) -> dict:
    stats: dict = {}
    for ev in events:
        s = stats.setdefault(ev.domain_key, DomainStats(domain_key=ev.domain_key, raw_domain=ev.raw_domain))
        s.citation_count += 1
        if ev.topic:
            s.topics.add(ev.topic)
        s.prompts.add(ev.prompt_id)
        s.surfaces.add(ev.surface)
        if ev.is_primary_position:
            s.primary_citations += 1
        else:
            s.secondary_citations += 1
        if len(s.sample_urls) < 3 and ev.url not in s.sample_urls:
            s.sample_urls.append(ev.url)
    return stats


def categorize_all(
    stats: dict,
    owned_domains: set,
    competitor_domains: set,
    use_llm: bool,
) -> tuple:
    """Assign category to every domain. Returns (rule_hits, llm_hits)."""
    rule_hits = 0
    llm_hits = 0
    unknowns_for_llm = []
    # Pass 1: rules
    for key, s in stats.items():
        cat = categorize_rule_based(s.raw_domain, owned_domains, competitor_domains)
        if cat:
            s.category = cat
            rule_hits += 1
        else:
            unknowns_for_llm.append(key)
    if use_llm and unknowns_for_llm:
        print(f"  Categorizing {len(unknowns_for_llm)} unknown domains via Claude Haiku...", flush=True)
        for key in unknowns_for_llm:
            s = stats[key]
            s.category = categorize_via_llm(s.raw_domain, s.sample_urls)
            if s.category != "unknown":
                llm_hits += 1
    return rule_hits, llm_hits


# ---------------------------------------------------------------------------
# Adaptive sampling — Wilson score interval
# ---------------------------------------------------------------------------


def wilson_half_width_pp(n_hits: int, n_total: int, z: float = WILSON_Z) -> float:
    """Half-width of the 95% Wilson score interval, in percentage points."""
    if n_total <= 0:
        return 100.0
    p = n_hits / n_total
    denom = 1 + z * z / n_total
    center = (p + z * z / (2 * n_total)) / denom
    spread = (z / denom) * math.sqrt(p * (1 - p) / n_total + z * z / (4 * n_total * n_total))
    return spread * 100.0


def entity_half_widths(
    results: list,
    primary: BrandSpec,
    competitors: list,
) -> dict:
    """Compute 95% Wilson CI half-width (pp) per tracked entity."""
    out = {}
    total = len([r for r in results if not r.error])
    for brand in [primary] + competitors:
        hits = 0
        for r in results:
            if r.error:
                continue
            if brand_appears_in(r.response_text, r.citation_urls, brand):
                hits += 1
        out[brand.name] = wilson_half_width_pp(hits, total)
    return out


def run_with_adaptive_sampling(
    prompts: list,
    surfaces: list,
    primary: BrandSpec,
    competitors: list,
    initial_runs: int,
    step_runs: int,
    max_runs_per_prompt: int,
    target_half_width_pp: float,
    models: dict,
    sleep_between: float,
) -> tuple:
    """Run SoA prompts with sequential sampling until entity CI half-widths
    converge below target_half_width_pp, or the per-prompt cap is hit.

    Returns (results, rounds_log) where rounds_log is list of dicts per pass.
    """
    all_results = []
    rounds = []
    runs_done = 0
    start_run_number = 1
    while runs_done < max_runs_per_prompt:
        pass_runs = initial_runs if not all_results else step_runs
        pass_runs = min(pass_runs, max_runs_per_prompt - runs_done)
        print(f"\n== Adaptive pass — adding {pass_runs} runs/prompt "
              f"(total after pass: {runs_done + pass_runs}) ==", flush=True)
        new_results = run_suite(
            prompts=prompts,
            surfaces=surfaces,
            runs_per_prompt=pass_runs,
            models=models,
            sleep_between=sleep_between,
            start_run_number=start_run_number,
        )
        all_results.extend(new_results)
        runs_done += pass_runs
        start_run_number += pass_runs
        half_widths = entity_half_widths(all_results, primary, competitors)
        max_hw = max(half_widths.values()) if half_widths else 0.0
        rounds.append({
            "total_runs_per_prompt": runs_done,
            "cumulative_samples": len(all_results),
            "entity_half_widths_pp": half_widths,
            "max_half_width_pp": max_hw,
        })
        print("  95% Wilson CI half-widths (pp):")
        for name, hw in sorted(half_widths.items(), key=lambda x: -x[1]):
            flag = "  ✓" if hw <= target_half_width_pp else "  (wide)"
            print(f"    {name:<30} {hw:5.2f}{flag}")
        if max_hw <= target_half_width_pp:
            print(f"  ✓ all entities within {target_half_width_pp}pp — stopping.")
            break
        if runs_done >= max_runs_per_prompt:
            print(f"  Cap reached ({max_runs_per_prompt} runs/prompt). Stopping with max_hw={max_hw:.2f}pp.")
            break
    return all_results, rounds


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------


NETWORK_COLS = [
    "domain", "category", "citation_count", "topic_count", "prompt_count",
    "ai_surfaces", "primary_citations", "secondary_citations",
    "citation_share_pct", "outreach_angle", "effort", "sample_url",
]


def write_citation_network_csv(
    out_dir: Path,
    stats: dict,
    total_citations: int,
    min_citations: int,
) -> Path:
    sorted_stats = sorted(stats.values(), key=lambda s: (-s.citation_count, s.domain_key))
    out = out_dir / "citation_network.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=NETWORK_COLS)
        w.writeheader()
        for s in sorted_stats:
            if s.citation_count < min_citations:
                continue
            w.writerow({
                "domain": s.domain_key,
                "category": s.category,
                "citation_count": s.citation_count,
                "topic_count": len(s.topics),
                "prompt_count": len(s.prompts),
                "ai_surfaces": "|".join(sorted(s.surfaces)),
                "primary_citations": s.primary_citations,
                "secondary_citations": s.secondary_citations,
                "citation_share_pct": round(100 * s.citation_count / total_citations, 2) if total_citations else 0,
                "outreach_angle": OUTREACH_ANGLES.get(s.category, ""),
                "effort": EFFORT_BY_CATEGORY.get(s.category, "M"),
                "sample_url": s.sample_urls[0] if s.sample_urls else "",
            })
    return out


def write_earned_mentions_md(
    out_dir: Path,
    stats: dict,
    total_citations: int,
    vertical: str,
    primary: BrandSpec,
    top_n: int,
) -> Path:
    """Rank earned-mention candidates by composite score.

    Excludes:
      * owned  — it's yours already
      * vendor — competitors' own domains aren't earnable mentions; they're
                 competitive landscape (reported in network_analysis.md)
      * unknown — can't recommend action without knowing the category
    """
    candidates = [
        s for s in stats.values()
        if s.category not in {"owned", "vendor", "unknown"} and s.citation_count >= 2
    ]
    # Composite score rewards domains with both volume AND topic spread.
    def score(s):
        share = s.citation_count / total_citations if total_citations else 0
        breadth = math.log1p(len(s.topics))
        return share * (1 + breadth)
    candidates.sort(key=score, reverse=True)
    top = candidates[:top_n]

    lines = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines.append(f"# Earned-Mention Targets — {vertical or 'vertical'}")
    lines.append("")
    lines.append(f"**Primary brand:** {primary.name}  ")
    lines.append(f"**Generated:** {today} UTC  ")
    lines.append(f"**Ranking:** composite of citation share × topic breadth (log1p).")
    lines.append(f"  Volume alone is misleading — a domain cited 100× on one topic is less")
    lines.append(f"  valuable than one cited 60× across 10 topics.")
    lines.append("")
    lines.append("## Top targets")
    lines.append("")
    lines.append("| # | Domain | Category | Citation share | Topics | AI surfaces | Effort | Outreach angle |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for i, s in enumerate(top, start=1):
        share_pct = (100 * s.citation_count / total_citations) if total_citations else 0
        lines.append(
            f"| {i} | `{s.domain_key}` | {s.category} | {share_pct:.1f}% "
            f"({s.citation_count}) | {len(s.topics)} | {len(s.surfaces)}/4 | "
            f"{EFFORT_BY_CATEGORY.get(s.category, 'M')} | "
            f"{OUTREACH_ANGLES.get(s.category, '—')} |"
        )
    lines.append("")
    lines.append("## Category distribution of top targets")
    lines.append("")
    by_cat = defaultdict(int)
    for s in top:
        by_cat[s.category] += 1
    lines.append("| Category | Count in top list |")
    lines.append("|---|---|")
    for cat in sorted(by_cat, key=lambda c: -by_cat[c]):
        lines.append(f"| {cat} | {by_cat[cat]} |")
    lines.append("")
    lines.append("## How to use this list")
    lines.append("")
    lines.append("1. **Verify feasibility** per target — is an active outreach channel open "
                 "(journalist contact, community moderator, program manager)?")
    lines.append("2. **Sequence by effort + impact** — ship the S-effort, high-share targets "
                 "first (usually UGC + aggregator profile claims).")
    lines.append("3. **Pair with content** — off-site mentions work best when there's a "
                 "citable asset on your own domain. Run `/cmo/geo/content-restructure` on "
                 "the landing page the earned mention will link to, first.")
    lines.append("4. **Measure re-run** — rerun this skill quarterly. Citation network "
                 "shifts as AI providers update retrieval.")
    lines.append("")
    out = out_dir / "earned_mentions.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def write_network_analysis_md(
    out_dir: Path,
    stats: dict,
    total_citations: int,
    total_unique_domains: int,
    vertical: str,
    primary: BrandSpec,
    competitors: list,
    ingestion_mode: str,
    source_note: str,
    rule_hits: int,
    llm_hits: int,
    unknown_count: int,
    adaptive_rounds: Optional[list] = None,
) -> Path:
    """Network-level analysis: concentration, gap analysis, competitive view."""
    sorted_stats = sorted(stats.values(), key=lambda s: -s.citation_count)
    top10 = sorted_stats[:10]
    top30 = sorted_stats[:30]
    top10_share = sum(s.citation_count for s in top10) / total_citations * 100 if total_citations else 0
    top30_share = sum(s.citation_count for s in top30) / total_citations * 100 if total_citations else 0

    # Category distribution of all citations
    cat_citations = defaultdict(int)
    cat_domains = defaultdict(int)
    for s in stats.values():
        cat_citations[s.category] += s.citation_count
        cat_domains[s.category] += 1

    # Competitor appearances
    competitor_hits = {c.name: 0 for c in competitors}
    owned_hits = 0
    for s in stats.values():
        if s.category == "owned":
            owned_hits += s.citation_count
        if s.category == "vendor":
            for c in competitors:
                if c.domain and (s.raw_domain == c.domain or s.raw_domain.endswith("." + c.domain)):
                    competitor_hits[c.name] += s.citation_count

    lines = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines.append(f"# Citation Network — {vertical or 'vertical'}")
    lines.append("")
    lines.append(f"**Primary brand:** {primary.name}  ")
    lines.append(f"**Generated:** {today} UTC  ")
    lines.append(f"**Ingestion mode:** {ingestion_mode}  ")
    lines.append(f"**Source:** {source_note}  ")
    lines.append(f"**Total citations aggregated:** {total_citations:,}  ")
    lines.append(f"**Unique domains:** {total_unique_domains}  ")
    cat_breakdown = f"rules: {rule_hits}, LLM: {llm_hits}, unknown: {unknown_count}"
    lines.append(f"**Categorization:** {cat_breakdown}")
    lines.append("")

    # ---- Adaptive sampling report ----
    if adaptive_rounds:
        lines.append("## Adaptive sampling report")
        lines.append("")
        lines.append("Sequential sampling stopped when all tracked entities reached a 95% Wilson score "
                     "interval half-width ≤ 6pp (per Graphite methodology — reduces required runs ~51% vs. fixed N).")
        lines.append("")
        lines.append("| Pass | Runs/prompt | Cumulative samples | Max entity CI half-width (pp) |")
        lines.append("|---|---|---|---|")
        for i, rd in enumerate(adaptive_rounds, start=1):
            lines.append(f"| {i} | {rd['total_runs_per_prompt']} | {rd['cumulative_samples']} | {rd['max_half_width_pp']:.2f} |")
        lines.append("")
        # Final per-entity CIs
        final = adaptive_rounds[-1]["entity_half_widths_pp"]
        lines.append("**Final entity confidence (95% Wilson CI half-width):**")
        lines.append("")
        for name, hw in sorted(final.items(), key=lambda x: -x[1]):
            lines.append(f"- **{name}:** ±{hw:.2f}pp")
        lines.append("")

    # ---- Concentration ----
    lines.append("## Domain concentration")
    lines.append("")
    lines.append(f"- **Top-10 share:** {top10_share:.1f}% of all citations")
    lines.append(f"- **Top-30 share:** {top30_share:.1f}% of all citations")
    lines.append("")
    # Benchmark against Framework 02
    lines.append("Framework 02 vertical benchmarks for top-10 share:")
    lines.append("")
    lines.append("- Education: **59.5%** (high concentration)")
    lines.append("- Healthcare: **13.0%** (low concentration, fragmented)")
    lines.append("- General: ~**46%** (Indig's 1.2M-citation corpus)")
    lines.append("")
    if top10_share > 55:
        concentration_verdict = "**HIGH concentration** — to win in this vertical you must either be a top-10 domain or earn citations from one. Off-site strategy is non-negotiable."
    elif top10_share > 30:
        concentration_verdict = "**MODERATE concentration** — off-site strategy matters but there's room for a well-positioned new entrant."
    else:
        concentration_verdict = "**LOW concentration** — fragmented network, opportunity for a new entrant to build topical authority. Off-site is helpful but not gating."
    lines.append(concentration_verdict)
    lines.append("")

    # ---- Category distribution ----
    lines.append("## Category distribution")
    lines.append("")
    lines.append("| Category | Citations | Share | Unique domains |")
    lines.append("|---|---|---|---|")
    for cat in sorted(cat_citations, key=lambda c: -cat_citations[c]):
        c = cat_citations[cat]
        share = (c / total_citations * 100) if total_citations else 0
        lines.append(f"| {cat} | {c} | {share:.1f}% | {cat_domains[cat]} |")
    lines.append("")

    # ---- Gap analysis ----
    lines.append("## Gap analysis")
    lines.append("")
    lines.append("Where is the network concentrated that you're NOT appearing?")
    lines.append("")
    absent_top = [
        s for s in top30
        if s.category not in {"owned"}
        and s.raw_domain != primary.domain
    ]
    if absent_top:
        lines.append("**Top-30 domains that cite this vertical (you should be on or mentioned by these):**")
        lines.append("")
        for s in absent_top[:15]:
            share = (100 * s.citation_count / total_citations) if total_citations else 0
            lines.append(f"- `{s.domain_key}` — {s.category}, {share:.1f}% share, {len(s.topics)} topics")
    else:
        lines.append("_No top-30 gap domains found._")
    lines.append("")

    # Underrepresented categories
    underrep = [cat for cat, c in cat_citations.items() if c / total_citations < 0.05 and cat not in {"owned", "unknown"}]
    if underrep:
        lines.append(f"**Under-represented categories in your cited-with network:** {', '.join(underrep)}. "
                     f"These are channels you may be missing — worth a dedicated push if any connect to your ICP.")
        lines.append("")

    # ---- Competitive view ----
    if competitors:
        lines.append("## Competitor presence in the network")
        lines.append("")
        lines.append("| Brand | Domain-level citations | Notes |")
        lines.append("|---|---|---|")
        lines.append(f"| **{primary.name} (you)** | {owned_hits} | Own-domain citations in this network |")
        for c in competitors:
            lines.append(f"| {c.name} | {competitor_hits[c.name]} | Competitor's own domain |")
        lines.append("")
        lines.append("Note: this is competitor *domain* citations (how often their site is the source). "
                     "Brand *mentions within responses* (e.g., competitor named in a paragraph without linking to their domain) "
                     "are measured by `/cmo/geo/share-of-answers`, not here.")
        lines.append("")

    # ---- Methodology + gating ----
    lines.append("---")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append(f"- **Ingestion:** {source_note}")
    lines.append(f"- **Domain extraction:** tldextract for eTLD+1; reddit/stackexchange preserve first subpath segment")
    lines.append(f"- **Categorization:** rule-based knowledge base ({rule_hits} hits) + Claude Haiku fallback ({llm_hits}) + {unknown_count} unresolved")
    lines.append(f"- **Ranking:** earned-mention list uses citation_share × log1p(topic_count) — volume alone is misleading")
    lines.append("")

    lines.append("## Required gating (Framework 03 + 04)")
    lines.append("")
    lines.append("Before acting on this report:")
    lines.append("")
    lines.append("1. **Misattribution.** A domain appearing frequently in citations does not mean a mention there will cause citations of *you*. Test small before investing heavily.")
    lines.append("2. **Relative vs. absolute.** Citation counts on small prompt sets (<50 prompts) are directional. Treat this report as a priority order, not a promise.")
    lines.append("3. **Vanity metrics.** Being cited on a Top-10 domain is not inherently valuable. Tie earned mentions to downstream AI-referred traffic or brand lift.")
    lines.append("4. **Brand reputation bias.** Some top-10 domains cite the category's largest brand because of pre-existing SEO authority — not editorial merit. Don't assume the path is open.")
    lines.append("5. **Reproduction.** Rerun quarterly. Citation networks shift as AI providers change retrieval.")
    lines.append("")
    lines.append("**SEO/GEO gate (Framework 04):** Any earned-mention tactic proposed from this list must pass the SEO+/GEO+ test — tactics that are SEO-negative don't ship.")
    lines.append("")
    out = out_dir / "network_analysis.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    # Ingestion (exactly one required)
    parser.add_argument("--from-runs", type=Path, help="Path to existing SoA runs.csv (FREE — no API calls)")
    parser.add_argument("--from-profound", type=Path, help="Path to Profound citation export CSV (FREE)")
    parser.add_argument("--prompts", type=Path, help="Prompt CSV for fresh run (PAID — adaptive sampling + cost gate)")
    parser.add_argument("--prompts-for-topics", type=Path,
                        help="Optional prompts CSV to recover topic names when --from-runs is used "
                             "(runs.csv doesn't store topic). Without this, topic_count will be 0.")

    parser.add_argument("--brands", type=Path, required=True, help="Brands CSV (role,name,aliases,domain)")
    parser.add_argument("--output", type=Path, required=True, help="Output directory")

    parser.add_argument("--vertical", type=str, default="", help="Vertical label for output metadata")
    parser.add_argument("--top-targets", type=int, default=20, help="Top N earned-mention targets (default 20)")
    parser.add_argument("--min-citations", type=int, default=2, help="Min citations to appear in citation_network.csv (default 2)")
    parser.add_argument("--no-llm-categorize", action="store_true", help="Skip Claude Haiku fallback for unknown domains")

    # Fresh-run only
    parser.add_argument("--surfaces", type=str, default=",".join(SUPPORTED_SURFACES),
                        help="Comma-separated subset of: " + ",".join(SUPPORTED_SURFACES))
    parser.add_argument("--limit", type=int, default=None, help="Run only first N prompts (fresh-run mode)")
    parser.add_argument("--runs-per-prompt", type=int, default=DEFAULT_INITIAL_RUNS,
                        help=f"Initial runs/prompt for adaptive sampling (default {DEFAULT_INITIAL_RUNS})")
    parser.add_argument("--step-runs", type=int, default=DEFAULT_STEP_RUNS,
                        help=f"Runs added per adaptive pass (default {DEFAULT_STEP_RUNS})")
    parser.add_argument("--max-runs-per-prompt", type=int, default=DEFAULT_MAX_RUNS,
                        help=f"Cap on total runs/prompt (default {DEFAULT_MAX_RUNS})")
    parser.add_argument("--target-ci-half-width", type=float, default=DEFAULT_CI_HALF_WIDTH_PP,
                        help=f"Target 95%% Wilson CI half-width in pp (default {DEFAULT_CI_HALF_WIDTH_PP})")
    parser.add_argument("--max-cost", type=float, default=10.0, help="Abort if estimated worst-case cost exceeds (default $10)")
    parser.add_argument("--no-confirm", action="store_true", help="Skip cost confirmation")
    parser.add_argument("--sleep-between", type=float, default=0.5)
    parser.add_argument("--anthropic-model", default=DEFAULT_MODELS["anthropic"])
    parser.add_argument("--openai-model", default=DEFAULT_MODELS["openai"])
    parser.add_argument("--google-model", default=DEFAULT_MODELS["google"])
    parser.add_argument("--perplexity-model", default=DEFAULT_MODELS["perplexity"])

    opts = parser.parse_args()

    # Exactly one ingestion mode
    modes = [bool(opts.from_runs), bool(opts.from_profound), bool(opts.prompts)]
    if sum(modes) != 1:
        die("exactly one of --from-runs, --from-profound, --prompts is required")

    primary, competitors = load_brands(opts.brands)
    opts.output.mkdir(parents=True, exist_ok=True)

    owned_domains = {primary.domain} if primary.domain else set()
    competitor_domains = {c.domain for c in competitors if c.domain}

    adaptive_rounds = None

    # --- Ingest ---
    if opts.from_runs:
        print(f"Ingesting runs from {opts.from_runs}")
        topic_lookup = {}
        if opts.prompts_for_topics:
            for row in csv.DictReader(opts.prompts_for_topics.open(newline="", encoding="utf-8")):
                topic_lookup[row["prompt_id"]] = row.get("topic", "")
            print(f"  Recovered {len(topic_lookup)} prompt→topic mappings from {opts.prompts_for_topics}")
        events = citation_events_from_runs_csv(opts.from_runs, topic_lookup)
        ingestion_mode = "from-runs"
        source_note = f"Existing SoA runs: `{opts.from_runs}`"
    elif opts.from_profound:
        print(f"Ingesting Profound export from {opts.from_profound}")
        events = citation_events_from_profound_csv(opts.from_profound)
        ingestion_mode = "from-profound"
        source_note = f"Profound export: `{opts.from_profound}`"
    else:
        # Fresh run
        surfaces = [s.strip() for s in opts.surfaces.split(",") if s.strip()]
        bad = [s for s in surfaces if s not in SUPPORTED_SURFACES]
        if bad:
            die(f"unknown surfaces: {bad} — supported: {SUPPORTED_SURFACES}")
        required_env = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "google": "GOOGLE_API_KEY",
            "perplexity": "PERPLEXITY_API_KEY",
        }
        missing = [required_env[s] for s in surfaces if not os.getenv(required_env[s])]
        if missing:
            die(f"missing env vars: {missing}")

        prompts = load_prompts(opts.prompts, limit=opts.limit)
        print(f"\nPrompts: {len(prompts)}")
        print(f"Primary brand: {primary.name}")
        print(f"Competitors: {[c.name for c in competitors]}")
        print(f"Surfaces: {surfaces}")

        # Worst-case cost = max_runs_per_prompt
        worst = estimate_cost(len(prompts), opts.max_runs_per_prompt, surfaces)
        best = estimate_cost(len(prompts), opts.runs_per_prompt, surfaces)
        print(f"\nAdaptive sampling cost range:")
        print(f"  Best case  (stop after {opts.runs_per_prompt} runs/prompt): ${best['total']:.2f} ({best['calls']} calls)")
        print(f"  Worst case (cap at  {opts.max_runs_per_prompt} runs/prompt): ${worst['total']:.2f} ({worst['calls']} calls)")
        for s, c in worst["by_surface"].items():
            print(f"    {s:<12} up to ${c:.3f}")
        if worst["total"] > opts.max_cost:
            die(f"worst-case cost ${worst['total']:.2f} exceeds --max-cost ${opts.max_cost:.2f}")
        if not opts.no_confirm and not confirm("\nProceed with adaptive run?"):
            print("aborted.")
            return 1

        models = {
            "anthropic": opts.anthropic_model,
            "openai": opts.openai_model,
            "google": opts.google_model,
            "perplexity": opts.perplexity_model,
        }

        started = time.time()
        results, adaptive_rounds = run_with_adaptive_sampling(
            prompts=prompts,
            surfaces=surfaces,
            primary=primary,
            competitors=competitors,
            initial_runs=opts.runs_per_prompt,
            step_runs=opts.step_runs,
            max_runs_per_prompt=opts.max_runs_per_prompt,
            target_half_width_pp=opts.target_ci_half_width,
            models=models,
            sleep_between=opts.sleep_between,
        )
        elapsed = time.time() - started
        print(f"\nRun complete in {elapsed:.1f}s. {len(results)} total responses.")

        # Also write the raw SoA-compatible runs.csv so the fresh run can be
        # reused (free) next time without re-hitting APIs.
        raw_path = opts.output / "runs.csv"
        _write_raw_runs_csv(raw_path, results, primary, competitors)
        print(f"Saved raw runs.csv → {raw_path}")

        prompts_by_id = {p.prompt_id: p for p in prompts}
        events = citation_events_from_run_results(results, prompts_by_id)
        ingestion_mode = "fresh-run"
        final_runs = adaptive_rounds[-1]["total_runs_per_prompt"] if adaptive_rounds else opts.runs_per_prompt
        source_note = f"Fresh run: {len(prompts)} prompts × {len(surfaces)} surfaces × {final_runs} runs (adaptive)"

    print(f"\nExtracted {len(events)} citation events.")
    if not events:
        die("No citation events extracted. Nothing to aggregate — check input source.")

    stats = aggregate_domains(events)
    print(f"Aggregated to {len(stats)} unique domains.")

    use_llm = not opts.no_llm_categorize
    rule_hits, llm_hits = categorize_all(stats, owned_domains, competitor_domains, use_llm)
    unknowns = sum(1 for s in stats.values() if s.category == "unknown")
    print(f"Categorization: rule={rule_hits}, llm={llm_hits}, unknown={unknowns}")

    total_citations = sum(s.citation_count for s in stats.values())
    network_csv = write_citation_network_csv(opts.output, stats, total_citations, opts.min_citations)
    earned = write_earned_mentions_md(opts.output, stats, total_citations, opts.vertical, primary, opts.top_targets)
    analysis = write_network_analysis_md(
        opts.output, stats, total_citations, len(stats), opts.vertical, primary, competitors,
        ingestion_mode, source_note, rule_hits, llm_hits, unknowns, adaptive_rounds,
    )
    print(f"\nWrote:")
    print(f"  {network_csv}")
    print(f"  {earned}")
    print(f"  {analysis}")
    return 0


def _write_raw_runs_csv(path: Path, results: list, primary: BrandSpec, competitors: list) -> None:
    """Mini version of SoA's runs.csv writer — saves fresh-run results for later reuse."""
    RUNS_COLS = [
        "run_id", "timestamp", "prompt_id", "intent_type", "ai_surface", "run_number",
        "response_text", "citation_urls", "brand_cited", "brand_position", "competitor_citations",
    ]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RUNS_COLS)
        w.writeheader()
        for i, r in enumerate(results, start=1):
            if r.error:
                w.writerow({
                    "run_id": f"R{i:05d}", "timestamp": ts, "prompt_id": r.prompt_id,
                    "intent_type": r.intent_type, "ai_surface": r.surface, "run_number": r.run_number,
                    "response_text": f"[ERROR] {r.error}", "citation_urls": "", "brand_cited": "error",
                    "brand_position": "", "competitor_citations": "",
                })
                continue
            status, position = brand_position_classify(r.response_text, r.citation_urls, primary)
            comp_cited = detect_competitors(r.response_text, r.citation_urls, competitors)
            w.writerow({
                "run_id": f"R{i:05d}", "timestamp": ts, "prompt_id": r.prompt_id,
                "intent_type": r.intent_type, "ai_surface": r.surface, "run_number": r.run_number,
                "response_text": r.response_text.replace("\r", " "),
                "citation_urls": "|".join(r.citation_urls),
                "brand_cited": status,
                "brand_position": position if position is not None else "",
                "competitor_citations": "|".join(comp_cited),
            })


if __name__ == "__main__":
    sys.exit(main())
