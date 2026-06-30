"""Entry point — runs the coordinator agent loop on a single inbound request."""
import argparse
from agent.coordinator import run_coordinator


def main() -> None:
    parser = argparse.ArgumentParser(description="IT Helpdesk Triage Agent")
    parser.add_argument("--input", required=True, help="Inbound request text")
    args = parser.parse_args()

    result = run_coordinator(args.input)
    print(result)


if __name__ == "__main__":
    main()
