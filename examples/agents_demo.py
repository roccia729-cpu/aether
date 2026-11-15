"""Synthetic agent log demo for `aether agents scan`."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

now = datetime.now(tz=timezone.utc)
path = Path("/tmp/aether_agents_demo.jsonl")

lines = []
# baseline-like normal activity
for i in range(40):
    ts = (now - timedelta(hours=6) + timedelta(minutes=i * 5)).isoformat()
    lines.append(
        json.dumps(
            {
                "timestamp": ts,
                "attributes": {"tool": "bash", "command": f"echo heartbeat {i}", "status": "ok"},
            }
        )
    )

# recent risky + noisy activity
for i in range(15):
    ts = (now - timedelta(minutes=30) + timedelta(minutes=i)).isoformat()
    cmd = "rm -rf /tmp/build" if i == 5 else f"npm test #{i}"
    status = "error" if i % 4 == 0 else "ok"
    lines.append(
        json.dumps(
            {
                "timestamp": ts,
                "attributes": {"tool": "bash", "command": cmd, "status": status},
            }
        )
    )

path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Wrote {path}")
print("Run: aether agents scan /tmp/aether_agents_demo.jsonl --hours 2")
