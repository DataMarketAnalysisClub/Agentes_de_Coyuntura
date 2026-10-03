import re
from dataclasses import dataclass

from services.news_classifier import classify_topic, compile_keywords, normalize_text
from storage.models import NewsItem

SOURCE_TIERS = {
    "federal reserve": 1,
    "ecb": 1,
    "banco central": 1,
    "cmf": 1,
    "ine": 1,
    "financial times": 2,
    "reuters": 2,
    "bloomberg": 2,
    "la tercera pulso": 2,
    "diario financiero": 2,
    "marketwatch": 3,
    "investing.com": 3,
}

LOW_VALUE_PATTERNS = (
    "social security",
    "retirement",
    "retiree",
    "pension advice",
    "high earners",
    "better time to invest",
    "how much should i",
    "personal finance",
    "mortgage",
    "credit card",
    "dividend yield dwarfs",
    "value stocks",
    "top newsletters",
    "newsletters are betting",
    "13 stocks",
    "stock picks",
    "hodl",
    "bitcoin",
    "crypto*",
    "buy its stock",
    "motley fool",
    "the street",
    "seeking alpha",
    # Analisis tecnico intradia de Investing.com ("...: Live levels").
    "live levels",
    "support and resistance",
    "double top",
    "double bottom",
    "breakout",
    "52-week low",
    "52-week high",
    # Notas de analistas sobre una accion y avisos administrativos de fondos.
    "price target",
    "account statement",
    "monthly statement",
)

# Patrones sobre el titular que una lista de palabras no captura.
LOW_VALUE_TITLE_PATTERNS = (
    # "S&P 500 wedged at 7,739 between key support and resistance: Live"
    re.compile(r":\s*live(?: levels)?$"),
    # Finanzas personales en primera persona (columnas de consejo de
    # MarketWatch): "I'm 80 years old. Should I move out...", "My mother died
    # and I'm her executor". El apostrofo tipografico se pierde al normalizar.
    re.compile(r"(?<![a-z])i'?m (?:\d{1,3}|in my \d0s)(?![0-9])"),
    re.compile(r"(?<![a-z])should (?:i|we)(?![a-z])"),
    re.compile(
        r"(?<![a-z])my (?:wife|husband|mother|father|parents|son|daughter|sister|brother|boyfriend|girlfriend)"
        r"(?![a-z])"
    ),
    # "Why is Aritzia stock gaining today?"
    re.compile(r"^why (?:is|are) .{1,60}(?:stock|stocks|shares) (?:up|down|\w+ing) today"),
)

# Comunicados administrativos de bancos centrales: su fuente es tier 1 y el
# nombre "federal reserve" cuenta como alta senal, asi que antes pasaban
# siempre y desplazaban a noticias de mercado. Se evaluan solo sobre el
# titulo y solo para esas fuentes; FOMC, minutas y decisiones de tasas pasan.
ADMINISTRATIVE_NOTICE_SOURCES = ("federal reserve", "ecb")
ADMINISTRATIVE_NOTICE_PATTERNS = (
    "approval of application",
    "approval of the application",
    "enforcement action",
    "public comment",
    "seek comment",
    "request for comment",
    "community bank",
    "discount rate meetings",
    "banknote",
    "implementation guideline",
    "comment period",
    # Titulo mensual fijo del BCE para sus decisiones no monetarias.
    "in addition to decisions setting interest rates",
)

# Nombres de las fuentes oficiales: aparecen en casi todos sus titulares
# ("Federal Reserve Board announces...") y no dicen nada del contenido.
_OFFICIAL_SELF_NAMES = re.compile(
    r"(?<![a-z])(?:federal reserve board|federal reserve|european central bank|ecb)(?![a-z])"
)

HIGH_SIGNAL_TERMS = (
    "fed",
    "federal reserve",
    "ecb",
    "inflation",
    "inflacion",
    "rates",
    "tasas",
    "yield",
    "treasury",
    # "jobs" a secas aparece en notas de carrera; el dato macro es el informe.
    "jobs report",
    "jobs data",
    "nonfarm",
    "payroll",
    "cpi",
    "pce",
    "gdp",
    "imacec",
    "copper",
    "cobre",
    "oil",
    "brent",
    "wti",
    "dollar",
    "dolar",
    "peso",
    "china",
    "wall street",
    "nasdaq",
    "s&p",
    "geopolit*",
    "central bank",
    "banco central",
    "tariff",
    "tariffs",
    "trade",
    "shipping costs",
    "supreme court",
    "fed governor",
    # Empleo, presupuesto, crecimiento, etc. llegan por el tema
    # (`MACRO_SIGNAL_TOPICS`). "Bolsa" sola no: "salir a bolsa" es una
    # apertura en bolsa. Elecciones solo presidenciales.
    "ipsa",
    "ipc",
    "pib",
    "bolsa chilena",
    "bolsa de santiago",
    "presidencial",
    "presidential",
)

# Temas macro (de `classify_topic`) que bastan como senal. Quedan fuera
# "empresas", "renta variable" (una accion puntual no es macro) y
# "regulacion financiera".
MACRO_SIGNAL_TOPICS = frozenset(
    {"tasas", "inflacion", "actividad", "empleo", "politica fiscal", "bancos centrales", "FX", "commodities",
     "geopolitica"}
)

# Temas que bastan como senal en fuentes tier 3: los de mercado, donde la
# palabra clave rara vez aparece en notas de estilo de vida.
MARKET_SIGNAL_TOPICS = frozenset({"tasas", "inflacion", "bancos centrales", "FX", "commodities"})

# Palabras completas, no substrings: "fed" no calza con "fedex" ni "oil" con
# "turmoil". "geopolit" y "crypto" son prefijos.
_LOW_VALUE_PATTERN = compile_keywords({"low": LOW_VALUE_PATTERNS})["low"]
_HIGH_SIGNAL_PATTERN = compile_keywords({"high": HIGH_SIGNAL_TERMS})["high"]
_ADMINISTRATIVE_NOTICE_PATTERN = compile_keywords({"admin": ADMINISTRATIVE_NOTICE_PATTERNS})["admin"]


@dataclass(frozen=True)
class NewsQualityDecision:
    keep: bool
    reason: str
    score: int


def evaluate_news_quality(item: NewsItem) -> NewsQualityDecision:
    source = normalize_text(item.source)
    # Sin el nombre de la fuente: "federal reserve" en la fuente contaba como
    # alta senal para cualquier comunicado del Fed.
    title = normalize_text(item.title)
    text = normalize_text(f"{item.title} {item.summary}")

    if _LOW_VALUE_PATTERN.search(text) or any(pattern.search(title) for pattern in LOW_VALUE_TITLE_PATTERNS):
        return NewsQualityDecision(False, "low_value_pattern", 0)
    if is_administrative_notice(item):
        return NewsQualityDecision(False, "administrative_notice", 0)

    tier = source_tier(source)
    score = max(0, 5 - tier)
    if not _has_macro_signal(item, text, tier):
        return NewsQualityDecision(False, "low_macro_relevance", score)
    score += 3
    if item.region in {"Chile", "Latam", "EE.UU."}:
        score += 1
    if item.impact_score >= 7:
        score += 2
    elif item.impact_score >= 5:
        score += 1

    if score < 4:
        return NewsQualityDecision(False, "low_editorial_score", score)
    return NewsQualityDecision(True, "selected_candidate", score)


def _has_macro_signal(item: NewsItem, text: str, tier: int) -> bool:
    """Tema macro o termino de alta senal.

    Las fuentes oficiales (tier 1) antes pasaban siempre; ahora tambien
    necesitan senal, pero sin contar su propio nombre: un discurso de Lagarde
    sobre IA o un plazo de comentarios del Fed no son noticia de mercado, una
    decision de politica monetaria o un comunicado del FOMC si.
    """
    if tier >= 3:
        # MarketWatch e Investing.com publican mucha nota de carrera y finanzas
        # personales ("Switching jobs to get higher pay..."): ahi un tema
        # amplio como empleo o actividad no basta, hace falta un termino macro.
        return item.topic in MARKET_SIGNAL_TOPICS or bool(_HIGH_SIGNAL_PATTERN.search(text))
    if tier > 1:
        return item.topic in MACRO_SIGNAL_TOPICS or bool(_HIGH_SIGNAL_PATTERN.search(text))
    title = _OFFICIAL_SELF_NAMES.sub(" ", normalize_text(item.title))
    summary = _OFFICIAL_SELF_NAMES.sub(" ", normalize_text(item.summary))
    return classify_topic(title, summary) in MACRO_SIGNAL_TOPICS or bool(
        _HIGH_SIGNAL_PATTERN.search(f"{title} {summary}")
    )


def is_administrative_notice(item: NewsItem) -> bool:
    source = normalize_text(item.source)
    if not any(name in source for name in ADMINISTRATIVE_NOTICE_SOURCES):
        return False
    return bool(_ADMINISTRATIVE_NOTICE_PATTERN.search(normalize_text(item.title)))


def source_tier(normalized_source: str) -> int:
    for source_name, tier in SOURCE_TIERS.items():
        if source_name in normalized_source:
            return tier
    return 4
