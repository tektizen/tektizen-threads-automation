"""Command-line entry point: ``python -m tektizen <command>``."""

from __future__ import annotations

import argparse
import sys

from . import prompts, storage


def cmd_init(_: argparse.Namespace) -> int:
    created = storage.init_data()
    print("created: " + (", ".join(created) if created else "(nothing — all data files exist)"))
    return cmd_check(_)


def cmd_check(_: argparse.Namespace) -> int:
    ok = True
    for name, error in storage.check_all().items():
        print(f"{'OK ' if error is None else 'ERR'} data/{name}.json" + ("" if error is None else f"\n    {error}"))
        ok &= error is None
    for agent in prompts.AGENTS:
        try:
            prompts.load_prompt(agent)
            print(f"OK  agents/prompts/{agent}.md")
        except prompts.PromptError as exc:
            print(f"ERR agents/prompts/{agent}.md\n    {exc}")
            ok = False
    for doc in prompts.CONFIG_DOCS:
        try:
            prompts.load_config(doc)
            print(f"OK  config/{doc}.md")
        except prompts.PromptError as exc:
            print(f"ERR config/{doc}.md\n    {exc}")
            ok = False
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tektizen", description="TektiZen Content Intelligence engine")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create missing data files (never overwrites)").set_defaults(func=cmd_init)
    sub.add_parser("check", help="validate data files, prompts, and config").set_defaults(func=cmd_check)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
