"""Parser registry. Each parser exposes parse_list(html)->list[RawItem]
and parse_article(html)->ArticleBody."""
from . import sasol

REGISTRY = {
    "sasol": sasol,
}

BASE_URL = {
    "sasol": "https://www.sasol.com",
}


def get_parser(name: str):
    if name not in REGISTRY:
        raise KeyError(f"no parser for '{name}'. Available: {list(REGISTRY)}")
    return REGISTRY[name]
