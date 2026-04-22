#!/usr/bin/env python3
"""
Validate content restructures for /cmo/geo/content-restructure.

Deterministic checks only — no LLM calls. Reuses geo_audit.py's scoring
engine so the pre/post audit uses the same Framework 02 rubric.

Subcommands:
  extract-facts     Pull numbers, named entities, and quoted claims from
                    the source. Writes facts.json — used at the checkpoint
                    to show the operator exactly what must be preserved.
  detect-ymyl       Classify the source as YMYL (medical / legal / financial).
                    Exit 0 = not YMYL, exit 10 = YMYL (skill uses this as a gate).
  diff-report       Main command. Pre/post audit scorecards + preservation check
                    + voice markers diff + section mapping + length delta.
                    Writes <slug>_audit_diff.md.

Source can be a URL (fetched) or a local file (.md or .html).

Usage:
    python3 tools/geo_restructure_diff.py extract-facts \\
        --source https://example.com/page --output .tmp/geo/restructure/slug/

    python3 tools/geo_restructure_diff.py detect-ymyl \\
        --source clients/foo/content/page.md

    python3 tools/geo_restructure_diff.py diff-report \\
        --source https://example.com/page \\
        --rewrite .tmp/geo/restructure/slug/rewrite.md \\
        --output .tmp/geo/restructure/slug/

Requires: requests, beautifulsoup4, markdown, textstat (via geo_audit)
Exit codes: 0 success, 2 argument/setup error, 10 YMYL detected
"""
import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import requests
except ImportError:
    print("ERROR: pip install --user requests", file=sys.stderr)
    sys.exit(2)

try:
    import markdown as md_lib
except ImportError:
    print("ERROR: pip install --user markdown", file=sys.stderr)
    sys.exit(2)

from bs4 import BeautifulSoup

# Reuse the audit engine so pre/post scores use the same rubric
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.geo_audit import (  # noqa: E402
    AuditResult,
    PROPER_NOUN_RE,
    audit_html,
    url_to_slug,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30

# Length budget thresholds (as fraction of source word count)
LENGTH_WARN_THRESHOLD = 1.20   # soft warn
LENGTH_FAIL_THRESHOLD = 1.50   # hard fail — drifted into new-page territory
LENGTH_MIN_THRESHOLD = 0.50    # hard fail — too aggressive a cut

# YMYL term lists — compact, high-signal. Threshold: ≥1% of total words
# in any category = YMYL flag.
YMYL_MEDICAL = {
    "patient", "patients", "clinical", "diagnosis", "diagnose", "diagnosed",
    "treatment", "treat", "treats", "therapy", "therapeutic", "therapies",
    "medication", "drug", "drugs", "prescription", "prescribe", "symptom",
    "symptoms", "disease", "condition", "disorder", "disorders", "physician",
    "doctor", "doctors", "nurse", "hospital", "surgical", "surgery", "surgeon",
    "medical", "healthcare", "pharmacology", "pharmacy", "diagnostic",
    "procedure", "procedures", "dose", "dosage", "dosing", "adverse",
    "contraindication", "indication", "indicated", "cardiac", "cardiovascular",
    "renal", "hepatic", "neurological", "oncology", "oncologic", "pediatric",
    "geriatric", "placebo", "efficacy", "morbidity", "mortality", "fda",
    "chronic", "acute", "infection", "infectious", "inflammatory", "tumor",
    "malignant", "benign", "lesion", "clinical trial",
}

YMYL_LEGAL = {
    "lawsuit", "litigation", "litigate", "attorney", "lawyer", "counsel",
    "court", "judge", "jury", "plaintiff", "defendant", "contract",
    "agreement", "clause", "statute", "statutory", "regulation", "regulatory",
    "compliance", "compliant", "liability", "damages", "indemnification",
    "indemnify", "jurisdiction", "legal", "illegal", "lawful", "unlawful",
    "injunction", "breach", "settlement", "arbitration", "mediation",
    "deposition", "subpoena", "tort", "gdpr", "hipaa", "ccpa", "sox",
    "copyright", "trademark", "patent", "infringement",
}

YMYL_FINANCIAL = {
    "investment", "investor", "investors", "portfolio", "securities",
    "stock", "stocks", "bond", "bonds", "equity", "annuity", "ira",
    "retirement", "tax", "taxes", "taxable", "brokerage", "dividend",
    "dividends", "fiduciary", "finra", "sec", "insurance", "premium",
    "mortgage", "loan", "credit", "debt", "fiscal", "earnings", "yield",
    "apr", "apy", "interest rate", "capital gains", "mutual fund",
    "hedge fund", "etf",
}

# Voice marker patterns
EM_DASH_RE = re.compile(r"—|--")
HEDGING_RE = re.compile(
    r"\b(might|maybe|perhaps|possibly|could be|tends? to|generally|typically|"
    r"often|sometimes|seemingly|arguably|reportedly|apparently|allegedly)\b",
    re.IGNORECASE,
)
FILLER_RE = re.compile(
    r"\b(when it comes to|in today'?s|it'?s (?:important|worth|crucial|essential) to (?:note|understand|remember)|"
    r"at the end of the day|in (?:this|the) (?:comprehensive|ultimate|complete) guide|"
    r"navigating the|unlock(?:ing)? the (?:power|potential)|"
    r"in an (?:era|age) of|in the (?:modern|digital) (?:world|age|era))\b",
    re.IGNORECASE,
)

# Number tokens: integers, decimals, percentages, currency, multipliers
# \d+(?:,\d{3})* requires thousands-separator commas to be followed by 3 digits,
# so "1999," doesn't capture the trailing comma.
NUMBER_RE = re.compile(
    r"(?<![A-Za-z])"
    r"("
    r"\$\s?\d+(?:,\d{3})*(?:\.\d+)?[KMB]?"        # currency: $1,200.50, $3K
    r"|\d+(?:,\d{3})*(?:\.\d+)?\s?%"              # percent: 44.2%
    r"|\d+(?:\.\d+)?\s?x\b"                       # multiplier: 3.5x
    r"|\d{4}-\d{2}-\d{2}"                         # ISO date
    r"|\d+(?:,\d{3})*(?:\.\d+)?"                  # plain number: 500, 20,000
    r")"
    r"(?![A-Za-z])",
)

# Common-word filter shared with geo_audit's entity density signal — duplicated
# here to keep the tools loosely coupled. Keep in sync.
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


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Facts:
    """What must be preserved across a restructure."""
    numbers: list = field(default_factory=list)        # list of str tokens
    entities: list = field(default_factory=list)       # list of str (multi-word proper noun phrases)
    quoted_claims: list = field(default_factory=list)  # list of str sentences
    source: str = ""
    slug: str = ""
    word_count: int = 0


@dataclass
class YMYLReport:
    is_ymyl: bool = False
    medical_density_pct: float = 0.0
    legal_density_pct: float = 0.0
    financial_density_pct: float = 0.0
    top_category: str = ""
    word_count: int = 0


@dataclass
class VoiceMarkers:
    em_dash_count: int = 0
    hedging_count: int = 0
    filler_count: int = 0
    parenthetical_count: int = 0
    sentence_count: int = 0
    the_or_this_starter_pct: float = 0.0
    avg_sentence_length: float = 0.0


# ---------------------------------------------------------------------------
# Source loading (URL, .md, .html)
# ---------------------------------------------------------------------------


def die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def load_source(source: str) -> tuple[str, str, str]:
    """
    Return (html, body_text, identifier) for a source.
    Source can be http(s) URL, local .md file, or local .html file.
    identifier is the URL or file path — used as the 'url' param for audit_html.
    """
    if source.startswith("http://") or source.startswith("https://"):
        try:
            resp = requests.get(
                source,
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            die(f"Could not fetch {source}: {e}")
        html = resp.text
        body = BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)
        return html, body, source

    path = Path(source)
    if not path.exists():
        die(f"Source not found: {source}")

    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".md", ".markdown"):
        html = md_lib.markdown(raw, extensions=["extra", "tables"])
    elif path.suffix.lower() in (".html", ".htm"):
        html = raw
    else:
        # Treat unknown as markdown — most common case
        html = md_lib.markdown(raw, extensions=["extra", "tables"])

    body = BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)
    return html, body, str(path)


def source_to_slug(source: str) -> str:
    if source.startswith("http://") or source.startswith("https://"):
        return url_to_slug(source)
    return Path(source).stem


# ---------------------------------------------------------------------------
# Fact extraction
# ---------------------------------------------------------------------------


def extract_numbers(body: str) -> list[str]:
    """Pull every distinct numeric token. Preserves duplicates in document order
    so a 44.2% cited twice counts twice — the preservation check is per-occurrence."""
    return [m.group(1).strip() for m in NUMBER_RE.finditer(body)]


def extract_entities(body: str) -> list[str]:
    """Multi-word proper noun phrases, plus single-word non-common capitalized
    terms that aren't sentence starters. Mirrors geo_audit's entity density logic
    so the checkpoint 'entities to preserve' list matches what the audit rewards."""
    sentences = re.split(r"[.!?]\s+", body)
    sentence_starters = set()
    for s in sentences:
        s = s.strip()
        if s and s.split():
            sentence_starters.add(s.split()[0])

    entities: list[str] = []
    for m in PROPER_NOUN_RE.finditer(body):
        match = m.group(0)
        first_w = match.split()[0]
        if " " in match:
            if first_w not in COMMON_WORDS:
                entities.append(match)
        elif first_w not in COMMON_WORDS and first_w not in sentence_starters:
            entities.append(match)

    # Dedup preserving order
    seen = set()
    unique = []
    for e in entities:
        if e not in seen:
            seen.add(e)
            unique.append(e)
    return unique


def extract_quoted_claims(body: str) -> list[str]:
    """Sentences containing a direct quotation or an attributed source pattern
    (e.g., "per Framework X", "according to Y", "Smith et al."). These are
    highest-risk to paraphrase-drift during a restructure."""
    sentences = re.split(r"(?<=[.!?])\s+", body)
    claims = []
    attribution_re = re.compile(
        r'"[^"]{10,}"'
        r"|\b(according to|per|as stated by|noted by|"
        r"reports?|reported|wrote|writes|says?|claimed?)\b",
        re.IGNORECASE,
    )
    for s in sentences:
        s = s.strip()
        if 10 < len(s.split()) < 60 and attribution_re.search(s):
            claims.append(s)
    return claims


def do_extract_facts(source: str, output_dir: Path) -> int:
    _, body, identifier = load_source(source)
    slug = source_to_slug(source)
    facts = Facts(
        numbers=extract_numbers(body),
        entities=extract_entities(body),
        quoted_claims=extract_quoted_claims(body),
        source=identifier,
        slug=slug,
        word_count=len(body.split()),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "facts.json"
    out_path.write_text(json.dumps(asdict(facts), indent=2), encoding="utf-8")
    print(
        f"Extracted {len(facts.numbers)} numbers, "
        f"{len(facts.entities)} entities, "
        f"{len(facts.quoted_claims)} quoted claims -> {out_path}",
        file=sys.stderr,
    )
    return 0


# ---------------------------------------------------------------------------
# YMYL detection
# ---------------------------------------------------------------------------


def _term_density(body_lower: str, total_words: int, terms: set) -> tuple[float, int]:
    """Return (density_percent, hit_count) for a term set. Counts multi-word
    terms via substring search so 'clinical trial' matches even though it's
    two tokens."""
    if total_words == 0:
        return 0.0, 0
    hits = 0
    word_tokens = re.findall(r"\b[a-z]+(?:\s+[a-z]+)?\b", body_lower)
    single_word_set = {t for t in terms if " " not in t}
    multi_word_terms = [t for t in terms if " " in t]

    for tok in word_tokens:
        first = tok.split()[0]
        if first in single_word_set:
            hits += 1

    for mwt in multi_word_terms:
        hits += len(re.findall(r"\b" + re.escape(mwt) + r"\b", body_lower))

    return (100.0 * hits / total_words), hits


def detect_ymyl(body: str) -> YMYLReport:
    total = len(body.split())
    if total == 0:
        return YMYLReport()
    lower = body.lower()
    med_pct, _ = _term_density(lower, total, YMYL_MEDICAL)
    legal_pct, _ = _term_density(lower, total, YMYL_LEGAL)
    fin_pct, _ = _term_density(lower, total, YMYL_FINANCIAL)

    by_cat = {"medical": med_pct, "legal": legal_pct, "financial": fin_pct}
    top_cat, top_pct = max(by_cat.items(), key=lambda kv: kv[1])

    return YMYLReport(
        is_ymyl=(top_pct >= 1.0),
        medical_density_pct=round(med_pct, 2),
        legal_density_pct=round(legal_pct, 2),
        financial_density_pct=round(fin_pct, 2),
        top_category=top_cat if top_pct >= 1.0 else "",
        word_count=total,
    )


def do_detect_ymyl(source: str, output_dir: Optional[Path]) -> int:
    _, body, _ = load_source(source)
    report = detect_ymyl(body)
    payload = json.dumps(asdict(report), indent=2)
    print(payload)
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "ymyl_report.json").write_text(payload, encoding="utf-8")
    return 10 if report.is_ymyl else 0


# ---------------------------------------------------------------------------
# Voice markers
# ---------------------------------------------------------------------------


def count_voice_markers(body: str) -> VoiceMarkers:
    em_dash = len(EM_DASH_RE.findall(body))
    hedging = len(HEDGING_RE.findall(body))
    filler = len(FILLER_RE.findall(body))
    parens = body.count("(")

    sentences = [s.strip() for s in re.split(r"[.!?]+", body) if s.strip()]
    sentence_count = len(sentences)
    the_this = sum(
        1 for s in sentences
        if s.split() and s.split()[0].lower() in ("the", "this")
    )
    pct_the_this = 100.0 * the_this / sentence_count if sentence_count else 0.0
    avg_len = (
        sum(len(s.split()) for s in sentences) / sentence_count
        if sentence_count else 0.0
    )

    return VoiceMarkers(
        em_dash_count=em_dash,
        hedging_count=hedging,
        filler_count=filler,
        parenthetical_count=parens,
        sentence_count=sentence_count,
        the_or_this_starter_pct=round(pct_the_this, 1),
        avg_sentence_length=round(avg_len, 1),
    )


# ---------------------------------------------------------------------------
# Preservation check
# ---------------------------------------------------------------------------


def normalize_num(tok: str) -> str:
    """Normalize a number token for comparison — strip commas, spaces, $ signs.
    Keeps the magnitude suffix (K/M/B) and percent/x markers."""
    t = tok.strip().replace(",", "").replace(" ", "")
    return t


def check_number_preservation(
    source_numbers: list[str], rewrite_numbers: list[str]
) -> tuple[list[str], list[str]]:
    """Return (dropped, added). Comparison is on normalized forms, per-occurrence.
    Dropped = source numbers not found in rewrite.
    Added = rewrite numbers not in source (potential hallucination)."""
    src_norm = [normalize_num(n) for n in source_numbers]
    rw_norm = [normalize_num(n) for n in rewrite_numbers]

    rw_pool = list(rw_norm)
    dropped = []
    for n in src_norm:
        if n in rw_pool:
            rw_pool.remove(n)
        else:
            dropped.append(n)

    src_pool = list(src_norm)
    added = []
    for n in rw_norm:
        if n in src_pool:
            src_pool.remove(n)
        else:
            added.append(n)

    return dropped, added


def check_entity_preservation(
    source_entities: list[str], rewrite_body: str
) -> tuple[list[str], float]:
    """Return (dropped_entities, preservation_rate_pct).
    Case-insensitive substring match — if 'Monte Carlo Data' appears in rewrite
    even without the 'Data' trailing word, count as preserved."""
    if not source_entities:
        return [], 100.0
    rw_lower = rewrite_body.lower()
    dropped = []
    preserved = 0
    for e in source_entities:
        # Check full phrase, then fall back to head (first 2 words)
        if e.lower() in rw_lower:
            preserved += 1
            continue
        head = " ".join(e.split()[:2]).lower()
        if head and head in rw_lower:
            preserved += 1
            continue
        dropped.append(e)

    rate = 100.0 * preserved / len(source_entities)
    return dropped, round(rate, 1)


# ---------------------------------------------------------------------------
# Section mapping
# ---------------------------------------------------------------------------


def extract_h2s(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    return [h.get_text(strip=True) for h in soup.find_all("h2")]


def map_sections(source_h2s: list[str], rewrite_h2s: list[str]) -> list[dict]:
    """Sequential alignment with word-overlap heuristic. Returns a list of
    {source: str, rewrite: str, overlap: float} dicts. Overlap is Jaccard on
    lowercase content words. Missing side is the empty string."""
    stop = {
        "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or",
        "is", "are", "was", "were", "be", "been", "being", "with", "by",
    }

    def wset(s: str) -> set:
        return {w.lower() for w in re.findall(r"\w+", s) if w.lower() not in stop}

    result = []
    n = max(len(source_h2s), len(rewrite_h2s))
    for i in range(n):
        src = source_h2s[i] if i < len(source_h2s) else ""
        rw = rewrite_h2s[i] if i < len(rewrite_h2s) else ""
        if src and rw:
            ws, wr = wset(src), wset(rw)
            denom = len(ws | wr) or 1
            overlap = round(len(ws & wr) / denom, 2)
        else:
            overlap = 0.0
        result.append({"source": src, "rewrite": rw, "overlap": overlap})
    return result


# ---------------------------------------------------------------------------
# Diff report (main orchestration)
# ---------------------------------------------------------------------------


def _audit_scorecard_table(
    pre: AuditResult, post: AuditResult
) -> list[str]:
    lines = []
    lines.append("| Signal | Weight | Pre | Post | Delta |")
    lines.append("|---|---|---|---|---|")
    pre_map = {s.name: s.score for s in pre.content_signals}
    post_map = {s.name: s.score for s in post.content_signals}
    weight_map = {s.name: s.weight_label for s in pre.content_signals}
    for name in pre_map:
        pre_s = pre_map.get(name, 0)
        post_s = post_map.get(name, 0)
        delta = post_s - pre_s
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "–")
        lines.append(
            f"| {name} | {weight_map.get(name, '-')} | {pre_s} | {post_s} | {arrow} {abs(delta)} |"
        )
    return lines


def _verdict(pre_score: float, post_score: float, regressions: list[str]) -> str:
    net = post_score - pre_score
    if net >= 15 and not regressions:
        return f"**PASS** — net +{net:.1f} pts, no signal regressions."
    if net >= 15 and regressions:
        return f"**PASS WITH CAVEATS** — net +{net:.1f} pts but {len(regressions)} signal regression(s): {', '.join(regressions)}."
    if net >= 5:
        return f"**BELOW TARGET** — net +{net:.1f} pts (target ≥15). Revise weakest signals."
    return f"**FAIL** — net {net:+.1f} pts. Rewrite did not move the rubric; restart plan."


def do_diff_report(
    source: str,
    rewrite_path: Path,
    output_dir: Path,
) -> int:
    if not rewrite_path.exists():
        die(f"Rewrite file not found: {rewrite_path}")

    source_html, source_body, source_id = load_source(source)
    rewrite_raw = rewrite_path.read_text(encoding="utf-8")
    rewrite_html = md_lib.markdown(rewrite_raw, extensions=["extra", "tables"])
    rewrite_body = BeautifulSoup(rewrite_html, "html.parser").get_text(
        separator="\n", strip=True
    )

    slug = source_to_slug(source)
    is_url = source.startswith("http")
    domain = None
    if is_url:
        parsed = urlparse(source)
        domain = parsed.netloc
        if domain.startswith("www."):
            domain = domain[4:]

    # Pre-audit: remote checks only matter for URL source (robots.txt etc.
    # don't exist for local files). Post-audit: always local — skip remote.
    pre_audit = audit_html(
        source_html, source_id, domain, None, run_remote_checks=is_url
    )
    post_audit = audit_html(
        rewrite_html, str(rewrite_path), domain, None, run_remote_checks=False
    )

    # Preservation
    src_numbers = extract_numbers(source_body)
    src_entities = extract_entities(source_body)
    src_claims = extract_quoted_claims(source_body)
    rw_numbers = extract_numbers(rewrite_body)

    dropped_nums, added_nums = check_number_preservation(src_numbers, rw_numbers)
    dropped_ents, ent_rate = check_entity_preservation(src_entities, rewrite_body)

    # Voice markers
    pre_voice = count_voice_markers(source_body)
    post_voice = count_voice_markers(rewrite_body)

    # Length
    src_wc = len(source_body.split())
    rw_wc = len(rewrite_body.split())
    length_ratio = rw_wc / src_wc if src_wc else 0.0

    # Section mapping
    src_h2s = extract_h2s(source_html)
    rw_h2s = extract_h2s(rewrite_html)
    section_map = map_sections(src_h2s, rw_h2s)

    # YMYL
    ymyl = detect_ymyl(source_body)

    # Regressions on any signal (post < pre)
    regressions = []
    for name, pre_sig in {s.name: s for s in pre_audit.content_signals}.items():
        post_sig = next((x for x in post_audit.content_signals if x.name == name), None)
        if post_sig and post_sig.score < pre_sig.score:
            regressions.append(f"{name} ({pre_sig.score}→{post_sig.score})")

    # Write audit_diff.md
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{slug}_audit_diff.md"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = []
    lines.append(f"# Restructure Validation — {slug}")
    lines.append("")
    lines.append(f"**Date:** {today}")
    lines.append(f"**Source:** {source_id}")
    lines.append(f"**Rewrite:** {rewrite_path}")
    lines.append("")

    # Verdict first — this is what the operator needs to see at the top
    lines.append("## Verdict")
    lines.append("")
    lines.append(_verdict(pre_audit.overall_score, post_audit.overall_score, regressions))
    lines.append("")

    # Overall scores
    lines.append("## Overall Score")
    lines.append("")
    lines.append(f"- **Pre:** {pre_audit.overall_score}/100")
    lines.append(f"- **Post:** {post_audit.overall_score}/100")
    lines.append(f"- **Net:** {post_audit.overall_score - pre_audit.overall_score:+.1f} pts")
    lines.append("")

    # Per-signal table
    lines.append("## Per-Signal Delta")
    lines.append("")
    lines.extend(_audit_scorecard_table(pre_audit, post_audit))
    lines.append("")
    if regressions:
        lines.append(f"> **Regressions:** {', '.join(regressions)}")
        lines.append("")

    # Length
    lines.append("## Length Budget")
    lines.append("")
    lines.append(f"- Source: {src_wc} words")
    lines.append(f"- Rewrite: {rw_wc} words")
    lines.append(f"- Ratio: {length_ratio:.2f}x")
    if length_ratio > LENGTH_FAIL_THRESHOLD:
        lines.append(f"- **FAIL** — exceeds {LENGTH_FAIL_THRESHOLD:.0%} ceiling. Tighten before publishing.")
    elif length_ratio > LENGTH_WARN_THRESHOLD:
        lines.append(f"- **WARN** — exceeds {LENGTH_WARN_THRESHOLD:.0%} soft ceiling.")
    elif length_ratio < LENGTH_MIN_THRESHOLD:
        lines.append(f"- **FAIL** — below {LENGTH_MIN_THRESHOLD:.0%} floor. Too aggressive a cut.")
    else:
        lines.append("- Within budget.")
    lines.append("")

    # Preservation — numbers
    lines.append("## Preservation Check — Numbers")
    lines.append("")
    lines.append(f"- Source numbers: {len(src_numbers)}")
    lines.append(f"- Rewrite numbers: {len(rw_numbers)}")
    lines.append(f"- Dropped: {len(dropped_nums)}")
    lines.append(f"- **Added (potential hallucination):** {len(added_nums)}")
    if dropped_nums:
        lines.append("")
        lines.append("**Dropped numbers (present in source, missing from rewrite):**")
        for n in dropped_nums[:30]:
            lines.append(f"- `{n}`")
        if len(dropped_nums) > 30:
            lines.append(f"- ...and {len(dropped_nums) - 30} more")
    if added_nums:
        lines.append("")
        lines.append("**Added numbers (present in rewrite, NOT in source — verify these are not hallucinated):**")
        for n in added_nums[:30]:
            lines.append(f"- `{n}`")
        if len(added_nums) > 30:
            lines.append(f"- ...and {len(added_nums) - 30} more")
    lines.append("")

    # Preservation — entities
    lines.append("## Preservation Check — Named Entities")
    lines.append("")
    lines.append(f"- Source entities: {len(src_entities)}")
    lines.append(f"- Preservation rate: {ent_rate:.1f}%")
    lines.append(f"- Dropped: {len(dropped_ents)}")
    if dropped_ents:
        lines.append("")
        lines.append("**Dropped entities:**")
        for e in dropped_ents[:25]:
            lines.append(f"- {e}")
        if len(dropped_ents) > 25:
            lines.append(f"- ...and {len(dropped_ents) - 25} more")
    lines.append("")

    # Quoted claims
    lines.append("## Quoted Claims in Source (verify paraphrases in rewrite)")
    lines.append("")
    if src_claims:
        for c in src_claims[:15]:
            snippet = c if len(c) <= 200 else c[:197] + "..."
            lines.append(f"- {snippet}")
        if len(src_claims) > 15:
            lines.append(f"- ...and {len(src_claims) - 15} more")
    else:
        lines.append("_No attributed claims detected in source._")
    lines.append("")

    # YMYL
    lines.append("## YMYL Status")
    lines.append("")
    if ymyl.is_ymyl:
        lines.append(f"- **YMYL content detected** — top category: {ymyl.top_category}")
    else:
        lines.append("- Not flagged as YMYL.")
    lines.append(f"- Medical density: {ymyl.medical_density_pct}%")
    lines.append(f"- Legal density: {ymyl.legal_density_pct}%")
    lines.append(f"- Financial density: {ymyl.financial_density_pct}%")
    lines.append("")

    # Voice markers
    lines.append("## Voice Markers Diff")
    lines.append("")
    lines.append("| Marker | Pre | Post | Delta |")
    lines.append("|---|---|---|---|")
    lines.append(f"| em-dashes | {pre_voice.em_dash_count} | {post_voice.em_dash_count} | {post_voice.em_dash_count - pre_voice.em_dash_count:+d} |")
    lines.append(f"| hedging words | {pre_voice.hedging_count} | {post_voice.hedging_count} | {post_voice.hedging_count - pre_voice.hedging_count:+d} |")
    lines.append(f"| filler phrases | {pre_voice.filler_count} | {post_voice.filler_count} | {post_voice.filler_count - pre_voice.filler_count:+d} |")
    lines.append(f"| parentheticals | {pre_voice.parenthetical_count} | {post_voice.parenthetical_count} | {post_voice.parenthetical_count - pre_voice.parenthetical_count:+d} |")
    lines.append(f"| sentences | {pre_voice.sentence_count} | {post_voice.sentence_count} | {post_voice.sentence_count - pre_voice.sentence_count:+d} |")
    lines.append(f"| The/This starter % | {pre_voice.the_or_this_starter_pct} | {post_voice.the_or_this_starter_pct} | {post_voice.the_or_this_starter_pct - pre_voice.the_or_this_starter_pct:+.1f} |")
    lines.append(f"| avg sentence length | {pre_voice.avg_sentence_length} | {post_voice.avg_sentence_length} | {post_voice.avg_sentence_length - pre_voice.avg_sentence_length:+.1f} |")
    lines.append("")
    if post_voice.em_dash_count > 0:
        lines.append("> Em-dashes present in rewrite. Hanna's voice gate requires zero em-dashes.")
        lines.append("")

    # Section mapping
    lines.append("## Section Mapping (source H2 → rewrite H2)")
    lines.append("")
    lines.append("| # | Source H2 | Rewrite H2 | Overlap |")
    lines.append("|---|---|---|---|")
    for i, m in enumerate(section_map, 1):
        src_txt = m["source"] or "_(new in rewrite)_"
        rw_txt = m["rewrite"] or "_(removed)_"
        lines.append(f"| {i} | {src_txt} | {rw_txt} | {m['overlap']} |")
    lines.append("")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Validation report -> {out}", file=sys.stderr)
    print(
        f"Pre {pre_audit.overall_score} / Post {post_audit.overall_score} / "
        f"Net {post_audit.overall_score - pre_audit.overall_score:+.1f}",
        file=sys.stderr,
    )

    # Exit code: 0 = pass, 1 = partial, 2 = fail
    if added_nums or length_ratio > LENGTH_FAIL_THRESHOLD or length_ratio < LENGTH_MIN_THRESHOLD:
        return 2
    if regressions or (post_audit.overall_score - pre_audit.overall_score) < 15:
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command")

    p_facts = sub.add_parser(
        "extract-facts",
        help="Extract numbers, entities, quoted claims from source → facts.json",
    )
    p_facts.add_argument("--source", type=str, required=True,
                         help="URL or local file (.md / .html)")
    p_facts.add_argument("--output", type=Path, required=True, help="Output directory")

    p_ymyl = sub.add_parser(
        "detect-ymyl",
        help="Classify source as YMYL. Exit 0 = no, exit 10 = yes.",
    )
    p_ymyl.add_argument("--source", type=str, required=True)
    p_ymyl.add_argument("--output", type=Path, default=None,
                        help="Optional — write ymyl_report.json here")

    p_diff = sub.add_parser(
        "diff-report",
        help="Pre/post audit + preservation + voice + length + sections",
    )
    p_diff.add_argument("--source", type=str, required=True,
                        help="Original URL or file")
    p_diff.add_argument("--rewrite", type=Path, required=True,
                        help="Rewritten markdown file")
    p_diff.add_argument("--output", type=Path, required=True, help="Output directory")

    opts = parser.parse_args()

    if opts.command == "extract-facts":
        return do_extract_facts(opts.source, opts.output)
    if opts.command == "detect-ymyl":
        return do_detect_ymyl(opts.source, opts.output)
    if opts.command == "diff-report":
        return do_diff_report(opts.source, opts.rewrite, opts.output)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
