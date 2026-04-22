#!/usr/bin/env python3
"""
Run a GEO prompt set against ChatGPT, Claude, Gemini, and Perplexity. Detect
citations of a target brand + competitors. Output runs.csv, summary.md, and
append to trends.csv.

This is the foundational measurement tool for `/cmo/geo/share-of-answers`.
Reports two performance goals separately:
  * Goal A — Mentions:        share of answers where brand is cited (any intent)
  * Goal B — Shopping-intent: share of answers where brand is cited on
                              prompts with intent_type='shopping'

Usage:
    python3 tools/geo_share_of_answers.py \\
        --prompts research/geo-aeo/prompt-sets/data-observability_template.csv \\
        --brands  brands.csv \\
        --output  clients/<client>/geo/share-of-answers/2026-04-16/ \\
        --runs-per-prompt 3 \\
        --max-cost 10

    # Subset for quick testing:
    python3 tools/geo_share_of_answers.py --prompts ... --brands ... \\
        --output .tmp/geo/test/ --limit 5 --runs-per-prompt 1 --no-confirm

    # Use LLM-as-judge for primary/secondary classification:
    python3 tools/geo_share_of_answers.py ... --judge

    # Restrict to specific surfaces:
    python3 tools/geo_share_of_answers.py ... --surfaces anthropic,perplexity

CSV schemas:
    prompts:  prompt_id, prompt_text, intent_type, topic, priority [+ optional]
    brands:   role, name, aliases, domain
              role        in {primary, competitor}
              aliases     pipe-separated alternates ("MonteCarlo|Monte Carlo Data")
              domain      bare domain ("montecarlodata.com")

Requires: anthropic, openai, google-genai, requests, python-dotenv
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

warnings.filterwarnings("ignore")

# .env loader is optional but expected; fail loud if missing so user knows.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    print("ERROR: pip install --user python-dotenv", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Constants — locked vocabulary + default model IDs
# ---------------------------------------------------------------------------

INTENT_CLASSES = ["shopping", "comparative", "informational", "decision", "recommendation"]
SUPPORTED_SURFACES = ["anthropic", "openai", "google", "perplexity"]

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o",
    "google": "gemini-2.5-flash",
    "perplexity": "sonar-pro",
}

# Pricing per 1M tokens (input, output) — used only for cost preflight estimate.
# Web-search add-ons are approximated as ~$0.005/call where applicable.
PRICING = {
    "anthropic":  {"in": 3.0,  "out": 15.0, "search_per_call": 0.010},
    "openai":     {"in": 2.5,  "out": 10.0, "search_per_call": 0.010},
    "google":     {"in": 0.30, "out": 2.50, "search_per_call": 0.000},
    "perplexity": {"in": 3.0,  "out": 15.0, "search_per_call": 0.005},
}

# Heuristic per-call token estimate for cost preflight only (not reporting).
EST_INPUT_TOKENS = 200
EST_OUTPUT_TOKENS = 800

# Citation detection
PRIMARY_FIRST_PARA_CHAR_LIMIT = 600  # chars from start of response counted as "first paragraph"
PRIMARY_LIST_ITEM_LIMIT = 3          # first N list items count as primary

JUDGE_MODEL = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class BrandSpec:
    role: str           # primary | competitor
    name: str
    aliases: list = field(default_factory=list)
    domain: str = ""

    def all_name_variants(self) -> list:
        """All textual identifiers (name + aliases), normalized."""
        out = [normalize_text(self.name)]
        for a in self.aliases:
            n = normalize_text(a)
            if n and n not in out:
                out.append(n)
        return out


@dataclass
class Prompt:
    prompt_id: str
    prompt_text: str
    intent_type: str
    topic: str
    priority: str


@dataclass
class RunResult:
    prompt_id: str
    intent_type: str
    surface: str
    run_number: int
    response_text: str
    citation_urls: list
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Loaders + validators
# ---------------------------------------------------------------------------


def load_prompts(path: Path, limit: Optional[int] = None) -> list:
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    if not rows:
        die(f"prompts file is empty: {path}")
    required = {"prompt_id", "prompt_text", "intent_type", "topic", "priority"}
    missing = required - set(rows[0].keys())
    if missing:
        die(f"prompts CSV missing columns: {sorted(missing)}")
    bad = {r["intent_type"] for r in rows} - set(INTENT_CLASSES)
    if bad:
        die(f"unknown intent_type values in prompts: {sorted(bad)} — locked vocab: {INTENT_CLASSES}")
    prompts = [
        Prompt(
            prompt_id=r["prompt_id"],
            prompt_text=r["prompt_text"],
            intent_type=r["intent_type"],
            topic=r["topic"],
            priority=r["priority"],
        )
        for r in rows
    ]
    if limit:
        prompts = prompts[:limit]
    return prompts


def load_brands(path: Path) -> tuple:
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    if not rows:
        die(f"brands file is empty: {path}")
    required = {"role", "name", "aliases", "domain"}
    missing = required - set(rows[0].keys())
    if missing:
        die(f"brands CSV missing columns: {sorted(missing)}")
    primary = None
    competitors = []
    for r in rows:
        spec = BrandSpec(
            role=r["role"].strip().lower(),
            name=r["name"].strip(),
            aliases=[a.strip() for a in (r["aliases"] or "").split("|") if a.strip()],
            domain=(r["domain"] or "").strip().lower(),
        )
        if spec.role == "primary":
            if primary:
                die(f"brands CSV has multiple primary rows ({primary.name}, {spec.name})")
            primary = spec
        elif spec.role == "competitor":
            competitors.append(spec)
        else:
            die(f"brands CSV row has invalid role: {spec.role!r} (expected 'primary' or 'competitor')")
    if not primary:
        die("brands CSV must have exactly one row with role=primary")
    return primary, competitors


def write_brands_template(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "role,name,aliases,domain\n"
        'primary,Your Brand,"YourBrand|Your Brand Inc",yourbrand.com\n'
        "competitor,Competitor One,,competitorone.com\n"
        "competitor,Competitor Two,,competitortwo.com\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Normalization + citation detection
# ---------------------------------------------------------------------------


def normalize_text(s: str) -> str:
    """Lowercase, drop punctuation/whitespace, drop common TLD suffixes."""
    s = s.lower().strip()
    s = re.sub(r"\.(com|io|ai|co|net|org|app|dev|so|inc)$", "", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def brand_appears_in(text: str, urls: list, brand: BrandSpec) -> bool:
    """True if brand is cited anywhere in response text or citation URLs."""
    norm_text = normalize_text(text)
    for v in brand.all_name_variants():
        if v and v in norm_text:
            return True
    if brand.domain:
        for u in urls:
            d = domain_of(u)
            if d and (d == brand.domain or d.endswith("." + brand.domain)):
                return True
    return False


def brand_position_classify(text: str, urls: list, brand: BrandSpec) -> tuple:
    """
    Positional heuristic. Returns (status, position_index_or_None).
        status in {none, secondary, primary}
        primary  = appears in first ~600 chars OR in first 3 list items OR
                   is the only/first cited domain
        secondary = appears anywhere later in text or URLs
        none     = doesn't appear
    """
    if not brand_appears_in(text, urls, brand):
        return "none", None

    # First-paragraph check
    head = text[:PRIMARY_FIRST_PARA_CHAR_LIMIT].lower()
    norm_head = normalize_text(head)
    for v in brand.all_name_variants():
        if v and v in norm_head:
            return "primary", _first_index(text, brand)

    # First-N list items (lines starting with bullet, number, or dash)
    items = _extract_list_items(text, limit=PRIMARY_LIST_ITEM_LIMIT)
    for idx, item in enumerate(items, start=1):
        if any(v in normalize_text(item) for v in brand.all_name_variants() if v):
            return "primary", idx

    # First cited domain matches brand domain
    if brand.domain and urls:
        first_domain = domain_of(urls[0])
        if first_domain == brand.domain or first_domain.endswith("." + brand.domain):
            return "primary", 1

    return "secondary", _first_index(text, brand)


def _first_index(text: str, brand: BrandSpec) -> Optional[int]:
    norm_text = normalize_text(text)
    positions = []
    for v in brand.all_name_variants():
        if v and v in norm_text:
            positions.append(norm_text.index(v))
    return min(positions) + 1 if positions else None


def _extract_list_items(text: str, limit: int) -> list:
    items = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^(\*|-|\d+\.|\d+\))\s+", stripped):
            items.append(stripped)
            if len(items) >= limit:
                break
    return items


def detect_competitors(text: str, urls: list, competitors: list) -> list:
    return [c.name for c in competitors if brand_appears_in(text, urls, c)]


# ---------------------------------------------------------------------------
# Provider clients — each returns RunResult
# ---------------------------------------------------------------------------


def call_anthropic(prompt: Prompt, run_number: int, model: str) -> RunResult:
    from anthropic import Anthropic

    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": prompt.prompt_text}],
        )
    except Exception as e:
        return RunResult(prompt.prompt_id, prompt.intent_type, "anthropic", run_number, "", [], error=f"{type(e).__name__}: {e}")

    text_parts = []
    urls = []
    for block in resp.content:
        btype = getattr(block, "type", None)
        if btype == "text":
            text_parts.append(block.text)
        elif btype == "web_search_tool_result":
            for item in getattr(block, "content", []) or []:
                u = getattr(item, "url", None)
                if u:
                    urls.append(u)
    return RunResult(prompt.prompt_id, prompt.intent_type, "anthropic", run_number, "\n\n".join(text_parts), dedupe(urls))


def call_openai(prompt: Prompt, run_number: int, model: str) -> RunResult:
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        # Force web_search use — without tool_choice, gpt-4o often answers from
        # training data (0 citations), which misrepresents what ChatGPT Plus/Pro
        # users actually see in the wild.
        resp = client.responses.create(
            model=model,
            tools=[{"type": "web_search"}],
            tool_choice={"type": "web_search"},
            input=prompt.prompt_text,
        )
    except Exception as e:
        return RunResult(prompt.prompt_id, prompt.intent_type, "openai", run_number, "", [], error=f"{type(e).__name__}: {e}")

    text_parts = []
    urls = []
    for item in resp.output:
        if getattr(item, "type", None) == "message":
            for c in getattr(item, "content", []) or []:
                t = getattr(c, "text", None)
                if t:
                    text_parts.append(t)
                for ann in getattr(c, "annotations", []) or []:
                    u = getattr(ann, "url", None)
                    if u:
                        urls.append(strip_utm(u))
    return RunResult(prompt.prompt_id, prompt.intent_type, "openai", run_number, "\n\n".join(text_parts), dedupe(urls))


def call_google(prompt: Prompt, run_number: int, model: str) -> RunResult:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    try:
        resp = client.models.generate_content(
            model=model,
            contents=prompt.prompt_text,
            config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
        )
    except Exception as e:
        return RunResult(prompt.prompt_id, prompt.intent_type, "google", run_number, "", [], error=f"{type(e).__name__}: {e}")

    text = resp.text or ""
    # Gemini grounding chunks: web.uri is a Vertex redirect; web.title is the source domain.
    # We synthesize https://<title>/ as the citation URL so downstream matching uses real domain.
    urls = []
    for cand in resp.candidates or []:
        gm = getattr(cand, "grounding_metadata", None)
        if gm:
            for chunk in getattr(gm, "grounding_chunks", []) or []:
                web = getattr(chunk, "web", None)
                if web:
                    title = getattr(web, "title", None)  # actually the source domain
                    if title and "." in title:
                        urls.append(f"https://{title}/")
    return RunResult(prompt.prompt_id, prompt.intent_type, "google", run_number, text, dedupe(urls))


def call_perplexity(prompt: Prompt, run_number: int, model: str) -> RunResult:
    import requests

    try:
        r = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('PERPLEXITY_API_KEY')}",
                "Content-Type": "application/json",
            },
            json={"model": model, "messages": [{"role": "user", "content": prompt.prompt_text}]},
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return RunResult(prompt.prompt_id, prompt.intent_type, "perplexity", run_number, "", [], error=f"{type(e).__name__}: {e}")

    choice = (data.get("choices") or [{}])[0]
    text = choice.get("message", {}).get("content", "")
    raw = data.get("citations") or data.get("search_results") or []
    urls = [u.get("url") if isinstance(u, dict) else u for u in raw]
    urls = [u for u in urls if u]
    return RunResult(prompt.prompt_id, prompt.intent_type, "perplexity", run_number, text, dedupe(urls))


def strip_utm(url: str) -> str:
    """Strip query string for cleaner citation URLs."""
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}{p.path}"
    except Exception:
        return url


def dedupe(urls: list) -> list:
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


PROVIDER_CALLERS = {
    "anthropic": call_anthropic,
    "openai": call_openai,
    "google": call_google,
    "perplexity": call_perplexity,
}


# ---------------------------------------------------------------------------
# LLM-as-judge (option B)
# ---------------------------------------------------------------------------


def judge_classify(text: str, urls: list, brand: BrandSpec) -> tuple:
    """
    Use Claude Haiku to classify primary vs secondary vs none. Returns
    (status, position_or_None). Falls back to positional heuristic on error.
    """
    from anthropic import Anthropic

    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    sys_prompt = (
        "You classify whether a target brand is cited as the PRIMARY recommendation, "
        "as a SECONDARY mention (one of several), or NOT CITED in an AI search response. "
        'Respond ONLY as JSON: {"status": "primary|secondary|none", "reason": "<short>"}'
    )
    user_msg = (
        f"Target brand: {brand.name}\n"
        f"Aliases: {', '.join(brand.aliases) if brand.aliases else '(none)'}\n"
        f"Domain: {brand.domain or '(none)'}\n\n"
        f"Citation URLs:\n" + ("\n".join(urls[:20]) if urls else "(none)") + "\n\n"
        f"Response text:\n{text[:4000]}"
    )
    try:
        resp = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=200,
            system=sys_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        body = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        m = re.search(r"\{.*\}", body, re.DOTALL)
        if not m:
            return brand_position_classify(text, urls, brand)
        parsed = json.loads(m.group(0))
        status = parsed.get("status", "none").lower()
        if status not in {"primary", "secondary", "none"}:
            return brand_position_classify(text, urls, brand)
        return status, _first_index(text, brand) if status != "none" else None
    except Exception:
        return brand_position_classify(text, urls, brand)


# ---------------------------------------------------------------------------
# Cost preflight
# ---------------------------------------------------------------------------


def estimate_cost(num_prompts: int, num_runs: int, surfaces: list) -> dict:
    breakdown = {}
    total = 0.0
    for s in surfaces:
        p = PRICING[s]
        in_cost = num_prompts * num_runs * EST_INPUT_TOKENS / 1_000_000 * p["in"]
        out_cost = num_prompts * num_runs * EST_OUTPUT_TOKENS / 1_000_000 * p["out"]
        search_cost = num_prompts * num_runs * p["search_per_call"]
        total_s = in_cost + out_cost + search_cost
        breakdown[s] = round(total_s, 3)
        total += total_s
    return {"total": round(total, 2), "by_surface": breakdown, "calls": num_prompts * num_runs * len(surfaces)}


# ---------------------------------------------------------------------------
# Run orchestration
# ---------------------------------------------------------------------------


def run_provider_jobs(
    surface: str,
    prompts: list,
    runs_per_prompt: int,
    model: str,
    sleep_between: float,
    start_run_number: int = 1,
) -> list:
    """Run all prompts × N runs sequentially for one surface.

    `start_run_number` lets adaptive-sampling callers extend an existing batch
    without re-using run numbers (pass 1 uses 1..3; pass 2 passes start=4).
    """
    caller = PROVIDER_CALLERS[surface]
    results = []
    for prompt in prompts:
        for offset in range(runs_per_prompt):
            run_number = start_run_number + offset
            r = caller(prompt, run_number, model)
            results.append(r)
            if r.error:
                print(f"  [{surface}] {prompt.prompt_id} run {run_number} ERR: {r.error}", file=sys.stderr)
            else:
                print(f"  [{surface}] {prompt.prompt_id} run {run_number} OK ({len(r.citation_urls)} urls)", flush=True)
            if sleep_between:
                time.sleep(sleep_between)
    return results


def run_suite(
    prompts: list,
    surfaces: Optional[list] = None,
    runs_per_prompt: int = 3,
    models: Optional[dict] = None,
    sleep_between: float = 0.5,
    start_run_number: int = 1,
) -> list:
    """Run `prompts` across `surfaces` in parallel, return raw RunResult list.

    Importable entrypoint for other GEO tools (e.g. citation-network-mapper)
    that need to execute the SoA run engine without its CSV/MD output writers.

    Args:
        prompts: list of Prompt dataclasses
        surfaces: subset of SUPPORTED_SURFACES; defaults to all 4
        runs_per_prompt: how many runs each prompt gets on each surface
        models: override provider model IDs; defaults to DEFAULT_MODELS
        sleep_between: seconds between calls within a surface
        start_run_number: starting run_number to assign (for adaptive extra passes)

    Returns:
        flat list of RunResult (one per prompt × surface × run)
    """
    if surfaces is None:
        surfaces = list(SUPPORTED_SURFACES)
    bad = [s for s in surfaces if s not in SUPPORTED_SURFACES]
    if bad:
        raise ValueError(f"unknown surfaces: {bad} — supported: {SUPPORTED_SURFACES}")
    if models is None:
        models = dict(DEFAULT_MODELS)

    all_results = []
    with ThreadPoolExecutor(max_workers=len(surfaces)) as ex:
        futures = {
            ex.submit(
                run_provider_jobs, s, prompts, runs_per_prompt,
                models.get(s, DEFAULT_MODELS[s]), sleep_between, start_run_number,
            ): s
            for s in surfaces
        }
        for fut in as_completed(futures):
            s = futures[fut]
            try:
                all_results.extend(fut.result())
            except Exception as e:
                print(f"FATAL [{s}]: {e}", file=sys.stderr)
    return all_results


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------


RUNS_COLS = [
    "run_id", "timestamp", "prompt_id", "intent_type", "ai_surface", "run_number",
    "response_text", "citation_urls", "brand_cited", "brand_position", "competitor_citations",
]


def write_runs_csv(
    out_dir: Path,
    results: list,
    prompts_by_id: dict,
    primary: BrandSpec,
    competitors: list,
    use_judge: bool,
) -> Path:
    out = out_dir / "runs.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RUNS_COLS)
        w.writeheader()
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for i, r in enumerate(results, start=1):
            if r.error:
                w.writerow({
                    "run_id": f"R{i:05d}", "timestamp": ts, "prompt_id": r.prompt_id,
                    "intent_type": r.intent_type, "ai_surface": r.surface, "run_number": r.run_number,
                    "response_text": f"[ERROR] {r.error}", "citation_urls": "", "brand_cited": "error",
                    "brand_position": "", "competitor_citations": "",
                })
                continue
            if use_judge:
                status, position = judge_classify(r.response_text, r.citation_urls, primary)
            else:
                status, position = brand_position_classify(r.response_text, r.citation_urls, primary)
            comp_cited = detect_competitors(r.response_text, r.citation_urls, competitors)
            w.writerow({
                "run_id": f"R{i:05d}",
                "timestamp": ts,
                "prompt_id": r.prompt_id,
                "intent_type": r.intent_type,
                "ai_surface": r.surface,
                "run_number": r.run_number,
                "response_text": r.response_text.replace("\r", " "),
                "citation_urls": "|".join(r.citation_urls),
                "brand_cited": status,
                "brand_position": position if position is not None else "",
                "competitor_citations": "|".join(comp_cited),
            })
    return out


def write_summary_md(
    out_dir: Path,
    runs_csv: Path,
    primary: BrandSpec,
    competitors: list,
    surfaces: list,
    runs_per_prompt: int,
) -> Path:
    rows = list(csv.DictReader(runs_csv.open(newline="", encoding="utf-8")))
    if not rows:
        die("runs.csv is empty — nothing to summarize")

    def pct(num, denom):
        return f"{(100 * num / denom):.1f}%" if denom else "n/a"

    def cited(rs):
        return [r for r in rs if r["brand_cited"] in {"primary", "secondary"}]

    def by_surface(rs, surface):
        return [r for r in rs if r["ai_surface"] == surface]

    shopping = [r for r in rows if r["intent_type"] == "shopping"]
    all_rows = rows
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = []
    lines.append(f"# Share of Answers — {primary.name}")
    lines.append("")
    lines.append(f"**Run date:** {today} UTC")
    lines.append(f"**Surfaces:** {', '.join(surfaces)}")
    lines.append(f"**Runs per prompt:** {runs_per_prompt}")
    lines.append(f"**Total response samples:** {len(rows)}")
    lines.append("")

    # ---- Goal A — Mentions ----
    lines.append("## TL;DR — Goal A: Mentions (share of voice)")
    lines.append("")
    lines.append("| Surface | Cited | Total | Share of Answers |")
    lines.append("|---|---|---|---|")
    for s in surfaces:
        rs = by_surface(all_rows, s)
        c = len(cited(rs))
        lines.append(f"| {s} | {c} | {len(rs)} | {pct(c, len(rs))} |")
    overall_a = pct(len(cited(all_rows)), len(all_rows))
    lines.append(f"| **all surfaces** | **{len(cited(all_rows))}** | **{len(all_rows)}** | **{overall_a}** |")
    lines.append("")

    # ---- Goal B — Shopping-intent share ----
    lines.append("## TL;DR — Goal B: Shopping-intent share (pipeline metric)")
    lines.append("")
    if not shopping:
        lines.append("_No shopping-intent prompts in this run._")
    else:
        lines.append("| Surface | Cited | Shopping prompts | Shopping-intent share |")
        lines.append("|---|---|---|---|")
        for s in surfaces:
            rs = by_surface(shopping, s)
            c = len(cited(rs))
            lines.append(f"| {s} | {c} | {len(rs)} | {pct(c, len(rs))} |")
        overall_b = pct(len(cited(shopping)), len(shopping))
        lines.append(f"| **all surfaces** | **{len(cited(shopping))}** | **{len(shopping)}** | **{overall_b}** |")
    lines.append("")

    # ---- Intent-class breakout ----
    lines.append("## Intent-class breakout (where you win/lose by funnel stage)")
    lines.append("")
    lines.append("| Intent class | " + " | ".join(surfaces) + " | overall |")
    lines.append("|---|" + "---|" * (len(surfaces) + 1))
    for cls in INTENT_CLASSES:
        cells = []
        cls_rows = [r for r in all_rows if r["intent_type"] == cls]
        for s in surfaces:
            rs = by_surface(cls_rows, s)
            cells.append(pct(len(cited(rs)), len(rs)))
        cells.append(pct(len(cited(cls_rows)), len(cls_rows)))
        lines.append(f"| {cls} | " + " | ".join(cells) + " |")
    lines.append("")

    # ---- Competitive table — overall + shopping-only ----
    lines.append("## Competitive share (overall)")
    lines.append("")
    lines.append("| Brand | Citations | Share of Answers |")
    lines.append("|---|---|---|")
    you_overall = len(cited(all_rows))
    lines.append(f"| **{primary.name}** | {you_overall} | {pct(you_overall, len(all_rows))} |")
    for c in competitors:
        n = len([r for r in all_rows if c.name in (r["competitor_citations"] or "").split("|")])
        lines.append(f"| {c.name} | {n} | {pct(n, len(all_rows))} |")
    lines.append("")

    if shopping:
        lines.append("## Competitive share (shopping-intent prompts only)")
        lines.append("")
        lines.append("| Brand | Citations | Shopping-intent share |")
        lines.append("|---|---|---|")
        you_shop = len(cited(shopping))
        lines.append(f"| **{primary.name}** | {you_shop} | {pct(you_shop, len(shopping))} |")
        for c in competitors:
            n = len([r for r in shopping if c.name in (r["competitor_citations"] or "").split("|")])
            lines.append(f"| {c.name} | {n} | {pct(n, len(shopping))} |")
        lines.append("")

    # ---- Where you win / lose (aggregated by prompt, surfaces listed) ----
    # Group by prompt_id; collect status-per-surface so the report shows
    # which surfaces won/lost each prompt rather than one row per surface.
    by_prompt = {}
    for r in all_rows:
        by_prompt.setdefault(r["prompt_id"], {"intent": r["intent_type"], "by_surface": {}})
        by_prompt[r["prompt_id"]]["by_surface"][r["ai_surface"]] = r["brand_cited"]

    primary_prompts = [pid for pid, d in by_prompt.items() if "primary" in d["by_surface"].values()]
    lines.append("## Where you win (cited as primary on ≥1 surface)")
    lines.append("")
    if not primary_prompts:
        lines.append("_No primary citations in this run._")
    else:
        for pid in primary_prompts:
            wins_on = [s for s, st in by_prompt[pid]["by_surface"].items() if st == "primary"]
            lines.append(f"- `{pid}` ({by_prompt[pid]['intent']}) — primary on: {', '.join(wins_on)}")
    lines.append("")

    not_cited_anywhere = [pid for pid, d in by_prompt.items()
                          if all(st == "none" for st in d["by_surface"].values())]
    lines.append("## Where you lose (not cited on any surface)")
    lines.append("")
    if not not_cited_anywhere:
        lines.append("_All prompts had at least one citation across the surface set._")
    else:
        for pid in not_cited_anywhere:
            intent = by_prompt[pid]["intent"]
            tag = "**SHOPPING** " if intent == "shopping" else ""
            lines.append(f"- {tag}`{pid}` ({intent})")
    lines.append("")

    partial = [pid for pid, d in by_prompt.items()
               if "none" in d["by_surface"].values() and any(st != "none" for st in d["by_surface"].values())]
    if partial:
        lines.append("## Per-surface gaps (cited on some surfaces, missed on others)")
        lines.append("")
        for pid in partial:
            misses = [s for s, st in by_prompt[pid]["by_surface"].items() if st == "none"]
            hits = [s for s, st in by_prompt[pid]["by_surface"].items() if st != "none"]
            intent = by_prompt[pid]["intent"]
            tag = "**SHOPPING** " if intent == "shopping" else ""
            lines.append(f"- {tag}`{pid}` ({intent}) — missed on: {', '.join(misses)} | cited on: {', '.join(hits)}")
        lines.append("")

    # ---- Surface-specific gaps ----
    lines.append("## Surface-specific gaps")
    lines.append("")
    surface_shares = {}
    for s in surfaces:
        rs = by_surface(all_rows, s)
        surface_shares[s] = (100 * len(cited(rs)) / len(rs)) if rs else 0
    if surface_shares:
        sorted_surfaces = sorted(surface_shares.items(), key=lambda x: x[1], reverse=True)
        spread = sorted_surfaces[0][1] - sorted_surfaces[-1][1]
        lines.append("Per-surface Share of Answers:")
        lines.append("")
        for s, pct_val in sorted_surfaces:
            lines.append(f"- **{s}:** {pct_val:.1f}%")
        lines.append("")
        if spread < 1:
            lines.append("**Spread:** 0pp — surfaces are tied (likely small sample size; rerun with more prompts to differentiate).")
        elif spread > 15:
            lines.append(f"**Spread:** {spread:.1f}pp — investigate why the worst surface is missing the brand. Possible causes: source authority gap on that platform, model-version differences, content not indexed in that surface's search corpus.")
        else:
            lines.append(f"**Spread:** {spread:.1f}pp — surfaces are roughly balanced.")
    lines.append("")

    # ---- Required gating language (Framework 03 + 04) ----
    lines.append("---")
    lines.append("")
    lines.append("## Required gating: read before citing these numbers")
    lines.append("")
    lines.append("The five fake-case-study warnings (Ethan Smith) — these gate every 'this worked' claim:")
    lines.append("")
    lines.append("1. **Misattribution.** AI usage is growing organically. Movement in this report does not prove your work caused it. Use a treated-vs-control prompt subset before declaring a tactic worked.")
    lines.append("2. **Relative vs. absolute.** Percentages are meaningless without base. Report % AND raw counts; flag any aggregate Share of Answers measured on <50 prompts as directional only.")
    lines.append("3. **Vanity metrics.** Citation count without conversion impact is a vanity metric. Connect this report to AI-referred sessions + downstream conversion in GA4 before making investment decisions.")
    lines.append("4. **Brand reputation bias.** If your brand has strong existing search authority, you'll appear in AI regardless of GEO work. Don't credit GEO tactics for what SEO authority earned.")
    lines.append("5. **Reproduction.** A single weekly run is one data point. Trend over ≥4 weeks before declaring a pattern.")
    lines.append("")
    lines.append("**SEO/GEO gate (Framework 04):** Any tactic proposed off the back of this report must pass: SEO-positive AND GEO-positive. Stop and re-evaluate any tactic that is SEO-neutral or SEO-negative.")
    lines.append("")

    # Stochasticity note
    if runs_per_prompt > 1:
        lines.append(f"_Variance note: each prompt was run {runs_per_prompt}x. Report shares are aggregated across all runs._")
    else:
        lines.append("_Single-run mode: AI responses are stochastic. Run with --runs-per-prompt 3 for production baselines._")

    out = out_dir / "summary.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def append_trends_csv(out_dir: Path, runs_csv: Path, surfaces: list) -> Path:
    rows = list(csv.DictReader(runs_csv.open(newline="", encoding="utf-8")))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    cols = ["run_date"]
    for s in surfaces:
        cols.append(f"{s}_share")
        cols.append(f"{s}_shopping_share")
    cols.append("overall_share")
    cols.append("overall_shopping_share")

    new_row = {"run_date": today}
    cited_rows = [r for r in rows if r["brand_cited"] in {"primary", "secondary"}]
    shopping_rows = [r for r in rows if r["intent_type"] == "shopping"]
    cited_shopping = [r for r in shopping_rows if r["brand_cited"] in {"primary", "secondary"}]
    for s in surfaces:
        s_rows = [r for r in rows if r["ai_surface"] == s]
        s_cited = [r for r in s_rows if r["brand_cited"] in {"primary", "secondary"}]
        s_shop = [r for r in s_rows if r["intent_type"] == "shopping"]
        s_shop_cited = [r for r in s_shop if r["brand_cited"] in {"primary", "secondary"}]
        new_row[f"{s}_share"] = round(100 * len(s_cited) / len(s_rows), 2) if s_rows else ""
        new_row[f"{s}_shopping_share"] = round(100 * len(s_shop_cited) / len(s_shop), 2) if s_shop else ""
    new_row["overall_share"] = round(100 * len(cited_rows) / len(rows), 2) if rows else ""
    new_row["overall_shopping_share"] = round(100 * len(cited_shopping) / len(shopping_rows), 2) if shopping_rows else ""

    out = out_dir / "trends.csv"
    write_header = not out.exists()
    with out.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if write_header:
            w.writeheader()
        w.writerow(new_row)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def confirm(msg: str) -> bool:
    if not sys.stdin.isatty():
        return True
    try:
        return input(f"{msg} [y/N]: ").strip().lower() in {"y", "yes"}
    except (EOFError, KeyboardInterrupt):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--prompts", type=Path, required=True, help="Prompt set CSV (from /cmo/geo/prompt-set-builder)")
    parser.add_argument("--brands", type=Path, help="Brands CSV (role,name,aliases,domain)")
    parser.add_argument("--init-brands", type=Path, help="Write a brands.csv template to this path and exit")
    parser.add_argument("--output", type=Path, required=False, help="Output directory")
    parser.add_argument("--runs-per-prompt", type=int, default=3)
    parser.add_argument("--surfaces", type=str, default=",".join(SUPPORTED_SURFACES),
                        help="Comma-separated subset of: " + ",".join(SUPPORTED_SURFACES))
    parser.add_argument("--limit", type=int, default=None, help="Run only first N prompts (for quick tests)")
    parser.add_argument("--max-cost", type=float, default=10.0, help="Abort if estimated cost exceeds this USD (default: 10)")
    parser.add_argument("--no-confirm", action="store_true", help="Skip the cost-confirmation prompt")
    parser.add_argument("--judge", action="store_true", help="Use Claude Haiku to classify primary/secondary instead of positional heuristic")
    parser.add_argument("--sleep-between", type=float, default=0.5, help="Seconds between calls within a provider (default 0.5)")
    parser.add_argument("--anthropic-model", default=DEFAULT_MODELS["anthropic"])
    parser.add_argument("--openai-model", default=DEFAULT_MODELS["openai"])
    parser.add_argument("--google-model", default=DEFAULT_MODELS["google"])
    parser.add_argument("--perplexity-model", default=DEFAULT_MODELS["perplexity"])
    opts = parser.parse_args()

    if opts.init_brands:
        write_brands_template(opts.init_brands)
        print(f"wrote brands template -> {opts.init_brands}")
        return 0

    if not opts.brands or not opts.output:
        die("--brands and --output are required (use --init-brands <path> to generate a template)")

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
    primary, competitors = load_brands(opts.brands)

    print(f"\nPrompts: {len(prompts)} (limit: {opts.limit or 'none'})")
    print(f"Primary brand: {primary.name} (domain={primary.domain or 'n/a'}, aliases={primary.aliases or '[]'})")
    print(f"Competitors: {[c.name for c in competitors]}")
    print(f"Surfaces: {surfaces}")
    print(f"Runs per prompt: {opts.runs_per_prompt}")
    print(f"Citation classifier: {'LLM-as-judge (Claude Haiku)' if opts.judge else 'positional heuristic'}")

    cost = estimate_cost(len(prompts), opts.runs_per_prompt, surfaces)
    print(f"\nEstimated cost: ${cost['total']:.2f} ({cost['calls']} calls)")
    for s, c in cost["by_surface"].items():
        print(f"  {s:<12} ${c:.3f}")
    if cost["total"] > opts.max_cost:
        die(f"estimated cost ${cost['total']:.2f} exceeds --max-cost ${opts.max_cost:.2f}")
    if not opts.no_confirm and not confirm("\nProceed?"):
        print("aborted.")
        return 1

    opts.output.mkdir(parents=True, exist_ok=True)

    print(f"\nRunning {cost['calls']} calls across {len(surfaces)} surfaces in parallel...\n")
    models = {
        "anthropic": opts.anthropic_model,
        "openai": opts.openai_model,
        "google": opts.google_model,
        "perplexity": opts.perplexity_model,
    }
    started = time.time()
    all_results = run_suite(
        prompts=prompts,
        surfaces=surfaces,
        runs_per_prompt=opts.runs_per_prompt,
        models=models,
        sleep_between=opts.sleep_between,
    )
    elapsed = time.time() - started
    print(f"\nDone in {elapsed:.1f}s. {len(all_results)} responses collected.")

    prompts_by_id = {p.prompt_id: p for p in prompts}
    runs_csv = write_runs_csv(opts.output, all_results, prompts_by_id, primary, competitors, opts.judge)
    summary = write_summary_md(opts.output, runs_csv, primary, competitors, surfaces, opts.runs_per_prompt)
    trends = append_trends_csv(opts.output, runs_csv, surfaces)
    print(f"\nWrote:")
    print(f"  {runs_csv}")
    print(f"  {summary}")
    print(f"  {trends}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
