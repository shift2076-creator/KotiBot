"""Nightly client check and download: ``python -m subsystems.pivault_admin.maintain [--check-only]``."""

import argparse
import sys

from . import client_packages


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check official client releases and download new ones.")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)

    if client_packages.offline():
        print("Offline mode is on: release checks and downloads are paused.")
        return 0

    try:
        errors = client_packages.maintain(check_only=args.check_only, progress=print)
    except client_packages.ClientRunBusy:
        print("Another client maintenance run is in progress; this run is skipped.")
        return 0

    print("Client checks needing review: " + ", ".join(errors) if errors else "Client releases are up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
