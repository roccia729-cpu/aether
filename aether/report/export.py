import json
from pathlib import Path

from ..models import Anomaly


def to_json(anomalies: list[Anomaly], path: Path) -> None:
    data = [
        {
            "kind": a.kind,
            "level": a.level.value,
            "window_start": a.window_start.isoformat(),
            "window_end": a.window_end.isoformat(),
            "description": a.description,
            "evidence": a.evidence,
        }
        for a in anomalies
    ]
    Path(path).write_text(json.dumps(data, indent=2))
