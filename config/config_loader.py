from pathlib import Path
import yaml

def load_keywords() -> list[str]:
    """
    Load keywords from the keywords.yaml file.

    Returns:
        list[str]: A list of keywords.
    """
    keywords_file = Path(__file__).parent / "keywords.yaml"
    with open(keywords_file, "r", encoding="utf-8") as f:
        keywords = yaml.safe_load(f)
    return keywords.get("keywords", [])