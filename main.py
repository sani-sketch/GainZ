"""Command-line entry point for the GainZ Alpha research project."""

from config.settings import load_settings


def main() -> None:
    """Load the research settings and show the current V1 scope."""
    settings = load_settings()
    print(f"{settings['project']['name']} is ready for research.")
    print(f"Universe: {', '.join(settings['universe']['symbols'])}")
    print("V1 mode: long-only daily research; no live trading.")


if __name__ == "__main__":
    main()
