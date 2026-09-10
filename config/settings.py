"""Load the small, human-readable project configuration."""

from pathlib import Path
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.toml"


def load_settings() -> dict:
    """Return settings from the project's TOML configuration file."""
    with SETTINGS_PATH.open("rb") as settings_file:
        return tomllib.load(settings_file)
