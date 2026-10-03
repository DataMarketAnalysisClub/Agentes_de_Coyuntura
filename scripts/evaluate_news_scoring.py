"""Evalua la calificacion de noticias contra un conjunto etiquetado a mano.

Uso:
    python -m scripts.evaluate_news_scoring              # resumen de metricas
    python -m scripts.evaluate_news_scoring --details    # + cada error
    python -m scripts.evaluate_news_scoring --file otro.jsonl

Cada linea del archivo es una nota real con su etiqueta: `relevant` (la
consideraria un editor del brief como candidata a titular) y, si es
relevante, el `topic` y la `region` correctos. Las notas se reclasifican con
el codigo actual (region, tema, impacto, filtro de calidad), asi que correr
esto antes y despues de un cambio muestra si mejora o empeora.

Limites: el impacto se calcula sin movimientos de mercado (el archivo no
guarda precios) y sin deduplicar (cada nota etiquetada se evalua). Ver
`docs/news-scoring.md`.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from services.impact_scoring import with_impact_scores
from services.news_classifier import classify_region, classify_topic, default_region, normalize_text
from services.news_quality import evaluate_news_quality, source_tier
from storage.models import NewsItem

DEFAULT_EVAL_FILE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "news_eval.jsonl"
TOP_K = (10, 20)


@dataclass(frozen=True)
class LabeledNews:
    item: NewsItem
    relevant: bool
    topic: str | None
    region: str | None


@dataclass
class EvaluationReport:
    total: int
    relevant: int
    kept: int
    true_positives: int
    topic_hits: int
    region_hits: int
    precision_at: dict[int, float]
    false_positives: list[NewsItem] = field(default_factory=list)
    false_negatives: list[tuple[NewsItem, str]] = field(default_factory=list)
    topic_misses: list[tuple[NewsItem, str]] = field(default_factory=list)
    region_misses: list[tuple[NewsItem, str]] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.true_positives / self.kept if self.kept else 0.0

    @property
    def recall(self) -> float:
        return self.true_positives / self.relevant if self.relevant else 0.0

    @property
    def f1(self) -> float:
        total = self.precision + self.recall
        return 2 * self.precision * self.recall / total if total else 0.0

    @property
    def topic_accuracy(self) -> float:
        return self.topic_hits / self.relevant if self.relevant else 0.0

    @property
    def region_accuracy(self) -> float:
        return self.region_hits / self.relevant if self.relevant else 0.0


def load_labeled_news(path: Path = DEFAULT_EVAL_FILE) -> list[LabeledNews]:
    """Lee el archivo y reclasifica cada nota con las reglas actuales."""
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    items = [
        NewsItem(
            timestamp=datetime.fromisoformat(record["timestamp"]),
            source=record["source"],
            title=record["title"],
            url=record["url"],
            summary=record["summary"],
            region=classify_region(
                record["title"], record["summary"], default_region(record["source"], record["url"])
            ),
            topic=classify_topic(record["title"], record["summary"]),
        )
        for record in records
    ]
    scored = with_impact_scores(items, [])
    return [
        LabeledNews(item, bool(record["relevant"]), record.get("topic"), record.get("region"))
        for item, record in zip(scored, records, strict=True)
    ]


def _rank_key(item: NewsItem) -> tuple[int, int, int, datetime]:
    # Mismo orden que `select_executive_news`.
    return (
        evaluate_news_quality(item).score,
        item.impact_score,
        max(0, 5 - source_tier(normalize_text(item.source))),
        item.timestamp,
    )


def evaluate(labeled: list[LabeledNews]) -> EvaluationReport:
    report = EvaluationReport(
        total=len(labeled),
        relevant=sum(entry.relevant for entry in labeled),
        kept=0,
        true_positives=0,
        topic_hits=0,
        region_hits=0,
        precision_at={},
    )
    kept: list[LabeledNews] = []
    for entry in labeled:
        decision = evaluate_news_quality(entry.item)
        if decision.keep:
            kept.append(entry)
            if entry.relevant:
                report.true_positives += 1
            else:
                report.false_positives.append(entry.item)
        elif entry.relevant:
            report.false_negatives.append((entry.item, decision.reason))
        if not entry.relevant:
            continue
        if entry.item.topic == entry.topic:
            report.topic_hits += 1
        else:
            report.topic_misses.append((entry.item, entry.topic or ""))
        if entry.item.region == entry.region:
            report.region_hits += 1
        else:
            report.region_misses.append((entry.item, entry.region or ""))
    report.kept = len(kept)

    ranked = sorted(kept, key=lambda entry: _rank_key(entry.item), reverse=True)
    for k in TOP_K:
        top = ranked[:k]
        report.precision_at[k] = sum(entry.relevant for entry in top) / len(top) if top else 0.0
    return report


def format_report(report: EvaluationReport, details: bool = False) -> str:
    lines = [
        f"Notas: {report.total} ({report.relevant} relevantes segun la etiqueta)",
        f"Filtro de calidad: pasan {report.kept}",
        f"  precision {report.precision:.2f} | recall {report.recall:.2f} | F1 {report.f1:.2f}",
        "  " + " | ".join(f"precision@{k} {value:.2f}" for k, value in report.precision_at.items()),
        f"Tema correcto (relevantes): {report.topic_accuracy:.2f}",
        f"Region correcta (relevantes): {report.region_accuracy:.2f}",
    ]
    if details:
        lines.append("\nPasan sin ser relevantes:")
        lines += [f"  [{item.source}] {item.title}" for item in report.false_positives]
        lines.append("\nRelevantes rechazadas:")
        lines += [f"  [{item.source}] ({reason}) {item.title}" for item, reason in report.false_negatives]
        lines.append("\nTema distinto (asignado -> esperado):")
        lines += [f"  {item.topic} -> {expected}: {item.title}" for item, expected in report.topic_misses]
        lines.append("\nRegion distinta (asignada -> esperada):")
        lines += [f"  {item.region} -> {expected}: {item.title}" for item, expected in report.region_misses]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, default=DEFAULT_EVAL_FILE)
    parser.add_argument("--details", action="store_true", help="lista cada error")
    args = parser.parse_args()
    print(format_report(evaluate(load_labeled_news(args.file)), details=args.details))


if __name__ == "__main__":
    main()
