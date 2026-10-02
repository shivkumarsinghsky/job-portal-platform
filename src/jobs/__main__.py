"""Run the prototype API: python -m jobs [--port 8000] [--seed]"""

from __future__ import annotations

import argparse

import uvicorn

from jobs.api import create_app
from jobs.portal import Portal
from jobs.seed import load_sample_jobs


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--seed", action="store_true", help="load sample jobs (company owner: recruiter-1)")
    args = p.parse_args()
    portal = Portal()
    if args.seed:
        load_sample_jobs(portal)
    uvicorn.run(create_app(portal), host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
