"""Loads the configurable rule set the Risk Analyzer checks clauses against.

Swap in a different rule set per document type (NDA vs vendor SLA vs HR
policy) by pointing CLAUSEGUARD_RULES_FILE at a different JSON file with the
same shape as default_rules.json.
"""

import json
import os
from pathlib import Path

from clauseguard.models.schemas import Rule

_DEFAULT_RULES_PATH = Path(__file__).parent / "default_rules.json"


def load_rules(path: str | Path | None = None) -> list[Rule]:
    rules_path = Path(path or os.environ.get("CLAUSEGUARD_RULES_FILE", _DEFAULT_RULES_PATH))
    data = json.loads(rules_path.read_text(encoding="utf-8"))
    return [Rule.model_validate(item) for item in data]
