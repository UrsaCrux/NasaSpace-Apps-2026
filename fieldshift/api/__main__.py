"""Command line: python -m fieldshift.api LON LAT [--radius M] [--start D] [--end D]."""

import argparse
import json
import sys

from fieldshift.api import get_site_data, list_providers


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m fieldshift.api",
                                     description="Get field data for a position.")
    parser.add_argument("lon", type=float, nargs="?", help="longitude in degrees")
    parser.add_argument("lat", type=float, nargs="?", help="latitude in degrees")
    parser.add_argument("--radius", type=float, default=1000.0, help="radius in metres")
    parser.add_argument("--start", help="first day, YYYY-MM-DD")
    parser.add_argument("--end", help="last day, YYYY-MM-DD")
    parser.add_argument("--only", nargs="+", metavar="NAME", help="only these providers")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    parser.add_argument("--list", action="store_true", help="list the providers and exit")
    args = parser.parse_args(argv)

    if args.list:
        for name, title, status in list_providers():
            print(f"{name:15} {status:12} {title}")
        return 0
    if args.lon is None or args.lat is None:
        parser.error("lon and lat are required")

    site = get_site_data(args.lon, args.lat, args.radius, args.start, args.end, args.only)
    print(json.dumps(site.to_dict(), indent=2, ensure_ascii=False) if args.json
          else site.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
