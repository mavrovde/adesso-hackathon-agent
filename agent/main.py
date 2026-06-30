from __future__ import annotations

import argparse
import json
import logging
import sys

from agent.coordinator import run_coordinator


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": %(message)s}',
        stream=sys.stderr,
    )


def main() -> int:
    _configure_logging()
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(description="IT Helpdesk Triage Agent")
    parser.add_argument("--input", required=True, help="The helpdesk request text")
    parser.add_argument("--user-id", default=None, help="Optional user identifier")
    args = parser.parse_args()

    try:
        result = run_coordinator(args.input, args.user_id)
        logger.debug(json.dumps(result))
        print(json.dumps(result, indent=2))
        return 0
    except Exception:
        logger.exception(json.dumps("Unhandled exception in main"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
