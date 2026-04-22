#!/usr/bin/env python3
"""
Compute revenue model and scaffold plan artifacts for /cmo/geo/plan.

Two modes:
  extract-baselines   Parse audit + SoA outputs → baselines.json
  build-plan          Read initiatives.json + business inputs → revenue model + scaffolds

Usage:
    # Stage 1: Extract baselines from audit + SoA
    python3 tools/geo_plan.py extract-baselines \
        --audit-dir clients/acme/geo/audit/2026-04-17/ \
        --soa-dir clients/acme/geo/share-of-answers/2026-04-16/ \
        --output clients/acme/geo/plan/2026-04-17/

    # Stage 2: Build plan (after Claude writes initiatives.json)
    python3 tools/geo_plan.py build-plan \
        --initiatives initiatives.json \
        --baselines baselines.json \
        --output clients/acme/geo/plan/2026-04-17/ \
        --client "Acme Corp" --segment mid-market \
        --acv 35000 --annual-organic-traffic 120000

    # Show B2B SaaS segment defaults
    python3 tools/geo_plan.py show-defaults

Requires: python-dotenv
Exit codes: 0 success, 2 argument/setup error
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # optional — .env not strictly needed for this tool


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIDENCE_LOW_FACTOR = 0.30
CONFIDENCE_HIGH_FACTOR = 1.70
DEFAULT_ATTRIBUTION_HAIRCUT = 0.50
DEFAULT_AI_TRAFFIC_SHARE = 0.05  # 5% of organic estimated as AI-referred

SEGMENT_DEFAULTS = {
    "mid-market": {
        "acv": 30000,
        "visitor_to_mql": 0.025,
        "mql_to_sql": 0.20,
        "sql_to_close": 0.25,
        "sales_cycle_months": 2,
    },
    "enterprise": {
        "acv": 150000,
        "visitor_to_mql": 0.0075,
        "mql_to_sql": 0.30,
        "sql_to_close": 0.20,
        "sales_cycle_months": 9,
    },
}

REVENUE_CSV_COLS = [
    "initiative", "goal", "baseline", "projected_lift_pct",
    "new_monthly_inbound", "pipeline_contribution_usd",
    "annual_revenue_impact_usd",
    "confidence_low", "confidence_mid", "confidence_high",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------------------
# Stage 1: Extract baselines
# ---------------------------------------------------------------------------


def parse_runs_csv(soa_dir: Path) -> dict[str, Any]:
    """Parse SoA runs.csv → Goal A + Goal B baseline numbers + competitor shares."""
    runs_path = soa_dir / "runs.csv"
    if not runs_path.exists():
        die(f"runs.csv not found at {runs_path}")

    rows = list(csv.DictReader(runs_path.open(newline="", encoding="utf-8")))
    if not rows:
        die("runs.csv is empty")

    valid = [r for r in rows if r.get("brand_cited") != "error"]
    cited = [r for r in valid if r["brand_cited"] in ("primary", "secondary")]

    # Surfaces
    surfaces = sorted(set(r["ai_surface"] for r in valid))

    # Goal A: overall mention share
    goal_a_by_surface = {}
    for s in surfaces:
        s_rows = [r for r in valid if r["ai_surface"] == s]
        s_cited = [r for r in s_rows if r["brand_cited"] in ("primary", "secondary")]
        goal_a_by_surface[s] = round(100 * len(s_cited) / len(s_rows), 1) if s_rows else 0

    overall_a = round(100 * len(cited) / len(valid), 1) if valid else 0

    # Goal B: shopping-intent share
    shopping = [r for r in valid if r.get("intent_type") == "shopping"]
    shopping_cited = [r for r in shopping if r["brand_cited"] in ("primary", "secondary")]
    goal_b_by_surface = {}
    for s in surfaces:
        s_rows = [r for r in shopping if r["ai_surface"] == s]
        s_cited = [r for r in s_rows if r["brand_cited"] in ("primary", "secondary")]
        goal_b_by_surface[s] = round(100 * len(s_cited) / len(s_rows), 1) if s_rows else 0

    overall_b = round(100 * len(shopping_cited) / len(shopping), 1) if shopping else 0

    # Competitor shares
    comp_counts: dict[str, dict[str, int]] = {}
    for r in valid:
        for comp in (r.get("competitor_citations") or "").split("|"):
            comp = comp.strip()
            if comp:
                comp_counts.setdefault(comp, {"cited": 0, "shopping_cited": 0})
                comp_counts[comp]["cited"] += 1
                if r.get("intent_type") == "shopping":
                    comp_counts[comp]["shopping_cited"] += 1

    comp_shares = {}
    for name, counts in comp_counts.items():
        comp_shares[name] = {
            "overall": round(100 * counts["cited"] / len(valid), 1),
            "shopping": round(100 * counts["shopping_cited"] / len(shopping), 1) if shopping else 0,
        }

    return {
        "goal_a": {
            "overall_share": overall_a,
            "by_surface": goal_a_by_surface,
            "total_responses": len(valid),
            "cited_responses": len(cited),
        },
        "goal_b": {
            "shopping_share": overall_b,
            "by_surface": goal_b_by_surface,
            "shopping_responses": len(shopping),
            "cited_shopping_responses": len(shopping_cited),
        },
        "competitor_shares": comp_shares,
    }


def parse_audit_dir(audit_dir: Path) -> dict[str, Any]:
    """Parse audit scorecard markdown files for scores and common issues."""
    scores: list[float] = []
    common_issues: dict[str, int] = {}
    risk_flags_detected: list[str] = []

    # Find individual scorecard files (generated by geo_audit.py)
    for md_file in sorted(audit_dir.glob("*_audit.md")):
        text = md_file.read_text(encoding="utf-8")

        # Extract overall score: "**Overall content score:** 61.3/100"
        m = re.search(r"Overall content score:\*?\*?\s*(\d+\.?\d*)/100", text)
        if m:
            scores.append(float(m.group(1)))

        # Extract per-signal scores from table rows: "| signal_name | 45/100 |"
        for m in re.finditer(r"\|\s*(\w[\w_]*)\s*\|\s*(\d+)/100\s*\|", text):
            signal_name = m.group(1)
            signal_score = int(m.group(2))
            if signal_score < 70:
                common_issues[signal_name] = common_issues.get(signal_name, 0) + 1

        # Extract risk flags: "[FLAG] Risk Name:"
        for m in re.finditer(r"\[FLAG\]\*?\*?\s*(.+?):", text):
            risk_flags_detected.append(m.group(1).strip())

    # Also check batch_audit_summary.md if no individual scorecards found
    if not scores:
        batch_path = audit_dir / "batch_audit_summary.md"
        if batch_path.exists():
            text = batch_path.read_text(encoding="utf-8")
            for m in re.finditer(r"\|\s*\S+\s*\|\s*(\d+\.?\d*)/100\s*\|", text):
                scores.append(float(m.group(1)))

    if not scores:
        return {
            "urls_audited": 0,
            "avg_score": 0,
            "score_distribution": {"ready_80_plus": 0, "needs_work_50_79": 0, "not_citable_below_50": 0},
            "common_issues": [],
            "risk_flags": [],
        }

    avg_score = round(sum(scores) / len(scores), 1)
    sorted_issues = sorted(common_issues.items(), key=lambda x: x[1], reverse=True)

    return {
        "urls_audited": len(scores),
        "avg_score": avg_score,
        "score_distribution": {
            "ready_80_plus": sum(1 for s in scores if s >= 80),
            "needs_work_50_79": sum(1 for s in scores if 50 <= s < 80),
            "not_citable_below_50": sum(1 for s in scores if s < 50),
        },
        "common_issues": [
            {"signal": name, "failing_pages": count, "pct": round(100 * count / len(scores))}
            for name, count in sorted_issues
        ],
        "risk_flags": list(set(risk_flags_detected)),
    }


def do_extract_baselines(audit_dir: Optional[Path], soa_dir: Optional[Path], output_dir: Path) -> int:
    """Stage 1: Extract baselines from audit + SoA outputs → baselines.json."""
    output_dir.mkdir(parents=True, exist_ok=True)

    baselines: dict[str, Any] = {
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }

    # Parse SoA
    if soa_dir and soa_dir.exists():
        soa_data = parse_runs_csv(soa_dir)
        baselines.update(soa_data)
        print(f"SoA baselines: Goal A = {soa_data['goal_a']['overall_share']}%, "
              f"Goal B = {soa_data['goal_b']['shopping_share']}%", file=sys.stderr)
    else:
        print("WARNING: No SoA directory — baselines will be partial", file=sys.stderr)
        baselines["goal_a"] = {"overall_share": None, "note": "SoA data not available"}
        baselines["goal_b"] = {"shopping_share": None, "note": "SoA data not available"}
        baselines["competitor_shares"] = {}

    # Parse audit
    if audit_dir and audit_dir.exists():
        scorecards_dir = audit_dir / "page-scorecards"
        target_dir = scorecards_dir if scorecards_dir.exists() else audit_dir
        audit_stats = parse_audit_dir(target_dir)
        baselines["audit"] = audit_stats
        print(f"Audit baselines: {audit_stats['urls_audited']} URLs, "
              f"avg score = {audit_stats['avg_score']}/100", file=sys.stderr)
    else:
        print("WARNING: No audit directory — audit baselines missing", file=sys.stderr)
        baselines["audit"] = {"urls_audited": 0, "note": "Audit data not available"}

    out_path = output_dir / "baselines.json"
    out_path.write_text(json.dumps(baselines, indent=2) + "\n", encoding="utf-8")
    print(f"\nBaselines → {out_path}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# Stage 2: Revenue model + scaffolds
# ---------------------------------------------------------------------------


def load_initiatives(path: Path) -> list[dict]:
    """Load and validate initiatives.json."""
    data = json.loads(path.read_text(encoding="utf-8"))
    initiatives = data.get("initiatives", [])
    if not initiatives:
        die("initiatives.json contains no initiatives")
    if len(initiatives) > 12:
        die(f"initiatives.json has {len(initiatives)} initiatives — hard cap is 12")

    required = {"id", "name", "goal", "seo_geo_tag", "ice_impact", "ice_confidence",
                "ice_effort", "projected_lift_pct"}
    for i, init in enumerate(initiatives):
        missing = required - set(init.keys())
        if missing:
            die(f"Initiative #{i+1} ({init.get('id', '?')}) missing fields: {sorted(missing)}")
        if init["seo_geo_tag"] == "GEO+ but SEO-":
            print(f"WARNING: {init['id']} tagged [GEO+ but SEO-] — flagged, deprioritized",
                  file=sys.stderr)
    return initiatives


def compute_ice(init: dict) -> float:
    """ICE = (Impact × Confidence) / Effort × 10."""
    effort = max(init["ice_effort"], 1)
    return round((init["ice_impact"] * init["ice_confidence"]) / effort * 10, 1)


def compute_revenue_model(
    initiatives: list[dict],
    baselines: dict[str, Any],
    biz: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compute per-initiative revenue projections. Returns list of model rows."""
    monthly_organic = biz["annual_organic_traffic"] / 12
    monthly_ai_sessions = monthly_organic * biz.get("ai_traffic_share", DEFAULT_AI_TRAFFIC_SHARE)

    goal_a_baseline = (baselines.get("goal_a") or {}).get("overall_share") or 0
    goal_b_baseline = (baselines.get("goal_b") or {}).get("shopping_share") or 0

    haircut = biz.get("attribution_haircut", DEFAULT_ATTRIBUTION_HAIRCUT)

    model_rows = []

    for init in initiatives:
        goal = init["goal"].upper()
        lift_pct = init["projected_lift_pct"]
        ice = compute_ice(init)

        row: dict[str, Any] = {
            "initiative": init["name"],
            "id": init["id"],
            "goal": goal,
            "seo_geo_tag": init["seo_geo_tag"],
            "phase": init.get("phase", ""),
            "ice_score": ice,
        }

        if goal in ("B", "BOTH"):
            baseline = goal_b_baseline
            # Relative lift: 15% means share goes from 35% → 40.25%
            new_share = baseline * (1 + lift_pct / 100)

            current_shopping_sessions = monthly_ai_sessions * (baseline / 100)
            new_shopping_sessions = monthly_ai_sessions * (new_share / 100)
            incremental_sessions = new_shopping_sessions - current_shopping_sessions

            incremental_mqls = incremental_sessions * biz["visitor_to_mql"]
            incremental_sqls = incremental_mqls * biz["mql_to_sql"]
            incremental_closed = incremental_sqls * biz["sql_to_close"]

            attributed_closed = incremental_closed * (1 - haircut)
            monthly_pipeline = incremental_sqls * biz["acv"] * (1 - haircut)
            annual_revenue = attributed_closed * 12 * biz["acv"]

            if goal == "BOTH":
                baseline_str = f"A:{goal_a_baseline:.1f}% / B:{baseline:.1f}%"
            else:
                baseline_str = f"{baseline:.1f}%"

            row.update({
                "baseline": baseline_str,
                "projected_lift_pct": lift_pct,
                "new_monthly_inbound": round(incremental_sessions, 1),
                "pipeline_contribution_usd": round(monthly_pipeline),
                "annual_revenue_impact_usd": round(annual_revenue),
                "confidence_low": round(annual_revenue * CONFIDENCE_LOW_FACTOR),
                "confidence_mid": round(annual_revenue),
                "confidence_high": round(annual_revenue * CONFIDENCE_HIGH_FACTOR),
            })

        elif goal == "A":
            baseline = goal_a_baseline
            # Goal A: qualitative + branded-search equivalent analogy
            monthly_branded = monthly_organic * 0.20  # est. 20% of organic is branded
            branded_lift_sessions = monthly_branded * (lift_pct / 100)
            cpc_equivalent = biz.get("branded_cpc_equivalent", 2.00)
            annual_equivalent = branded_lift_sessions * cpc_equivalent * 12

            row.update({
                "baseline": f"{baseline:.1f}%",
                "projected_lift_pct": lift_pct,
                "new_monthly_inbound": "n/a (brand awareness)",
                "pipeline_contribution_usd": "n/a",
                "annual_revenue_impact_usd": f"~${round(annual_equivalent):,} branded-search equiv",
                "confidence_low": round(annual_equivalent * CONFIDENCE_LOW_FACTOR),
                "confidence_mid": round(annual_equivalent),
                "confidence_high": round(annual_equivalent * CONFIDENCE_HIGH_FACTOR),
            })

        model_rows.append(row)

    model_rows.sort(key=lambda r: r.get("ice_score", 0), reverse=True)
    return model_rows


def write_revenue_csv(output_dir: Path, model_rows: list[dict]) -> Path:
    """Write revenue-model.csv."""
    out = output_dir / "revenue-model.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REVENUE_CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for row in model_rows:
            w.writerow(row)
    return out


def _dollar(val: Any) -> str:
    """Format a value as a dollar string, handling non-numeric gracefully."""
    if isinstance(val, (int, float)):
        return f"${val:,.0f}"
    return str(val)


def write_revenue_md(
    output_dir: Path,
    model_rows: list[dict],
    biz: dict,
    baselines: dict,
) -> Path:
    """Write revenue-model.md with the model + assumptions + sensitivity."""
    ga = baselines.get("goal_a", {})
    gb = baselines.get("goal_b", {})

    lines = [
        "# Revenue Impact Model",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "**Attribution model:** Assisted (50% haircut on modeled lift)",
        "",
        "## Assumptions (editable — all dollar figures trace to these)",
        "",
        "| Parameter | Value | Source |",
        "|---|---|---|",
        f"| ACV | ${biz['acv']:,.0f} | User input |",
        f"| Visitor → MQL | {biz['visitor_to_mql']*100:.1f}% | User input |",
        f"| MQL → SQL | {biz['mql_to_sql']*100:.0f}% | User input |",
        f"| SQL → Closed-won | {biz['sql_to_close']*100:.0f}% | User input |",
        f"| Sales cycle | {biz.get('sales_cycle_months', 'n/a')} months | User input |",
        f"| Annual organic traffic | {biz['annual_organic_traffic']:,} | User input |",
        f"| AI traffic share (est.) | {biz.get('ai_traffic_share', DEFAULT_AI_TRAFFIC_SHARE)*100:.0f}% | Estimated |",
        f"| Attribution haircut | {biz.get('attribution_haircut', DEFAULT_ATTRIBUTION_HAIRCUT)*100:.0f}% | Assisted model |",
    ]

    if ga.get("overall_share") is not None:
        lines.append(f"| Goal A baseline (mention share) | {ga['overall_share']}% | SoA measurement |")
    if gb.get("shopping_share") is not None:
        lines.append(f"| Goal B baseline (shopping-intent share) | {gb['shopping_share']}% | SoA measurement |")
    lines.extend([
        "| Confidence band | Low=30% / Mid=100% / High=170% | Default |",
        "",
        "## Per-Initiative Revenue Impact",
        "",
        "| # | Initiative | Goal | SEO/GEO | ICE | Lift | Annual (mid) | Low | High |",
        "|---|---|---|---|---|---|---|---|---|",
    ])

    total_mid = 0
    total_low = 0
    total_high = 0

    for i, row in enumerate(model_rows, 1):
        annual = row.get("annual_revenue_impact_usd", 0)
        low = row.get("confidence_low", 0)
        high = row.get("confidence_high", 0)

        if isinstance(annual, (int, float)):
            total_mid += annual
        if isinstance(low, (int, float)):
            total_low += low
        if isinstance(high, (int, float)):
            total_high += high

        lines.append(
            f"| {i} | {row['initiative'][:50]} | {row['goal']} | {row['seo_geo_tag']} | "
            f"{row.get('ice_score', '')} | {row['projected_lift_pct']}% | "
            f"{_dollar(annual)} | {_dollar(low)} | {_dollar(high)} |"
        )

    lines.extend([
        f"| | **TOTAL (not additive)** | | | | | **${total_mid:,.0f}** | **${total_low:,.0f}** | **${total_high:,.0f}** |",
        "",
        "> **Note:** Initiative impacts are modeled independently. Actual aggregate impact",
        "> will be less than the sum due to overlap. Use the total as a ceiling, not a forecast.",
        "",
    ])

    # Goal A note
    if any(r["goal"] == "A" for r in model_rows):
        lines.extend([
            "## Goal A Note (Mentions / Share of Voice)",
            "",
            "Goal A initiatives target brand mention share in AI answers — a share-of-voice metric.",
            "This does not translate directly to dollars. The 'branded-search equivalent' column",
            "estimates: *if branded search volume increases proportionally to mention share,",
            "what would that traffic be worth at current organic conversion rates?*",
            "",
            "This is an analogy, not a forecast. If your finance team rejects the analogy,",
            "present Goal A lift as qualitative only.",
            "",
        ])

    # Sensitivity
    ai_share = biz.get("ai_traffic_share", DEFAULT_AI_TRAFFIC_SHARE)
    lines.extend([
        "## Sensitivity Analysis",
        "",
        "| Scenario | Annual Revenue Impact |",
        "|---|---|",
        f"| Base case (as modeled) | ${total_mid:,.0f} |",
        f"| ACV 30% lower (${round(biz['acv'] * 0.7):,}) | ~${round(total_mid * 0.7):,.0f} |",
        f"| ACV 30% higher (${round(biz['acv'] * 1.3):,}) | ~${round(total_mid * 1.3):,.0f} |",
        f"| AI traffic share 2× ({ai_share*200:.0f}%) | ~${round(total_mid * 2):,.0f} |",
        f"| AI traffic share 0.5× ({ai_share*50:.0f}%) | ~${round(total_mid * 0.5):,.0f} |",
        f"| No attribution haircut (100% credit) | ~${round(total_mid * 2):,.0f} |",
        "",
    ])

    out = output_dir / "revenue-model.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def scaffold_eng_cards(output_dir: Path, initiatives: list[dict]) -> list[Path]:
    """Write eng-handoff card scaffolds. One per initiative."""
    cards_dir = output_dir / "eng-cards"
    cards_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for init in initiatives:
        card_id = init["id"]
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", init["name"].lower()).strip("-")[:40]
        filename = f"{card_id}_{slug}.md"

        lines = [
            f"# {card_id}: {init['name']}",
            "",
            f"**Goal:** {init['goal']} | **SEO/GEO:** {init['seo_geo_tag']} | "
            f"**Phase:** {init.get('phase', 'TBD')} | **Effort:** {init.get('effort_size', 'TBD')} | "
            f"**Role:** {init.get('role_needed', 'TBD')}",
            "",
            "## Context",
            "",
            "<!-- WHY this matters — 1-2 sentences, plain English. No GEO jargon without inline definition. -->",
            init.get("description", "[Claude fills in]"),
            "",
            "## What to do",
            "",
            "<!-- Specific, unambiguous instructions for someone who has never done GEO/AEO. -->",
            "",
        ]

        for step in init.get("steps", ["[Claude fills in specific steps]"]):
            lines.append(f"- [ ] {step}")

        lines.extend(["", "## Why", ""])

        findings = init.get("audit_findings", [])
        if findings:
            lines.append("**Audit findings:**")
            for f in findings:
                lines.append(f"- {f}")
            lines.append("")
        lines.append(f"**Research basis:** {init.get('context', '[Claude fills in framework reference]')}")

        lines.extend([
            "",
            "## Acceptance criteria",
            "",
        ])
        for ac in init.get("acceptance_criteria", ["[Claude fills in]"]):
            lines.append(f"- [ ] {ac}")

        lines.extend([
            "",
            "## Technical requirements",
            "",
        ])
        for tr in init.get("technical_requirements", ["[Claude fills in URLs, files, schemas affected]"]):
            lines.append(f"- {tr}")

        lines.extend([
            "",
            "## Estimated effort",
            "",
            f"- **Size:** {init.get('effort_size', 'TBD')}",
            f"- **Role needed:** {init.get('role_needed', 'TBD')}",
            f"- **Dependencies:** {', '.join(init.get('dependencies', [])) or 'None'}",
            "",
            "## References",
            "",
            "<!-- Link to relevant framework sections in research/geo-aeo/ -->",
            "",
        ])

        path = cards_dir / filename
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        paths.append(path)

    return paths


def scaffold_exec_one_pager(
    output_dir: Path,
    client: str,
    baselines: dict,
    model_rows: list[dict],
    initiatives: list[dict],
) -> Path:
    """Write exec-one-pager.md scaffold."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    total_mid = sum(r["confidence_mid"] for r in model_rows
                    if isinstance(r.get("confidence_mid"), (int, float)))
    total_low = sum(r["confidence_low"] for r in model_rows
                    if isinstance(r.get("confidence_low"), (int, float)))
    total_high = sum(r["confidence_high"] for r in model_rows
                     if isinstance(r.get("confidence_high"), (int, float)))

    top_3 = sorted(initiatives, key=lambda x: compute_ice(x), reverse=True)[:3]

    ga = baselines.get("goal_a", {})
    gb = baselines.get("goal_b", {})
    audit = baselines.get("audit", {})

    lines = [
        "# GEO Optimization Plan — Executive One-Pager",
        "",
        f"**Client:** {client}",
        f"**Date:** {today}",
        f"**Prepared by:** <!-- name -->",
        "",
        "---",
        "",
        "## The Ask",
        "",
        "<!-- Dollar investment + headcount / time commitment. Be specific. -->",
        "",
        "## The Return",
        "",
        f"**Projected annual revenue impact (mid-confidence):** ${total_mid:,.0f}",
        f"**Range:** ${total_low:,.0f} (conservative) — ${total_high:,.0f} (optimistic)",
        "",
        "Attribution model: assisted (50% haircut). All assumptions in revenue-model.md.",
        "",
        "## Current State",
        "",
    ]

    if ga.get("overall_share") is not None:
        lines.append(f"- **Goal A (mention share):** {ga['overall_share']}% of AI answers cite {client}")
    if gb.get("shopping_share") is not None:
        lines.append(f"- **Goal B (shopping-intent share):** {gb['shopping_share']}% on buying queries")
    if audit.get("avg_score"):
        dist = audit.get("score_distribution", {})
        lines.extend([
            f"- **Content citation-readiness:** {audit['avg_score']}/100 avg across {audit['urls_audited']} priority pages",
            f"  - Ready (80+): {dist.get('ready_80_plus', 0)} | "
            f"Needs work (50-79): {dist.get('needs_work_50_79', 0)} | "
            f"Not citable (<50): {dist.get('not_citable_below_50', 0)}",
        ])

    lines.extend([
        "",
        "## Why Now",
        "",
        "<!-- 2-3 bullets grounded in market data from research corpus -->",
        "",
        "## Top 3 Initiatives",
        "",
    ])
    for i, init in enumerate(top_3, 1):
        lines.append(f"{i}. **{init['name']}** ({init['seo_geo_tag']}, {init.get('phase', 'TBD')})")

    lines.extend([
        "",
        "## Risks If We Don't Act",
        "",
        "<!-- 2-3 bullets: competitor citation dominance, pipeline decay, category-narrative capture -->",
        "",
        "---",
        "",
        "*Full plan: plan.md | Revenue model: revenue-model.md | Eng handoff cards: eng-cards/*",
        "",
    ])

    out = output_dir / "exec-one-pager.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def scaffold_business_case(output_dir: Path, client: str) -> Path:
    """Write business-case.md scaffold."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [
        "# Business Case Appendix — GEO Optimization Program",
        "",
        f"**Client:** {client}",
        f"**Date:** {today}",
        "",
        "## Full Assumption Set",
        "",
        "See revenue-model.md for the complete assumptions table + sensitivity analysis.",
        "",
        "## Timeline + Staffing Plan",
        "",
        "### 30-day phase",
        "- <!-- Quick wins: content restructuring, robots.txt, llms.txt -->",
        "- **Staffing:** <!-- roles, hours -->",
        "- **Gate:** <!-- acceptance criteria to proceed to 60-day -->",
        "",
        "### 60-day phase",
        "- <!-- Medium-effort: schema markup, new content, competitive gaps -->",
        "- **Staffing:** <!-- roles, hours -->",
        "- **Gate:** <!-- acceptance criteria to proceed to 90-day -->",
        "",
        "### 90-day phase",
        "- <!-- Heavy lifts: site architecture, SSR, ongoing measurement program -->",
        "- **Staffing:** <!-- roles, hours -->",
        "- **Gate:** <!-- program review — continue, adjust, or wind down -->",
        "",
        "## Comparable-Company Benchmarks",
        "",
        "<!-- Cite from research/geo-aeo/ corpus. Examples:",
        "- Graphite client: 32% traffic growth + 75% signup growth over 6 months",
        "- AEO early adopters seeing 2.3x faster pipeline growth than traffic growth",
        "- Top 10 domains capture 46% of citations in typical verticals -->",
        "",
        "## FAQ",
        "",
        "### How much does this cost?",
        "<!-- Total investment: $ + headcount + timeline -->",
        "",
        "### How long until we see results?",
        "<!-- 30-day quick wins measurable; 90-day for full program read -->",
        "",
        "### How do we know it's working (attribution)?",
        "<!-- Treated vs control pages; Share of Answers trend; GA4 AI-referred conversion -->",
        "",
        "### What's the risk?",
        "<!-- Low — all recs are SEO+/GEO+ or GEO+-only; no SEO-negative tactics -->",
        "",
        "### Why not just do more SEO?",
        "<!-- SEO is necessary but insufficient. AI answers 40%+ of informational queries",
        "without sending clicks. GEO ensures visibility in the answer layer.",
        "Every GEO initiative in this plan is also SEO-positive. -->",
        "",
    ]

    out = output_dir / "business-case.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def do_build_plan(
    initiatives_path: Path,
    baselines_path: Path,
    output_dir: Path,
    biz: dict,
    client: str,
) -> int:
    """Stage 2: Build all plan artifacts from initiatives + business inputs."""
    output_dir.mkdir(parents=True, exist_ok=True)

    initiatives = load_initiatives(initiatives_path)
    baselines = json.loads(baselines_path.read_text(encoding="utf-8"))

    model_rows = compute_revenue_model(initiatives, baselines, biz)

    csv_path = write_revenue_csv(output_dir, model_rows)
    print(f"Revenue model CSV  → {csv_path}", file=sys.stderr)

    md_path = write_revenue_md(output_dir, model_rows, biz, baselines)
    print(f"Revenue model MD   → {md_path}", file=sys.stderr)

    card_paths = scaffold_eng_cards(output_dir, initiatives)
    print(f"Eng cards ({len(card_paths):>2})     → {output_dir / 'eng-cards/'}", file=sys.stderr)

    exec_path = scaffold_exec_one_pager(output_dir, client, baselines, model_rows, initiatives)
    print(f"Exec one-pager     → {exec_path}", file=sys.stderr)

    biz_path = scaffold_business_case(output_dir, client)
    print(f"Business case      → {biz_path}", file=sys.stderr)

    total_mid = sum(r["confidence_mid"] for r in model_rows
                    if isinstance(r.get("confidence_mid"), (int, float)))

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Plan artifacts generated for {client}", file=sys.stderr)
    print(f"  Initiatives:    {len(initiatives)}", file=sys.stderr)
    print(f"  Annual revenue: ${total_mid:,.0f} (mid-confidence)", file=sys.stderr)
    print(f"  Output:         {output_dir}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command")

    # --- extract-baselines ---
    p_ext = sub.add_parser("extract-baselines",
                           help="Parse audit + SoA outputs → baselines.json")
    p_ext.add_argument("--audit-dir", type=Path, help="Audit output directory")
    p_ext.add_argument("--soa-dir", type=Path, help="Share-of-answers output directory")
    p_ext.add_argument("--output", type=Path, required=True, help="Plan output directory")

    # --- build-plan ---
    p_build = sub.add_parser("build-plan",
                             help="Build plan artifacts from initiatives + business inputs")
    p_build.add_argument("--initiatives", type=Path, required=True,
                         help="initiatives.json (Claude-generated)")
    p_build.add_argument("--baselines", type=Path, required=True,
                         help="baselines.json (from extract-baselines)")
    p_build.add_argument("--output", type=Path, required=True, help="Plan output directory")
    p_build.add_argument("--client", type=str, required=True, help="Client name")
    p_build.add_argument("--segment", choices=["mid-market", "enterprise", "both"],
                         default="mid-market",
                         help="B2B SaaS segment — sets funnel defaults (default: mid-market)")
    p_build.add_argument("--acv", type=float, help="Average contract value USD (overrides segment default)")
    p_build.add_argument("--visitor-to-mql", type=float,
                         help="Visitor → MQL rate as decimal (overrides segment default)")
    p_build.add_argument("--mql-to-sql", type=float,
                         help="MQL → SQL rate as decimal (overrides segment default)")
    p_build.add_argument("--sql-to-close", type=float,
                         help="SQL → Closed-won rate as decimal (overrides segment default)")
    p_build.add_argument("--sales-cycle-months", type=int,
                         help="Average sales cycle in months (overrides segment default)")
    p_build.add_argument("--annual-organic-traffic", type=int, required=True,
                         help="Annual organic sessions")
    p_build.add_argument("--ai-traffic-share", type=float, default=DEFAULT_AI_TRAFFIC_SHARE,
                         help=f"AI-referred share of organic (default {DEFAULT_AI_TRAFFIC_SHARE})")
    p_build.add_argument("--attribution-haircut", type=float, default=DEFAULT_ATTRIBUTION_HAIRCUT,
                         help=f"Attribution haircut (default {DEFAULT_ATTRIBUTION_HAIRCUT})")

    # --- show-defaults ---
    sub.add_parser("show-defaults", help="Print B2B SaaS segment defaults as JSON")

    opts = parser.parse_args()

    if opts.command == "show-defaults":
        print(json.dumps(SEGMENT_DEFAULTS, indent=2))
        return 0

    if opts.command == "extract-baselines":
        if not opts.audit_dir and not opts.soa_dir:
            die("Provide at least one of --audit-dir or --soa-dir")
        return do_extract_baselines(opts.audit_dir, opts.soa_dir, opts.output)

    if opts.command == "build-plan":
        defaults = SEGMENT_DEFAULTS.get(opts.segment, SEGMENT_DEFAULTS["mid-market"])
        biz = {
            "acv": opts.acv or defaults["acv"],
            "visitor_to_mql": opts.visitor_to_mql if opts.visitor_to_mql is not None else defaults["visitor_to_mql"],
            "mql_to_sql": opts.mql_to_sql if opts.mql_to_sql is not None else defaults["mql_to_sql"],
            "sql_to_close": opts.sql_to_close if opts.sql_to_close is not None else defaults["sql_to_close"],
            "sales_cycle_months": opts.sales_cycle_months or defaults["sales_cycle_months"],
            "annual_organic_traffic": opts.annual_organic_traffic,
            "ai_traffic_share": opts.ai_traffic_share,
            "attribution_haircut": opts.attribution_haircut,
        }
        return do_build_plan(opts.initiatives, opts.baselines, opts.output, biz, opts.client)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
