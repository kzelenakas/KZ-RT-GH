from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.models import RuleDefinition


def load_ruleset(path: Path) -> tuple[list[RuleDefinition], str]:
    """Load an external ruleset file. Version = name + content hash, so any
    change to the file produces a new recorded ruleset_version."""
    raw = Path(path).read_bytes()
    data = json.loads(raw.decode("utf-8-sig"))  # tolerate BOM from Windows editors
    rules = [RuleDefinition.model_validate(r) for r in data.get("rules", [])]
    name = data.get("name", Path(path).stem)
    digest = hashlib.sha256(raw).hexdigest()[:12]
    return rules, f"{name}-{digest}"
