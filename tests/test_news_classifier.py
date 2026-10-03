from datetime import UTC, datetime

import pytest

from data_sources.rss_news_client import RawNewsItem
from services.news_classifier import (
    canonicalize_url,
    classify_news,
    classify_region,
    classify_topic,
    deduplicate_news,
    is_same_story,
)


def _raw(source: str, title: str, url: str) -> RawNewsItem:
    return RawNewsItem(datetime(2026, 9, 29, tzinfo=UTC), source, title, url, "")


def test_chilean_outlets_default_to_chile_unless_keywords_or_foreign_section() -> None:
    items = classify_news(
        [
            _raw("Diario Financiero", "Dolar abre a la baja", "https://www.df.cl/mercados/bolsa-monedas/dolar"),
            _raw("La Tercera Pulso", "Codelco anuncia nuevo proyecto", "https://www.latercera.com/pulso/noticia/codelco"),
            _raw("Diario Financiero", "Anthropic advierte riesgos en su prospecto", "https://www.df.cl/internacional/ft/anthropic"),
            _raw("Diario Financiero", "China prepara estimulos", "https://www.df.cl/mercados/commodities/china"),
            _raw("Financial Times", "Bond investors turn oil traders", "https://www.ft.com/content/bonds"),
        ]
    )

    assert [item.region for item in items] == ["Chile", "Chile", "Global", "Global", "Global"]


def test_canonicalize_url_strips_tracking_params() -> None:
    url = "https://Example.com/story/?utm_source=x&keep=1&fbclid=abc#section"

    assert canonicalize_url(url) == "https://example.com/story?keep=1"


def test_deduplicate_news_uses_canonical_url_and_similar_titles() -> None:
    now = datetime.now(UTC)
    items = [
        RawNewsItem(now, "A", "Fed signals rate decision", "https://example.com/a?utm_source=x", ""),
        RawNewsItem(now, "B", "Fed signals rate decision", "https://example.com/a?utm_medium=y", ""),
        RawNewsItem(now, "C", "Fed signals rates decision", "https://example.com/b", ""),
    ]

    unique = deduplicate_news(items)

    assert len(unique) == 1
    assert unique[0].url == "https://example.com/a"


@pytest.mark.parametrize(
    ("title", "not_expected"),
    [
        ("Investors focus on status of talks", "EE.UU."),  # "us " dentro de focus/status
        ("Energy sector rallies", "regulacion financiera"),  # "sec" dentro de sector
        ("Markets in turmoil after vote", "commodities"),  # "oil" dentro de turmoil
        ("Corporate bond issuance slows", "tasas"),  # "rate" dentro de corporate
        ("Tell us what you think about bonus season", "EE.UU."),  # pronombre "us"
        ("EFE cifra en US$ 800 millones los pagos", "EE.UU."),  # US$ es moneda
    ],
)
def test_classifier_ignores_substring_false_positives(title: str, not_expected: str) -> None:
    assert classify_region(title) != not_expected
    assert classify_topic(title) != not_expected


def test_mexico_ipc_index_is_not_chilean_inflation() -> None:
    assert classify_region("IPC de Mexico sube 1% por bancos") == "Latam"
    assert classify_region("Bolsa: el Mexico IPC cierra al alza") == "Latam"
    assert classify_region("IPC de agosto sube 0,3%") == "Chile"


@pytest.mark.parametrize(
    ("title", "region", "topic"),
    [
        ("Fed signals two more rate cuts", "EE.UU.", "tasas"),
        ("Las tasas largas suben en Chile", "Chile", "tasas"),
        ("U.S. yields climb as jobs data beats", "EE.UU.", "tasas"),
        # "tasa de desempleo" es empleo, no tasas.
        ("Tasa de desempleo en EE.UU. baja", "EE.UU.", "empleo"),
        ("Desempleo en Chile llega a 8,7%", "Chile", "empleo"),
        ("Oil jumps on new sanctions", "Global", "commodities"),
        ("Chilean peso weakens", "Chile", "FX"),
        ("Tensiones geopoliticas en Europa", "Global", "geopolitica"),
        ("Brazil's central bank holds", "Latam", "bancos centrales"),
        ("Federal Reserve issues FOMC statement", "EE.UU.", "bancos centrales"),
        ("US-Iran war adds costs to EU fuel bill", "EE.UU.", "geopolitica"),
        ("Plan laboral del gobierno avanza", "Global", "empleo"),
    ],
)
def test_classifier_matches_whole_words_and_plurals(title: str, region: str, topic: str) -> None:
    assert classify_region(title) == region
    assert classify_topic(title) == topic


# Notas reales (2026-09-28/29) que antes caian en el primer tema de la lista.
@pytest.mark.parametrize(
    ("title", "summary", "topic"),
    [
        (
            "Expertos aprueban plan laboral, pero piden un subsidio al empleo más “robusto”",
            "El desempleo se ubica hoy en 9,5%. Con este plan la tasa de desocupación podría bajar cerca de un punto.",
            "empleo",
        ),
        (
            "Ministro Daniel Mas da señales de que el gasto público del Presupuesto 2027 podría superar el 1%",
            "Sobre el plan de empleo, calculó un impacto de un punto porcentual en la tasa de desocupación.",
            "politica fiscal",
        ),
        (
            "Dólar anota mayor valor en más de un año por tensiones en Medio Oriente",
            "La divisa estadounidense subió $8. El precio del petróleo Brent alcanzaba los US$98 por barril.",
            "FX",
        ),
        (
            "Bolsa chilena repunta tras racha de caídas y Wall Street abre al alza",
            "La última baja del IPSA medido en dólares lo hizo borrar sus avances de 2026.",
            "renta variable",
        ),
        (
            "Santander reduce a la mitad su proyección de crecimiento de Chile en 2026 y anticipa que la inflación"
            " tendrá su mayor avance en cuatro años",
            "Las expectativas de inversión impulsarían la recuperación de la actividad.",
            "actividad",
        ),
        (
            "Job openings are low and hiring is weak. Why the U.S. labor market won’t get better soon.",
            "War, high gas prices, rising interest rates and AI are keeping a lid on U.S. job creation.",
            "empleo",
        ),
    ],
)
def test_topic_is_the_most_mentioned_weighting_the_title(title: str, summary: str, topic: str) -> None:
    assert classify_topic(title, summary) == topic


def test_topic_ties_keep_keyword_order() -> None:
    # "rate" (tasas) y "fed" (bancos centrales) empatan: gana el primero de la lista.
    assert classify_topic("Fed signals two more rate cuts") == "tasas"


def test_latam_leaders_mark_region_without_naming_the_country() -> None:
    title = "Lula y Flávio Bolsonaro empatan en las encuestas a días de la primera vuelta presidencial"

    assert classify_region(title, default="Chile") == "Latam"


def test_same_story_matches_paraphrased_titles_but_not_unrelated_ones() -> None:
    assert is_same_story(
        "Fed’s Barr says more rate hikes likely to be needed to curb inflation",
        "Fed’s Barr signals more rate hikes needed amid inflation risks",
    )
    assert not is_same_story(
        "Fed’s Barr says more rate hikes likely to be needed to curb inflation",
        "BOE’s Taylor urges caution on rate hikes as second-round inflation risks lag",
    )
    # Titulos cortos: solo cuenta la similitud de texto.
    assert not is_same_story("Oil rises", "Oil falls")


def test_deduplicate_news_keeps_first_and_compares_only_titles_sharing_words() -> None:
    now = datetime.now(UTC)
    items = [
        RawNewsItem(now, "A", "Copper hits record on supply fears", "https://example.com/1", ""),
        RawNewsItem(now, "B", "Copper hits record on supply fear", "https://example.com/2", ""),
        RawNewsItem(now, "C", "Bolsa chilena repunta", "https://example.com/3", ""),
        RawNewsItem(now, "D", "Fed", "https://example.com/4", ""),
        RawNewsItem(now, "E", "Fed.", "https://example.com/5", ""),
    ]

    assert [item.source for item in deduplicate_news(items)] == ["A", "C", "D"]


def test_tags_help_the_topic_but_not_the_region() -> None:
    # Nota real de Senal DF (2026-10-03): el titular no nombra el tema.
    title = "Gobierno sale a buscar en Asia y Medio Oriente para no depender de EEUU"
    tags = ("combustible", "Energía", "ENAP", "Estados Unidos", "China")

    assert classify_topic(title) == "macro general"
    assert classify_topic(title, "", tags) == "commodities"
    items = classify_news(
        [RawNewsItem(datetime(2026, 10, 3, tzinfo=UTC), "Diario Financiero", "Gobierno sale a buscar diesel",
                     "https://www.df.cl/senal-df/el-deal/gobierno-sale-a-buscar-diesel", "", tags)]
    )
    assert items[0].region == "Chile"
    assert items[0].topic == "commodities"
