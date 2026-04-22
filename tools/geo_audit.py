#!/usr/bin/env python3
"""
Audit web pages for GEO/AEO citation-worthiness. Scores content against an
8-signal rubric, runs technical checks, and detects high-risk tactics.

This is the execution tool for `/cmo/geo/audit`.

Usage:
    # Single URL
    python3 tools/geo_audit.py --url https://example.com/page --output output/

    # Multiple URLs from CSV
    python3 tools/geo_audit.py --urls urls.csv --output output/

    # With brand name (for self-promotional listicle detection)
    python3 tools/geo_audit.py --url https://example.com/page --brand "Acme" --output output/

    # With domain (for robots.txt / llms.txt checks)
    python3 tools/geo_audit.py --url https://example.com/page --domain example.com --output output/

Requires: requests, beautifulsoup4, textstat, python-dotenv
Optional: readability-lxml (falls back to BS4-only extraction)

Exit codes:
    0  success
    1  partial success (some URLs failed)
    2  argument / setup error
"""
import argparse
import csv
import math
import re
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    print("WARNING: python-dotenv not installed; .env not loaded", file=sys.stderr)

try:
    import requests
except ImportError:
    print("ERROR: pip install --user requests", file=sys.stderr)
    sys.exit(2)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: pip install --user beautifulsoup4", file=sys.stderr)
    sys.exit(2)

try:
    import textstat
except ImportError:
    print("ERROR: pip install --user textstat", file=sys.stderr)
    sys.exit(2)

# readability-lxml is optional
try:
    from readability import Document as ReadabilityDocument

    HAS_READABILITY = True
except ImportError:
    HAS_READABILITY = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

REQUEST_TIMEOUT = 30

# Crawlers to check in robots.txt
AI_CRAWLERS = ["GPTBot", "ClaudeBot", "PerplexityBot", "Googlebot-Extended"]

# Signals weights
SIGNAL_WEIGHTS = {
    "first_30_answer": 3,       # High
    "qa_h2s": 3,                # High
    "entity_density": 3,        # High
    "definitive_openings": 2,   # Medium
    "chunk_independence": 3,    # High
    "sentiment_balance": 2,     # Medium
    "readability": 1,           # Low
    "length_match": 2,          # Medium
}

# Proper noun regex — capitalized multi-word sequences (NOT sentence starters)
PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")

# Context-dependent openers that break chunk independence
DEPENDENT_OPENERS = re.compile(
    r"^(As mentioned|As discussed|As noted|As described|As stated|"
    r"This\s+(?:is|was|means|shows|demonstrates|indicates|suggests|requires|involves)|"
    r"These\s+(?:are|were|include|show)|"
    r"It\s+(?:is|was|also|should|can|may|might|will))\b",
    re.IGNORECASE,
)

# Superlative / promotional words
SUPERLATIVES = {
    "best", "greatest", "leading", "ultimate", "unrivaled", "unmatched",
    "revolutionary", "groundbreaking", "game-changing", "world-class",
    "cutting-edge", "state-of-the-art", "incredible", "amazing", "exceptional",
    "unparalleled", "premier", "superior", "dominant", "top-tier",
}

# Opinion / stance words (not superlatives, just signals of opinion)
OPINION_WORDS = {
    "should", "recommend", "suggest", "believe", "consider", "prefer",
    "argue", "contend", "however", "although", "despite", "nonetheless",
    "importantly", "notably", "surprisingly", "unfortunately", "fortunately",
    "better", "worse", "ideal", "crucial", "essential", "critical",
}

# JS framework indicators
JS_FRAMEWORK_INDICATORS = [
    '<div id="root"', '<div id="app"', '<div id="__next"',
    "__NEXT_DATA__", "bundle.js", "main.js", "app.js",
    "react-root", "ng-app", "data-reactroot",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TechnicalCheck:
    name: str
    passed: bool
    detail: str


@dataclass
class ContentSignal:
    name: str
    score: int  # 0-100
    weight_label: str  # High / Medium / Low
    evidence: str


@dataclass
class RiskFlag:
    name: str
    detected: bool
    detail: str


@dataclass
class Recommendation:
    label: str          # [SEO+/GEO+], [GEO+ only], [GEO+ but SEO-]
    description: str
    effort: str         # S / M / L
    impact: str         # high / med / low


@dataclass
class AuditResult:
    url: str
    slug: str
    fetch_ok: bool
    error: Optional[str] = None
    title: str = ""
    word_count: int = 0
    overall_score: float = 0.0
    technical_checks: list = field(default_factory=list)
    content_signals: list = field(default_factory=list)
    risk_flags: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    quotable_passages: list = field(default_factory=list)
    weak_passages: list = field(default_factory=list)
    js_rendered_warning: bool = False


# ---------------------------------------------------------------------------
# URL slug generation
# ---------------------------------------------------------------------------


def url_to_slug(url: str) -> str:
    """Take the URL path, replace slashes with hyphens, truncate to 60 chars."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        path = parsed.netloc.replace(".", "-")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", path).strip("-")
    return slug[:60] if slug else "page"


# ---------------------------------------------------------------------------
# HTML fetching + content extraction
# ---------------------------------------------------------------------------


def fetch_html(url: str) -> tuple[str, Optional[str]]:
    """Fetch HTML from URL. Returns (html_string, error_or_none)."""
    try:
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        return resp.text, None
    except requests.RequestException as e:
        return "", f"Fetch failed: {e}"


def extract_content(html: str) -> tuple[str, str, BeautifulSoup]:
    """
    Extract main content text and title from HTML.
    Uses readability-lxml if available, falls back to BS4.
    Returns (title, body_text, soup_of_extracted_content).
    """
    if HAS_READABILITY:
        try:
            doc = ReadabilityDocument(html)
            title = doc.title() or ""
            content_html = doc.summary()
            soup = BeautifulSoup(content_html, "html.parser")
            body_text = soup.get_text(separator="\n", strip=True)
            return title, body_text, soup
        except Exception:
            pass  # fall through to BS4

    # BS4 fallback: find article or main tag
    full_soup = BeautifulSoup(html, "html.parser")
    title_tag = full_soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    content_el = (
        full_soup.find("article")
        or full_soup.find("main")
        or full_soup.find("div", {"role": "main"})
        or full_soup.find("div", class_=re.compile(r"content|article|post", re.I))
    )
    if content_el is None:
        content_el = full_soup.find("body") or full_soup
    body_text = content_el.get_text(separator="\n", strip=True)
    return title, body_text, content_el


def detect_js_rendered(html: str, body_text: str) -> bool:
    """Check if the page is likely JS-rendered with minimal server-side content."""
    word_count = len(body_text.split())
    if word_count >= 100:
        return False
    for indicator in JS_FRAMEWORK_INDICATORS:
        if indicator in html:
            return True
    return False


# ---------------------------------------------------------------------------
# Technical checks
# ---------------------------------------------------------------------------


def check_robots_txt(domain: str) -> list[TechnicalCheck]:
    """Check robots.txt for AI crawler access."""
    checks = []
    if not domain:
        return checks

    robots_url = f"https://{domain}/robots.txt"
    try:
        resp = requests.get(
            robots_url, headers={"User-Agent": USER_AGENT}, timeout=10
        )
        if resp.status_code != 200:
            checks.append(TechnicalCheck(
                "robots.txt",
                True,
                f"No robots.txt found ({resp.status_code}) — crawlers allowed by default",
            ))
            return checks

        robots_text = resp.text.lower()
        for crawler in AI_CRAWLERS:
            # Simple check: look for "user-agent: <crawler>" followed by "disallow: /"
            crawler_lower = crawler.lower()
            blocked = False
            in_section = False
            for line in robots_text.splitlines():
                line = line.strip()
                if line.startswith("user-agent:"):
                    agent = line.split(":", 1)[1].strip()
                    # Check both specific crawler and wildcard
                    in_section = agent == crawler_lower or agent == "*"
                elif in_section and line.startswith("disallow:"):
                    path = line.split(":", 1)[1].strip()
                    if path == "/":
                        blocked = True
                        break
                elif line.startswith("user-agent:"):
                    in_section = False

            checks.append(TechnicalCheck(
                f"robots.txt ({crawler})",
                not blocked,
                f"{'BLOCKED' if blocked else 'Allowed'} in robots.txt",
            ))

    except requests.RequestException as e:
        checks.append(TechnicalCheck(
            "robots.txt", True, f"Could not fetch robots.txt: {e}"
        ))
    return checks


def check_llms_txt(domain: str) -> TechnicalCheck:
    """Check if llms.txt exists and report contents."""
    if not domain:
        return TechnicalCheck("llms.txt", False, "No domain provided — skipped")

    llms_url = f"https://{domain}/llms.txt"
    try:
        resp = requests.get(
            llms_url, headers={"User-Agent": USER_AGENT}, timeout=10
        )
        if resp.status_code == 200:
            content_preview = resp.text[:500].strip()
            return TechnicalCheck(
                "llms.txt",
                True,
                f"Found — preview: {content_preview[:200]}...",
            )
        else:
            return TechnicalCheck(
                "llms.txt",
                False,
                f"Not found ({resp.status_code})",
            )
    except requests.RequestException as e:
        return TechnicalCheck("llms.txt", False, f"Could not fetch: {e}")


def check_ssr(html: str, body_text: str) -> TechnicalCheck:
    """Check if page has server-side rendered content."""
    is_js = detect_js_rendered(html, body_text)
    if is_js:
        return TechnicalCheck(
            "SSR content",
            False,
            "Page appears JS-rendered with minimal server-side content. "
            "AI crawlers may not see full content.",
        )
    return TechnicalCheck("SSR content", True, "Content appears server-side rendered")


def check_schema_org(html: str) -> TechnicalCheck:
    """Check for schema.org structured data."""
    soup = BeautifulSoup(html, "html.parser")
    # JSON-LD
    json_ld_tags = soup.find_all("script", type="application/ld+json")
    if json_ld_tags:
        return TechnicalCheck(
            "Schema.org",
            True,
            f"Found {len(json_ld_tags)} JSON-LD block(s)",
        )
    # Microdata
    if soup.find(attrs={"itemscope": True}):
        return TechnicalCheck("Schema.org", True, "Found microdata markup")
    # RDFa
    if soup.find(attrs={"typeof": True}):
        return TechnicalCheck("Schema.org", True, "Found RDFa markup")
    return TechnicalCheck("Schema.org", False, "No structured data found")


def check_canonical(html: str) -> TechnicalCheck:
    """Check for canonical tag."""
    soup = BeautifulSoup(html, "html.parser")
    link = soup.find("link", rel="canonical")
    if link and link.get("href"):
        return TechnicalCheck(
            "Canonical tag", True, f"Found: {link['href']}"
        )
    return TechnicalCheck("Canonical tag", False, "No canonical tag found")


def check_noindex_nosnippet(html: str) -> TechnicalCheck:
    """Check for noindex or nosnippet directives."""
    soup = BeautifulSoup(html, "html.parser")
    issues = []

    for meta in soup.find_all("meta", attrs={"name": re.compile(r"robots", re.I)}):
        content = (meta.get("content") or "").lower()
        if "noindex" in content:
            issues.append("noindex")
        if "nosnippet" in content:
            issues.append("nosnippet")
        # max-snippet:-1 means unlimited (permissive), only flag restrictive values
        max_snippet_match = re.search(r"max-snippet\s*:\s*(-?\d+)", content)
        if max_snippet_match:
            val = int(max_snippet_match.group(1))
            if val >= 0 and val < 300:
                issues.append(f"max-snippet:{val} (restrictive — limits snippet to {val} chars)")

    if issues:
        return TechnicalCheck(
            "noindex/nosnippet",
            False,
            f"Found directives: {', '.join(issues)}",
        )
    return TechnicalCheck("noindex/nosnippet", True, "No restrictive directives found")


def run_technical_checks(
    html: str, body_text: str, domain: Optional[str]
) -> list[TechnicalCheck]:
    """Run all technical checks, return list of results."""
    checks = []
    checks.extend(check_robots_txt(domain or ""))
    checks.append(check_llms_txt(domain or ""))
    checks.append(check_ssr(html, body_text))
    checks.append(check_schema_org(html))
    checks.append(check_canonical(html))
    checks.append(check_noindex_nosnippet(html))
    return checks


# ---------------------------------------------------------------------------
# Content signal scoring
# ---------------------------------------------------------------------------


def _get_h1(soup: BeautifulSoup) -> str:
    """Get H1 text from soup."""
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else ""


def _get_h2s(soup: BeautifulSoup) -> list[str]:
    """Get all H2 texts."""
    return [h2.get_text(strip=True) for h2 in soup.find_all("h2")]


def _get_sections(soup: BeautifulSoup) -> list[dict]:
    """
    Split content into sections by H2 headings.
    Returns list of {heading: str, text: str}.
    """
    sections = []
    current_heading = "(intro)"
    current_text_parts = []

    for el in soup.find_all(["h1", "h2", "h3", "p", "li", "div", "span", "blockquote"]):
        if el.name == "h2":
            if current_text_parts:
                sections.append({
                    "heading": current_heading,
                    "text": " ".join(current_text_parts),
                })
            current_heading = el.get_text(strip=True)
            current_text_parts = []
        elif el.name in ("p", "li", "blockquote"):
            text = el.get_text(strip=True)
            if text:
                current_text_parts.append(text)

    if current_text_parts:
        sections.append({
            "heading": current_heading,
            "text": " ".join(current_text_parts),
        })

    return sections


def score_first_30_answer(body_text: str, h1: str) -> ContentSignal:
    """Check if first 30% contains a direct answer to implied page question."""
    words = body_text.split()
    total = len(words)
    if total < 20:
        return ContentSignal(
            "first_30_answer", 0, "High",
            "Insufficient content to evaluate",
        )

    cutoff = max(20, int(total * 0.3))
    first_30 = " ".join(words[:cutoff])

    # Look for definitional patterns: "X is...", "X are...", "X refers to..."
    definitional_patterns = [
        r"(?:is|are|refers?\s+to|means?|involves?|describes?)\s+",
    ]

    has_definition = False
    for pattern in definitional_patterns:
        if re.search(pattern, first_30, re.IGNORECASE):
            has_definition = True
            break

    # Also check if a direct answer sentence exists (short declarative)
    sentences = re.split(r"[.!?]+", first_30)
    short_declarative = sum(
        1 for s in sentences
        if 5 <= len(s.split()) <= 30
        and re.search(r"\b(is|are|means?|provides?|helps?|allows?|enables?)\b", s, re.I)
    )

    score = 0
    evidence_parts = []

    if has_definition:
        score += 50
        evidence_parts.append("Definitional pattern found in first 30%")
    if short_declarative >= 1:
        score += 30
        evidence_parts.append(f"{short_declarative} short declarative sentence(s) in first 30%")
    if h1 and any(
        w.lower() in first_30.lower()
        for w in h1.split()
        if len(w) > 3
    ):
        score += 20
        evidence_parts.append("H1 keywords echoed in first 30%")

    score = min(score, 100)
    evidence = "; ".join(evidence_parts) if evidence_parts else "No direct answer pattern in first 30% of content"

    return ContentSignal("first_30_answer", score, "High", evidence)


def score_qa_h2s(h2s: list[str]) -> ContentSignal:
    """Check if >= 60% of H2s are in question form."""
    if not h2s:
        return ContentSignal("qa_h2s", 0, "High", "No H2 headings found")

    question_patterns = re.compile(
        r"^(what|how|why|when|where|who|which|can|does|do|is|are|should|will|would)\b",
        re.IGNORECASE,
    )
    question_count = sum(
        1 for h in h2s
        if question_patterns.search(h) or h.rstrip().endswith("?")
    )
    pct = 100 * question_count / len(h2s)

    if pct >= 60:
        score = 100
    elif pct >= 40:
        score = 70
    elif pct >= 20:
        score = 40
    else:
        score = 10 if question_count > 0 else 0

    return ContentSignal(
        "qa_h2s", score, "High",
        f"{question_count}/{len(h2s)} H2s in question form ({pct:.0f}%)",
    )


def score_entity_density(body_text: str) -> ContentSignal:
    """Check proper noun density >= 15% of word count."""
    words = body_text.split()
    total_words = len(words)
    if total_words < 20:
        return ContentSignal(
            "entity_density", 0, "High", "Insufficient content"
        )

    # Find capitalized sequences, but exclude sentence starters
    sentences = re.split(r"[.!?]\s+", body_text)
    sentence_starters = set()
    for s in sentences:
        s = s.strip()
        if s:
            first_word = s.split()[0] if s.split() else ""
            sentence_starters.add(first_word)

    # Common words that get capitalized at sentence starts — not entities
    COMMON_WORDS = {
        "The", "This", "That", "These", "Those", "It", "Its", "They", "Their",
        "There", "Here", "What", "When", "Where", "Which", "Who", "How", "Why",
        "Some", "Many", "Most", "All", "Each", "Every", "Any", "Both", "Few",
        "Several", "Other", "Another", "More", "Less", "Such", "Our", "Your",
        "His", "Her", "My", "We", "You", "One", "Two", "Three", "Four", "Five",
        "But", "And", "For", "Not", "Yet", "Also", "However", "Although",
        "While", "Since", "Because", "Before", "After", "During", "Between",
        "About", "Over", "Under", "Into", "With", "From", "Through",
        "According", "Based", "Using", "Given", "Despite", "Without",
        "Rather", "Instead", "Meanwhile", "Furthermore", "Moreover",
        "Additionally", "Finally", "First", "Second", "Third", "Last",
        "Next", "Then", "Now", "Still", "Just", "Even", "Only",
        "Retrieved", "Accessed", "Available", "Published", "Updated",
    }

    all_matches = PROPER_NOUN_RE.findall(body_text)
    entities = []
    for match in all_matches:
        first_w = match.split()[0]
        # Multi-word: filter if first word is common
        if " " in match:
            if first_w not in COMMON_WORDS:
                entities.append(match)
        # Single-word: skip common words and sentence starters
        elif first_w not in COMMON_WORDS and first_w not in sentence_starters:
            entities.append(match)

    unique_entities = set(entities)
    entity_word_count = sum(len(e.split()) for e in entities)
    density = 100 * entity_word_count / total_words if total_words else 0

    if density >= 15:
        score = 100
    elif density >= 10:
        score = 70
    elif density >= 5:
        score = 40
    else:
        score = max(0, int(density * 100 / 15))

    top_entities = sorted(
        set(entities), key=lambda e: entities.count(e), reverse=True
    )[:5]

    return ContentSignal(
        "entity_density", score, "High",
        f"Entity density: {density:.1f}% ({entity_word_count} entity words / {total_words} total). "
        f"Top entities: {', '.join(top_entities[:5])}",
    )


def score_definitive_openings(sections: list[dict]) -> ContentSignal:
    """Check if first sentence of each section uses definitive claim."""
    if not sections:
        return ContentSignal(
            "definitive_openings", 0, "Medium", "No sections found"
        )

    definitive_count = 0
    total = 0
    examples = []

    for sec in sections:
        text = sec["text"].strip()
        if not text:
            continue
        total += 1
        first_sentence = re.split(r"[.!?]", text)[0].strip()
        if not first_sentence:
            continue

        # "X is Y" pattern or direct claim (no hedging)
        is_definitive = bool(
            re.search(
                r"\b(is|are|was|were|means|refers?\s+to|provides?|represents?|includes?)\b",
                first_sentence,
                re.I,
            )
        )
        # Penalize hedging
        is_hedged = bool(
            re.search(
                r"\b(might|maybe|perhaps|possibly|could be|tends? to|generally|typically)\b",
                first_sentence,
                re.I,
            )
        )

        if is_definitive and not is_hedged:
            definitive_count += 1
        else:
            examples.append(
                f"[{sec['heading']}] \"{first_sentence[:80]}...\""
                if len(first_sentence) > 80
                else f"[{sec['heading']}] \"{first_sentence}\""
            )

    if total == 0:
        return ContentSignal("definitive_openings", 50, "Medium", "No parseable sections")

    pct = 100 * definitive_count / total
    score = min(100, int(pct))

    weak_examples = "; ".join(examples[:3])
    evidence = f"{definitive_count}/{total} sections open with definitive claims ({pct:.0f}%)"
    if weak_examples:
        evidence += f". Weak openers: {weak_examples}"

    return ContentSignal("definitive_openings", score, "Medium", evidence)


def score_chunk_independence(sections: list[dict]) -> ContentSignal:
    """Check that no section starts with context-dependent references."""
    if not sections:
        return ContentSignal(
            "chunk_independence", 0, "High", "No sections found"
        )

    dependent_count = 0
    dependent_examples = []

    for sec in sections:
        text = sec["text"].strip()
        if not text:
            continue
        first_sentence = text[:200]
        if DEPENDENT_OPENERS.search(first_sentence):
            dependent_count += 1
            dependent_examples.append(
                f"[{sec['heading']}] starts with: \"{first_sentence[:60]}...\""
            )

    total = len([s for s in sections if s["text"].strip()])
    if total == 0:
        return ContentSignal("chunk_independence", 50, "High", "No parseable sections")

    independent_pct = 100 * (total - dependent_count) / total
    score = min(100, int(independent_pct))

    evidence = f"{total - dependent_count}/{total} sections are self-contained ({independent_pct:.0f}%)"
    if dependent_examples:
        evidence += ". Dependent: " + "; ".join(dependent_examples[:3])

    return ContentSignal("chunk_independence", score, "High", evidence)


def score_sentiment_balance(sections: list[dict]) -> ContentSignal:
    """Check that no section is purely promotional or purely encyclopedic."""
    if not sections:
        return ContentSignal(
            "sentiment_balance", 50, "Medium", "No sections found"
        )

    issues = []
    total = 0

    for sec in sections:
        text = sec["text"].strip().lower()
        words = text.split()
        if len(words) < 10:
            continue
        total += 1

        superlative_count = sum(1 for w in words if w in SUPERLATIVES)
        opinion_count = sum(1 for w in words if w in OPINION_WORDS)
        superlative_pct = 100 * superlative_count / len(words)
        opinion_pct = 100 * opinion_count / len(words)

        if superlative_pct > 5:
            issues.append(f"[{sec['heading']}] Excessively promotional ({superlative_count} superlatives)")
        elif opinion_count == 0 and superlative_count == 0 and len(words) > 50:
            issues.append(f"[{sec['heading']}] Purely encyclopedic (zero opinion/stance words)")

    if total == 0:
        return ContentSignal("sentiment_balance", 50, "Medium", "No substantial sections")

    balanced_pct = 100 * (total - len(issues)) / total
    score = min(100, int(balanced_pct))

    evidence = f"{total - len(issues)}/{total} sections have balanced tone"
    if issues:
        evidence += ". Issues: " + "; ".join(issues[:3])

    return ContentSignal("sentiment_balance", score, "Medium", evidence)


def score_readability(body_text: str) -> ContentSignal:
    """Check Flesch-Kincaid Grade 14-17 (expert but accessible)."""
    if len(body_text.split()) < 30:
        return ContentSignal("readability", 50, "Low", "Too short for reliable readability score")

    grade = textstat.flesch_kincaid_grade(body_text)

    if 14 <= grade <= 17:
        score = 100
    elif 12 <= grade < 14 or 17 < grade <= 19:
        score = 70
    elif 10 <= grade < 12 or 19 < grade <= 21:
        score = 40
    else:
        score = 20

    return ContentSignal(
        "readability", score, "Low",
        f"Flesch-Kincaid Grade: {grade:.1f} (target: 14-17)",
    )


def score_length_match(body_text: str) -> ContentSignal:
    """Check word count: 500-2K for focused page, 5K+ for guide."""
    word_count = len(body_text.split())

    if 500 <= word_count <= 2000:
        score = 100
        label = "focused page range"
    elif word_count >= 5000:
        score = 90
        label = "category guide range"
    elif 2000 < word_count < 5000:
        score = 60
        label = "between focused and guide ranges"
    elif 300 <= word_count < 500:
        score = 40
        label = "slightly under focused minimum"
    elif word_count < 300:
        score = 15
        label = "very thin content"
    else:
        score = 50
        label = "unexpected range"

    return ContentSignal(
        "length_match", score, "Medium",
        f"{word_count} words ({label}). Target: 500-2K (focused) or 5K+ (guide)",
    )


def run_content_signals(
    body_text: str, soup: BeautifulSoup
) -> list[ContentSignal]:
    """Run all 8 content signals and return scored results."""
    h1 = _get_h1(soup)
    h2s = _get_h2s(soup)
    sections = _get_sections(soup)

    return [
        score_first_30_answer(body_text, h1),
        score_qa_h2s(h2s),
        score_entity_density(body_text),
        score_definitive_openings(sections),
        score_chunk_independence(sections),
        score_sentiment_balance(sections),
        score_readability(body_text),
        score_length_match(body_text),
    ]


def compute_overall_score(signals: list[ContentSignal]) -> float:
    """Weighted average of content signal scores."""
    total_weight = 0
    weighted_sum = 0
    for sig in signals:
        w = SIGNAL_WEIGHTS.get(sig.name, 1)
        weighted_sum += sig.score * w
        total_weight += w
    return round(weighted_sum / total_weight, 1) if total_weight else 0.0


# ---------------------------------------------------------------------------
# High-risk tactic detection
# ---------------------------------------------------------------------------


def detect_rapid_ai_scaling(body_text: str, entity_density_score: int) -> RiskFlag:
    """Detect AI-generated content patterns."""
    words = body_text.split()
    word_count = len(words)
    issues = []

    # High word count + low entity density + repetitive phrasing
    if word_count > 2000 and entity_density_score < 30:
        issues.append("High word count with low entity density")

    # Check for repetitive sentence starters (AI tell)
    sentences = re.split(r"[.!?]\s+", body_text)
    if len(sentences) > 10:
        starters = [" ".join(s.split()[:3]).lower() for s in sentences if s.strip()]
        starter_counts = {}
        for s in starters:
            starter_counts[s] = starter_counts.get(s, 0) + 1
        most_repeated = max(starter_counts.values()) if starter_counts else 0
        repetition_pct = 100 * most_repeated / len(starters) if starters else 0
        if repetition_pct > 20:
            issues.append(f"Repetitive sentence starters ({repetition_pct:.0f}% share same opener)")

    # Check for filler phrases common in AI content
    filler_patterns = [
        r"in today'?s (?:digital|modern|fast-paced|ever-changing)",
        r"it'?s (?:important|worth|crucial|essential) to (?:note|understand|remember)",
        r"when it comes to",
        r"at the end of the day",
        r"in (?:this|the) (?:comprehensive|ultimate|complete) guide",
    ]
    filler_count = sum(
        len(re.findall(p, body_text, re.I)) for p in filler_patterns
    )
    if filler_count >= 3:
        issues.append(f"{filler_count} AI-typical filler phrases detected")

    detected = len(issues) > 0
    detail = "; ".join(issues) if issues else "No AI scaling patterns detected"
    return RiskFlag("Rapid AI content scaling", detected, detail)


def detect_artificial_refresh(html: str, body_text: str) -> RiskFlag:
    """Detect 'Updated: [date]' without substantive change signals."""
    # Look for "Updated" / "Last updated" dates
    date_patterns = re.findall(
        r"(?:updated|last\s+updated|modified|revised)[:\s]+(\w+\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})",
        html,
        re.IGNORECASE,
    )
    if not date_patterns:
        return RiskFlag("Artificial content refreshing", False, "No update date found")

    # Can only partially detect from single fetch — flag as informational
    return RiskFlag(
        "Artificial content refreshing",
        False,  # Can't confirm from single fetch, just note
        f"Update date found: {date_patterns[0]}. "
        f"Single-fetch limitation: cannot confirm whether update was substantive.",
    )


def detect_self_promotional_listicle(
    body_text: str, h1: str, brand: Optional[str]
) -> RiskFlag:
    """Detect 'best X' / 'top X' lists where the page's brand is ranked #1."""
    if not brand:
        return RiskFlag(
            "Self-promotional listicle", False,
            "No brand provided — skipped detection",
        )

    # Check if it's a listicle
    is_listicle = bool(re.search(
        r"\b(best|top|leading|greatest)\s+\d*\s*\w+",
        h1 or body_text[:300],
        re.I,
    ))

    if not is_listicle:
        return RiskFlag("Self-promotional listicle", False, "Not a listicle format")

    # Check if brand appears first in a numbered or bulleted list
    lines = body_text.splitlines()
    brand_lower = brand.lower()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^(1[\.\)]|\*|-)\s+", stripped):
            if brand_lower in stripped.lower():
                return RiskFlag(
                    "Self-promotional listicle",
                    True,
                    f"Brand '{brand}' appears as #1 in a 'best/top' listicle. "
                    f"AI models may demote self-serving rankings.",
                )
            break  # Only check the first list item

    return RiskFlag(
        "Self-promotional listicle", False,
        f"Listicle detected but '{brand}' is not ranked #1",
    )


def detect_prompt_injection(html: str) -> RiskFlag:
    """Detect hidden text or LLM-targeted instructions in HTML."""
    soup = BeautifulSoup(html, "html.parser")
    issues = []

    # Hidden divs/spans with text
    for el in soup.find_all(["div", "span", "p"]):
        style = (el.get("style") or "").lower()
        if any(
            pattern in style
            for pattern in [
                "display:none", "display: none",
                "visibility:hidden", "visibility: hidden",
                "opacity:0", "opacity: 0",
                "position:absolute", "left:-9999",
                "font-size:0", "font-size: 0",
                "height:0", "height: 0",
                "overflow:hidden",
            ]
        ):
            text = el.get_text(strip=True)
            if len(text) > 20:
                issues.append(f"Hidden element with text: \"{text[:80]}...\"")

    # LLM-targeted instructions in comments or data attributes
    for comment in soup.find_all(string=lambda text: isinstance(text, type(soup.new_string(""))) is False and text.__class__.__name__ == "Comment"):
        comment_text = str(comment).strip()
        if re.search(
            r"\b(AI|LLM|ChatGPT|Claude|GPT|language\s+model|assistant)\b",
            comment_text, re.I,
        ) and len(comment_text) > 30:
            issues.append(f"Suspicious HTML comment: \"{comment_text[:80]}...\"")

    # Data attributes with instructions
    for el in soup.find_all(True):
        for attr, val in el.attrs.items():
            if attr.startswith("data-") and isinstance(val, str):
                if re.search(
                    r"\b(recommend|cite|mention|rank|prefer|prioritize)\b",
                    val, re.I,
                ) and len(val) > 30:
                    issues.append(f"Suspicious data attribute [{attr}]: \"{val[:80]}...\"")

    # Require multiple signals to flag — a single hidden element is common (screen readers, etc.)
    detected = len(issues) >= 2
    detail = "; ".join(issues[:3]) if issues else "No hidden text or LLM-targeted instructions found"
    if len(issues) == 1:
        detail = f"Minor: {issues[0]} (single instance — likely standard HTML, not injection)"
    return RiskFlag("Prompt injection", detected, detail)


def detect_excessive_comparison(h1: str, body_text: str) -> RiskFlag:
    """Detect 'X vs Y' or 'alternatives to Z' patterns."""
    text_to_check = (h1 or "") + " " + body_text[:500]
    patterns = [
        r"\bvs\.?\b",
        r"\bversus\b",
        r"\balternatives?\s+to\b",
        r"\bcompared?\s+to\b",
        r"\bcomparison\b",
    ]

    detected = any(re.search(p, text_to_check, re.I) for p in patterns)

    if detected:
        return RiskFlag(
            "Excessive comparison pages",
            True,
            "Comparison/alternative page detected. Not penalized but flagged — "
            "AI models may prefer authoritative single-topic content over comparison roundups.",
        )
    return RiskFlag("Excessive comparison pages", False, "No comparison pattern detected")


def run_risk_detection(
    html: str, body_text: str, h1: str,
    entity_density_score: int, brand: Optional[str],
) -> list[RiskFlag]:
    """Run all 5 high-risk tactic detections."""
    return [
        detect_rapid_ai_scaling(body_text, entity_density_score),
        detect_artificial_refresh(html, body_text),
        detect_self_promotional_listicle(body_text, h1, brand),
        detect_prompt_injection(html),
        detect_excessive_comparison(h1, body_text),
    ]


# ---------------------------------------------------------------------------
# Passage extraction
# ---------------------------------------------------------------------------


def extract_passages(
    body_text: str, sections: list[dict]
) -> tuple[list[str], list[str]]:
    """
    Extract top 3 most-quotable and weakest passages.
    Quotable = short, definitive, entity-rich.
    Weak = long, hedging, low-info.
    """
    candidates = []

    for sec in sections:
        sentences = re.split(r"[.!?]+", sec["text"])
        for sent in sentences:
            sent = sent.strip()
            words = sent.split()
            if len(words) < 8 or len(words) > 50:
                continue

            # Score quotability
            q_score = 0
            # Entity-rich
            entities = PROPER_NOUN_RE.findall(sent)
            q_score += min(30, len(entities) * 10)
            # Definitive
            if re.search(r"\b(is|are|means?|defines?|refers? to)\b", sent, re.I):
                q_score += 25
            # Concise (15-25 words is ideal)
            if 15 <= len(words) <= 25:
                q_score += 20
            # Contains numbers/data
            if re.search(r"\d+", sent):
                q_score += 15
            # Hedging penalty
            if re.search(r"\b(might|maybe|perhaps|possibly|could be)\b", sent, re.I):
                q_score -= 20
            # Filler penalty
            if re.search(r"\b(it'?s important to note|when it comes to)\b", sent, re.I):
                q_score -= 20

            candidates.append((sent, q_score, sec["heading"]))

    candidates.sort(key=lambda x: x[1], reverse=True)

    quotable = [
        f"[{c[2]}] \"{c[0]}\""
        for c in candidates[:3]
    ]
    weak = [
        f"[{c[2]}] \"{c[0]}\""
        for c in candidates[-3:]
    ] if len(candidates) >= 6 else [
        f"[{c[2]}] \"{c[0]}\""
        for c in candidates[-min(3, len(candidates)):]
    ]

    return quotable, weak


# ---------------------------------------------------------------------------
# Recommendation generation
# ---------------------------------------------------------------------------


def generate_recommendations(
    signals: list[ContentSignal],
    tech_checks: list[TechnicalCheck],
    risk_flags: list[RiskFlag],
) -> list[Recommendation]:
    """Generate prioritized fix list with SEO/GEO labels."""
    recs = []

    signal_map = {s.name: s for s in signals}

    # Content signal-based recommendations
    if signal_map.get("first_30_answer", ContentSignal("", 100, "", "")).score < 70:
        recs.append(Recommendation(
            "[SEO+/GEO+]",
            "Add a direct, definitional answer in the first 30% of content. "
            "Lead with the answer, not background.",
            "S", "high",
        ))

    if signal_map.get("qa_h2s", ContentSignal("", 100, "", "")).score < 70:
        recs.append(Recommendation(
            "[SEO+/GEO+]",
            "Rewrite H2 headings as questions matching user queries. "
            "Target >= 60% of H2s in question form.",
            "S", "high",
        ))

    if signal_map.get("entity_density", ContentSignal("", 100, "", "")).score < 70:
        recs.append(Recommendation(
            "[SEO+/GEO+]",
            "Increase named entity density: add specific people, organizations, products, "
            "technologies, and locations. Target >= 15% proper noun density.",
            "M", "high",
        ))

    if signal_map.get("definitive_openings", ContentSignal("", 100, "", "")).score < 70:
        recs.append(Recommendation(
            "[GEO+ only]",
            "Rewrite section openers to use definitive 'X is Y' claims "
            "instead of hedged or vague introductions.",
            "S", "med",
        ))

    if signal_map.get("chunk_independence", ContentSignal("", 100, "", "")).score < 70:
        recs.append(Recommendation(
            "[GEO+ only]",
            "Make each section self-contained. Remove 'As mentioned above', "
            "'This', 'These' references to prior sections. "
            "Each chunk should be quotable standalone.",
            "M", "high",
        ))

    if signal_map.get("sentiment_balance", ContentSignal("", 100, "", "")).score < 70:
        recs.append(Recommendation(
            "[SEO+/GEO+]",
            "Balance promotional and informational tone. "
            "Reduce superlatives in promotional sections; "
            "add opinion/stance words to encyclopedic sections.",
            "M", "med",
        ))

    if signal_map.get("readability", ContentSignal("", 100, "", "")).score < 70:
        recs.append(Recommendation(
            "[SEO+/GEO+]",
            "Adjust readability to Flesch-Kincaid Grade 14-17 range "
            "(expert but accessible).",
            "M", "low",
        ))

    if signal_map.get("length_match", ContentSignal("", 100, "", "")).score < 70:
        recs.append(Recommendation(
            "[SEO+/GEO+]",
            "Adjust content length to target range: "
            "500-2K words for focused pages, 5K+ for category guides.",
            "L", "med",
        ))

    # Technical check recommendations
    for check in tech_checks:
        if not check.passed:
            if "robots.txt" in check.name and "BLOCKED" in check.detail:
                recs.append(Recommendation(
                    "[GEO+ but SEO-]",
                    f"Unblock AI crawler in robots.txt: {check.name}. "
                    f"WARNING: May increase crawl load. Evaluate trade-off.",
                    "S", "high",
                ))
            elif "llms.txt" in check.name:
                recs.append(Recommendation(
                    "[GEO+ only]",
                    "Add llms.txt file to help AI systems understand site context.",
                    "S", "med",
                ))
            elif "Schema.org" in check.name:
                recs.append(Recommendation(
                    "[SEO+/GEO+]",
                    "Add JSON-LD structured data (Article, FAQPage, HowTo, etc.).",
                    "M", "high",
                ))
            elif "Canonical" in check.name:
                recs.append(Recommendation(
                    "[SEO+/GEO+]",
                    "Add canonical tag to consolidate ranking signals.",
                    "S", "med",
                ))
            elif "noindex" in check.name:
                recs.append(Recommendation(
                    "[SEO+/GEO+]",
                    f"Review restrictive meta directives: {check.detail}. "
                    f"These may prevent AI citation.",
                    "S", "high",
                ))
            elif "SSR" in check.name:
                recs.append(Recommendation(
                    "[SEO+/GEO+]",
                    "Enable server-side rendering. JS-rendered content may not "
                    "be visible to AI crawlers.",
                    "L", "high",
                ))

    # Risk flag recommendations
    for flag in risk_flags:
        if flag.detected:
            if "AI content" in flag.name:
                recs.append(Recommendation(
                    "[SEO+/GEO+]",
                    "Reduce AI-generated content signals: diversify sentence starters, "
                    "remove filler phrases, add original data/quotes.",
                    "L", "high",
                ))
            elif "listicle" in flag.name:
                recs.append(Recommendation(
                    "[SEO+/GEO+]",
                    "Remove self-promotional bias from listicle. "
                    "Either rank objectively or disclose affiliation prominently.",
                    "M", "high",
                ))
            elif "injection" in flag.name:
                recs.append(Recommendation(
                    "[SEO+/GEO+]",
                    "Remove hidden text and LLM-targeted instructions. "
                    "These may trigger penalties in AI ranking.",
                    "S", "high",
                ))

    # Sort: high impact first, then by effort (S before M before L)
    impact_order = {"high": 0, "med": 1, "low": 2}
    effort_order = {"S": 0, "M": 1, "L": 2}
    recs.sort(key=lambda r: (impact_order.get(r.impact, 9), effort_order.get(r.effort, 9)))

    return recs


# ---------------------------------------------------------------------------
# Single-URL audit orchestration
# ---------------------------------------------------------------------------


def audit_html(
    html: str,
    url: str,
    domain: Optional[str],
    brand: Optional[str],
    run_remote_checks: bool = True,
) -> AuditResult:
    """Score pre-fetched HTML. Used by audit_url and by sibling tools that want
    to audit raw content (e.g., a markdown rewrite converted to HTML) without
    re-fetching. When run_remote_checks=False, skips robots.txt + llms.txt
    network calls — right for local content that isn't yet published.
    """
    slug = url_to_slug(url)
    result = AuditResult(url=url, slug=slug, fetch_ok=True)

    if not domain:
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain.startswith("www."):
            domain = domain[4:]

    title, body_text, soup = extract_content(html)
    result.title = title
    result.word_count = len(body_text.split())
    result.js_rendered_warning = detect_js_rendered(html, body_text)

    if run_remote_checks:
        result.technical_checks = run_technical_checks(html, body_text, domain)
    else:
        result.technical_checks = [
            check_ssr(html, body_text),
            check_schema_org(html),
            check_canonical(html),
            check_noindex_nosnippet(html),
        ]

    result.content_signals = run_content_signals(body_text, soup)
    result.overall_score = compute_overall_score(result.content_signals)

    h1 = _get_h1(soup)
    entity_score = next(
        (s.score for s in result.content_signals if s.name == "entity_density"), 50
    )
    result.risk_flags = run_risk_detection(html, body_text, h1, entity_score, brand)

    result.recommendations = generate_recommendations(
        result.content_signals, result.technical_checks, result.risk_flags
    )

    sections = _get_sections(soup)
    result.quotable_passages, result.weak_passages = extract_passages(body_text, sections)

    return result


def audit_url(
    url: str,
    domain: Optional[str],
    brand: Optional[str],
) -> AuditResult:
    """Fetch URL and run full audit. Returns AuditResult."""
    slug = url_to_slug(url)
    html, fetch_error = fetch_html(url)
    if fetch_error:
        return AuditResult(url=url, slug=slug, fetch_ok=False, error=fetch_error)
    return audit_html(html, url, domain, brand, run_remote_checks=True)


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------


def write_audit_md(result: AuditResult, out_dir: Path) -> Path:
    """Write per-URL audit markdown file."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = out_dir / f"{result.slug}_audit.md"

    lines = []
    lines.append(f"# GEO Audit: {result.title or result.url}")
    lines.append("")
    lines.append(f"**URL:** {result.url}")
    lines.append(f"**Audit date:** {today}")
    lines.append(f"**Overall content score:** {result.overall_score}/100")
    lines.append(f"**Word count:** {result.word_count}")
    lines.append("")

    if result.js_rendered_warning:
        lines.append("> **WARNING:** JS-rendered page — audit may be incomplete. "
                      "Consider using a browser-rendered version.")
        lines.append("")

    if not result.fetch_ok:
        lines.append(f"**Error:** {result.error}")
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out_path

    # Technical checks
    lines.append("## Technical Checks")
    lines.append("")
    for check in result.technical_checks:
        icon = "PASS" if check.passed else "FAIL"
        lines.append(f"- **[{icon}]** {check.name}: {check.detail}")
    lines.append("")

    # Content signals
    lines.append("## Content Signals (8-signal rubric)")
    lines.append("")
    lines.append("| Signal | Score | Weight | Evidence |")
    lines.append("|---|---|---|---|")
    for sig in result.content_signals:
        evidence_short = sig.evidence[:120] + "..." if len(sig.evidence) > 120 else sig.evidence
        lines.append(f"| {sig.name} | {sig.score}/100 | {sig.weight_label} | {evidence_short} |")
    lines.append("")
    lines.append(f"**Weighted overall: {result.overall_score}/100**")
    lines.append("")

    # Detailed evidence (expanded)
    lines.append("### Signal Details")
    lines.append("")
    for sig in result.content_signals:
        lines.append(f"**{sig.name}** ({sig.score}/100, {sig.weight_label} weight)")
        lines.append(f": {sig.evidence}")
        lines.append("")

    # Risk flags
    lines.append("## High-Risk Tactic Detection")
    lines.append("")
    for flag in result.risk_flags:
        icon = "FLAG" if flag.detected else "CLEAR"
        lines.append(f"- **[{icon}]** {flag.name}: {flag.detail}")
    lines.append("")

    # Prioritized fix list
    lines.append("## Prioritized Fix List")
    lines.append("")
    if result.recommendations:
        lines.append("| # | Label | Recommendation | Effort | Impact |")
        lines.append("|---|---|---|---|---|")
        for i, rec in enumerate(result.recommendations, 1):
            desc_short = rec.description[:100] + "..." if len(rec.description) > 100 else rec.description
            lines.append(f"| {i} | {rec.label} | {desc_short} | {rec.effort} | {rec.impact} |")
        lines.append("")

        # Expanded recommendations
        lines.append("### Detailed Recommendations")
        lines.append("")
        for i, rec in enumerate(result.recommendations, 1):
            lines.append(f"**{i}. {rec.label}** (effort: {rec.effort}, impact: {rec.impact})")
            lines.append(f": {rec.description}")
            lines.append("")
    else:
        lines.append("No high-priority fixes identified.")
        lines.append("")

    # Passages
    lines.append("## Sample Passages")
    lines.append("")
    lines.append("### Most Quotable (citation-worthy)")
    lines.append("")
    if result.quotable_passages:
        for p in result.quotable_passages:
            lines.append(f"- {p}")
    else:
        lines.append("_No strong quotable passages identified._")
    lines.append("")

    lines.append("### Weakest (need improvement)")
    lines.append("")
    if result.weak_passages:
        for p in result.weak_passages:
            lines.append(f"- {p}")
    else:
        lines.append("_N/A_")
    lines.append("")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def write_batch_summary(results: list[AuditResult], out_dir: Path) -> Path:
    """Write batch summary markdown."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = out_dir / "batch_audit_summary.md"

    lines = []
    lines.append("# GEO Audit — Batch Summary")
    lines.append("")
    lines.append(f"**Audit date:** {today}")
    lines.append(f"**URLs audited:** {len(results)}")
    lines.append("")

    # Aggregate scores
    scored = [r for r in results if r.fetch_ok]
    failed = [r for r in results if not r.fetch_ok]

    if scored:
        avg_score = sum(r.overall_score for r in scored) / len(scored)
        min_r = min(scored, key=lambda r: r.overall_score)
        max_r = max(scored, key=lambda r: r.overall_score)

        lines.append("## Score Overview")
        lines.append("")
        lines.append(f"- **Average score:** {avg_score:.1f}/100")
        lines.append(f"- **Highest:** {max_r.overall_score}/100 — {max_r.url}")
        lines.append(f"- **Lowest:** {min_r.overall_score}/100 — {min_r.url}")
        lines.append("")

        # Per-URL table
        lines.append("## Per-URL Scores")
        lines.append("")
        lines.append("| URL | Score | Word Count | Risk Flags | Top Issue |")
        lines.append("|---|---|---|---|---|")
        for r in sorted(scored, key=lambda x: x.overall_score):
            risk_count = sum(1 for f in r.risk_flags if f.detected)
            top_issue = r.recommendations[0].description[:60] + "..." if r.recommendations else "None"
            url_short = r.url[:80] + "..." if len(r.url) > 80 else r.url
            lines.append(f"| {url_short} | {r.overall_score}/100 | {r.word_count} | {risk_count} | {top_issue} |")
        lines.append("")

        # Common issues across URLs
        lines.append("## Common Issues")
        lines.append("")
        issue_counts: dict[str, int] = {}
        for r in scored:
            for sig in r.content_signals:
                if sig.score < 70:
                    issue_counts[sig.name] = issue_counts.get(sig.name, 0) + 1

        if issue_counts:
            sorted_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
            for name, count in sorted_issues:
                pct = 100 * count / len(scored)
                lines.append(f"- **{name}:** failing on {count}/{len(scored)} pages ({pct:.0f}%)")
        else:
            lines.append("_No common issues across pages._")
        lines.append("")

        # Recommended fix order
        lines.append("## Recommended Fix Order")
        lines.append("")
        lines.append("Prioritized by: frequency x impact across all pages.")
        lines.append("")

        # Aggregate recommendations
        rec_scores: dict[str, dict] = {}
        for r in scored:
            for rec in r.recommendations:
                key = rec.description[:80]
                if key not in rec_scores:
                    rec_scores[key] = {
                        "label": rec.label,
                        "description": rec.description,
                        "effort": rec.effort,
                        "impact": rec.impact,
                        "count": 0,
                    }
                rec_scores[key]["count"] += 1

        impact_val = {"high": 3, "med": 2, "low": 1}
        sorted_recs = sorted(
            rec_scores.values(),
            key=lambda x: x["count"] * impact_val.get(x["impact"], 1),
            reverse=True,
        )
        for i, rec in enumerate(sorted_recs[:10], 1):
            lines.append(
                f"{i}. {rec['label']} ({rec['count']}/{len(scored)} pages, "
                f"effort: {rec['effort']}, impact: {rec['impact']})"
            )
            lines.append(f"   {rec['description']}")
            lines.append("")

    if failed:
        lines.append("## Failed URLs")
        lines.append("")
        for r in failed:
            lines.append(f"- {r.url}: {r.error}")
        lines.append("")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def load_urls_from_csv(path: Path) -> list[str]:
    """Load URLs from CSV — one URL per line, or column named 'url'."""
    urls = []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames and "url" in [fn.lower() for fn in reader.fieldnames]:
                # Find the actual column name (case-insensitive)
                url_col = next(fn for fn in reader.fieldnames if fn.lower() == "url")
                for row in reader:
                    u = row[url_col].strip()
                    if u:
                        urls.append(u)
            else:
                # Fall back to first column or one-per-line
                f.seek(0)
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        # Take first comma-separated value
                        url = line.split(",")[0].strip().strip('"')
                        if url.startswith("http"):
                            urls.append(url)
    except Exception as e:
        die(f"Failed to read URLs from {path}: {e}")

    return urls


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", type=str, help="Single URL to audit")
    parser.add_argument("--urls", type=Path, help="CSV file with URLs (one per line or 'url' column)")
    parser.add_argument("--output", type=Path, required=True, help="Output directory for audit reports")
    parser.add_argument("--brand", type=str, default=None, help="Brand name for self-promotional listicle detection")
    parser.add_argument("--domain", type=str, default=None, help="Domain for robots.txt / llms.txt checks (inferred from URL if omitted)")
    opts = parser.parse_args()

    if not opts.url and not opts.urls:
        die("Provide --url or --urls")
    if opts.url and opts.urls:
        die("Provide --url or --urls, not both")

    # Collect URLs
    urls = []
    if opts.url:
        urls = [opts.url]
    else:
        if not opts.urls.exists():
            die(f"File not found: {opts.urls}")
        urls = load_urls_from_csv(opts.urls)
        if not urls:
            die(f"No valid URLs found in {opts.urls}")

    opts.output.mkdir(parents=True, exist_ok=True)

    # Run audits
    results: list[AuditResult] = []
    total = len(urls)
    for i, url in enumerate(urls, 1):
        if total > 1:
            print(f"[{i}/{total}] Auditing: {url}", file=sys.stderr)
        else:
            print(f"Auditing: {url}", file=sys.stderr)

        result = audit_url(url, opts.domain, opts.brand)
        results.append(result)

        # Write individual report
        out_file = write_audit_md(result, opts.output)
        if result.fetch_ok:
            print(f"  Score: {result.overall_score}/100 -> {out_file}", file=sys.stderr)
        else:
            print(f"  FAILED: {result.error} -> {out_file}", file=sys.stderr)

    # Write batch summary (even for single URL, useful context)
    if total > 1:
        summary_path = write_batch_summary(results, opts.output)
        print(f"\nBatch summary -> {summary_path}", file=sys.stderr)

    # Report
    succeeded = sum(1 for r in results if r.fetch_ok)
    failed = total - succeeded
    print(f"\nDone. {succeeded}/{total} URLs audited successfully.", file=sys.stderr)

    if failed > 0 and succeeded > 0:
        return 1  # partial success
    elif failed == total:
        return 2  # total failure
    return 0


if __name__ == "__main__":
    sys.exit(main())
