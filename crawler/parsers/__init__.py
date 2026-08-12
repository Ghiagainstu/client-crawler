"""Parser registry. Each parser exposes parse_list(html)->list[RawItem]
and parse_article(html)->ArticleBody."""
from . import sasol
from . import hitachi

REGISTRY = {
    "sasol": sasol,
    "hitachi": hitachi,
}

BASE_URL = {
    "sasol": "https://www.sasol.com",
    "hitachi": "https://www.hitachi-hightech.com",
}


def get_parser(name: str):
    if name not in REGISTRY:
        raise KeyError(f"no parser for '{name}'. Available: {list(REGISTRY)}")
    return REGISTRY[name]
