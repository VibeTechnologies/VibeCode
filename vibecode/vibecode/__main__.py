"""Entry point for vibecode CLI."""

# Suppress all warnings at the very start
import warnings
import os
warnings.simplefilter("ignore")
os.environ["PYDANTIC_DISABLE_WARNINGS"] = "1"

from .cli import main

if __name__ == "__main__":
    main()