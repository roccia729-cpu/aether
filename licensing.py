import os

from . import config

FREE_MAX_BASELINE_HOURS = 72


def is_pro() -> bool:
    """Placeholder: Pro se c'è AETHER_PRO_KEY o il file license.key."""
    if os.environ.get("AETHER_PRO_KEY"):
        return True
    return (config.data_dir() / "license.key").exists()
