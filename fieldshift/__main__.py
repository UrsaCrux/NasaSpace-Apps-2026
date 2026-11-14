"""Entry point: ``python -m fieldshift``."""

import sys

from fieldshift.app import main

if __name__ == "__main__":
    sys.exit(main(sys.argv))
