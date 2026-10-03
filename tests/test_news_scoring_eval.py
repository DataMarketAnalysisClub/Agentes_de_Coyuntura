"""Pisos de calidad de la calificacion de noticias (ver docs/news-scoring.md).

Si un cambio de reglas baja de estos pisos, revisar con
`python -m scripts.evaluate_news_scoring --details` que notas cambiaron antes
de bajar el piso.
"""

from pathlib import Path

from scripts.evaluate_news_scoring import DEFAULT_EVAL_FILE, evaluate, load_labeled_news

HOLDOUT_FILE = Path(DEFAULT_EVAL_FILE).with_name("news_eval_holdout.jsonl")


def test_scoring_meets_floors_on_development_set() -> None:
    report = evaluate(load_labeled_news(DEFAULT_EVAL_FILE))

    assert report.total == 160
    assert report.f1 >= 0.88
    assert report.precision_at[10] >= 0.9
    assert report.topic_accuracy >= 0.75
    assert report.region_accuracy >= 0.8


def test_scoring_meets_floors_on_holdout_set() -> None:
    report = evaluate(load_labeled_news(HOLDOUT_FILE))

    assert report.total == 63
    assert report.f1 >= 0.72
    assert report.topic_accuracy >= 0.7
