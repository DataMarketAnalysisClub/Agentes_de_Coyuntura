"""Compute a quality score for a phase 3 editorial email sample.

The score is a simple MVP heuristic (0-100) that helps reviewers spot
regressions quickly. It does NOT replace human review.

v2 adds qualitative checks (generic language, raw score prefixes, topic-only
bullets, and conditional mentions of Chile / COPPER) so a 100/100 is harder to
reach and better reflects editorial quality, not just structural completeness.
"""

from __future__ import annotations

import re

from services.ai.schemas import AiEditorialEmail

_GENERIC_HEADLINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^Coyuntura regional y de mercados$", re.IGNORECASE),
    re.compile(r"^DMAC\s+Coyuntura$", re.IGNORECASE),
)

_GENERIC_READING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"el conjunto de hechos sugiere movimientos vinculados a los focos", re.IGNORECASE),
    re.compile(r"el flujo se concentro en\b", re.IGNORECASE),
    re.compile(r"\bflujo de noticias del dia\b", re.IGNORECASE),
)

_RAW_SCORE_PREFIX = re.compile(r"^\s*\[\d+\]\s*")

_TOPIC_ONLY_BULLET = re.compile(
    r"^(en\s+[\w\sáéíóúñ]+:|bancos centrales:|politica fiscal:|forex:|"
    r"commodities:|mercados:|macro general:)$",
    re.IGNORECASE,
)


def _all_facts(email: AiEditorialEmail) -> list[str]:
    facts: list[str] = []
    facts.extend(email.executive_summary)
    for s in email.sections:
        facts.extend(s.body)
        facts.extend(s.bullets)
    return facts


def _join_text(*parts: str) -> str:
    return " ".join(p for p in parts if p).strip()


def compute_quality_score(
    email: AiEditorialEmail,
    news_count: int,
    phase2_regional_reports_count: int,
    source_count: int,
    chart_count: int,
    snapshots: list | None = None,
    news: list | None = None,
    fallback_used: bool = False,
) -> dict:
    """Compute a quality score (0-100) and a dict of boolean checks.

    Each check is worth 6 points, plus up to 16 bonus points. A small floor
    penalty is applied when the run used the deterministic fallback or had no
    charts, so 100/100 is reserved for high-quality editorial runs.
    """
    _ = fallback_used  # currently only used to apply a score cap below
    checks: dict[str, bool] = {}
    facts = _all_facts(email)
    snapshots = snapshots or []
    news = news or []

    checks["has_regional_sections"] = (
        len(email.sections) > 1
        or (len(email.sections) == 1 and email.sections[0].heading != "Visualizaciones")
    )

    checks["has_source_notes"] = bool(email.source_notes)

    seen_facts: set[str] = set()
    duplicates = 0
    for f in facts:
        normalized = f.lower().strip().rstrip(".")
        if normalized in seen_facts and normalized:
            duplicates += 1
        seen_facts.add(normalized)
    checks["has_no_duplicate_titles"] = duplicates == 0

    checks["has_minimum_summary_points"] = 1 <= len(email.executive_summary) <= 4

    checks["has_charts"] = chart_count > 0

    section_chart_ids = {cid for s in email.sections for cid in s.chart_ids}
    orphan_specs = {spec.chart_id for spec in email.chart_specs} - section_chart_ids
    checks["has_no_orphan_charts"] = (
        bool(email.chart_specs) and not orphan_specs if email.chart_specs else True
    )

    checks["has_cautions"] = bool(email.editorial_cautions)

    subject_ok = 0 < len(email.subject.strip()) <= 80
    checks["has_valid_subject_length"] = subject_ok

    preheader_ok = 0 < len(email.preheader.strip()) <= 120
    checks["has_valid_preheader_length"] = preheader_ok

    checks["has_headline"] = bool(email.headline.strip())

    if news_count > 0:
        checks["preserved_news"] = phase2_regional_reports_count > 0
    else:
        checks["preserved_news"] = True

    headline_clean = email.headline.strip()
    checks["headline_not_generic"] = bool(headline_clean) and not any(
        p.match(headline_clean) for p in _GENERIC_HEADLINE_PATTERNS
    )

    body_blob = _join_text(
        email.headline,
        email.preheader,
        " ".join(email.executive_summary),
        " ".join(
            line
            for s in email.sections
            if s.heading != "Visualizaciones"
            for line in s.body
        ),
    )
    generic_phrase_count = sum(
        1 for p in _GENERIC_READING_PATTERNS if p.search(body_blob)
    )
    checks["reading_not_generic"] = generic_phrase_count == 0

    raw_score_prefix_count = sum(1 for f in facts if _RAW_SCORE_PREFIX.match(f))
    checks["no_raw_score_prefixes"] = raw_score_prefix_count == 0

    topic_only_bullet_count = sum(
        1 for s in email.sections for b in s.bullets if _TOPIC_ONLY_BULLET.match(b.strip())
    )
    checks["no_topic_only_bullets"] = topic_only_bullet_count == 0

    chile_present_in_input = any(
        _looks_like_chile(getattr(n, "region", None))
        or _looks_like_chile(getattr(n, "country", None))
        for n in news
    )
    if chile_present_in_input:
        blob = _join_text(email.headline, email.subject, " ".join(s.heading for s in email.sections))
        checks["mentions_chile_when_present"] = _looks_like_chile(blob)
    else:
        checks["mentions_chile_when_present"] = True

    copper_moving = any(
        (getattr(s, "symbol", None) == "COPPER" and (getattr(s, "change_pct", None) or 0) != 0)
        for s in snapshots
    )
    if copper_moving:
        blob = _join_text(
            email.headline, email.subject, email.preheader,
            " ".join(
                line
                for s in email.sections
                for line in s.body
            ),
            " ".join(
                line
                for s in email.sections
                for line in s.bullets
            ),
        )
        checks["mentions_copper_when_moving"] = "cobre" in blob.lower()
    else:
        checks["mentions_copper_when_moving"] = True

    if news_count > 0:
        checks["section_count_reasonable"] = 1 <= len(email.sections) <= 8
    else:
        checks["section_count_reasonable"] = True

    base_score = sum(6 for v in checks.values() if v)

    bonus = 0
    if 1 <= chart_count <= 4:
        bonus += 8
    if source_count >= 3:
        bonus += 8

    score = min(100, base_score + bonus)
    if chart_count == 0:
        score = min(score, 96)
    if fallback_used:
        score = min(score, 96)

    return {
        "score": score,
        "quality_version": "v2",
        "checks": checks,
        "duplicate_titles_count": duplicates,
        "raw_score_prefix_count": raw_score_prefix_count,
        "topic_only_bullet_count": topic_only_bullet_count,
        "generic_phrase_count": generic_phrase_count,
        "chart_count": chart_count,
        "source_count": source_count,
        "news_count": news_count,
        "phase2_regional_reports_count": phase2_regional_reports_count,
        "section_count": len(email.sections),
    }


def _looks_like_chile(value: str | None) -> bool:
    if not value:
        return False
    return "chile" in value.lower()
