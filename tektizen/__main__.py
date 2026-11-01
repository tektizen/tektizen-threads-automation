"""Command-line entry point: ``python -m tektizen <command>``.

Used by the GitHub Actions workflows; also handy locally.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import prompts, storage


def _github_output(**values: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            for key, value in values.items():
                fh.write(f"{key}={value}\n")


def cmd_init(args: argparse.Namespace) -> int:
    created = storage.init_data()
    print("created: " + (", ".join(created) if created else "(nothing — all data files exist)"))
    return cmd_check(args)


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


def cmd_generate(args: argparse.Namespace) -> int:
    from . import pipeline
    from .runs import recorded_run
    from .settings import auto_publish_allowed

    workflow = {"daily": "daily-content", "manual": "manual-generation", "ideas": "idea-research"}[args.mode]
    with recorded_run(workflow) as rec:
        ctx = pipeline.build_context(rec)
        if args.mode == "daily":
            items = pipeline.run_daily(ctx)
        elif args.mode == "ideas":
            pipeline.run_research(ctx, max_ideas=5)
            items = []
        else:
            item = pipeline.run_manual(ctx, topic=args.topic or "", fmt=args.format, tone=args.tone or "",
                                       instructions=args.instructions or "")
            items = [item] if item else []
        ready = [i for i in items if i["status"] == "READY_TO_PUBLISH"]
        _github_output(publish="true" if ready and auto_publish_allowed(ctx.settings) else "false",
                       content_ids=",".join(i["id"] for i in items))
        failed = [i for i in items if i["status"] == "FAILED"]
        if failed and len(failed) == len(items):
            rec.error(f"all {len(items)} item(s) failed")
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    from integrations.zernio_client import ZernioClient

    from .publishing import publisher
    from .runs import recorded_run
    from .settings import load_settings

    pending = [i for i in storage.load("content")["items"]
               if i["status"] in ("READY_TO_PUBLISH", "PUBLISHING")
               or (i["status"] == "PUBLISH_UNCERTAIN" and (i.get("publishing") or {}).get("zernio_post_id"))]
    if not pending:
        print("Nothing to publish or reconcile.")  # no run record → no empty commit on scheduled checks
        return 0
    with recorded_run("publish-approved") as rec:
        settings = load_settings()
        client = ZernioClient()
        if not client.api_key:
            rec.error("ZERNIO_API_KEY is not set; nothing published")
            return 1
        publisher.reconcile_uncertain(rec, client)
        only = set(args.content_id) if args.content_id else None
        stats = publisher.publish_ready(rec, settings, client, only_ids=only)
        rec.info(f"publishing summary: {stats}")
    return 0


def cmd_analyze(_: argparse.Namespace) -> int:
    from integrations.zernio_client import ZernioClient

    from . import learning, performance, pipeline
    from .publishing import publisher
    from .runs import recorded_run

    with recorded_run("performance-analysis") as rec:
        client = ZernioClient()
        if client.api_key:
            publisher.reconcile_uncertain(rec, client)
            performance.collect_metrics(rec, client)
        else:
            rec.warn("ZERNIO_API_KEY not set; skipping metrics collection")
        ctx = pipeline.build_context(rec)
        learning.run_learning(rec, ctx.runner)
    return 0


def cmd_command(args: argparse.Namespace) -> int:
    from . import commands, pipeline
    from .runs import recorded_run
    from .settings import load_settings

    raw = args.json if args.json is not None else open(args.file, encoding="utf-8").read()
    try:
        cmd = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"invalid command JSON: {exc}")
        return 2
    actor = os.environ.get("TEKTIZEN_ACTOR") or os.environ.get("GITHUB_ACTOR") or "local"
    with recorded_run(f"dashboard-command:{cmd.get('type', '?')}", trigger="dashboard") as rec:
        settings = load_settings()
        try:
            result = commands.apply_command(cmd, actor, settings)
        except commands.CommandError as exc:
            rec.error(f"command rejected: {exc}")
            _github_output(publish="false", ok="false")
            return 1
        rec.info(result["message"])
        publish = bool(result.get("publish"))
        follow = result.get("ai")
        if follow:
            ctx = pipeline.build_context(rec, settings=settings)
            if follow["op"] == "evaluate":
                item = pipeline.evaluate_existing(ctx, follow["content_id"], user_notes=follow.get("user_notes"),
                                                  force_edit=follow.get("force_edit", False))
                if follow.get("then_approve"):
                    if item["status"] == "PENDING_APPROVAL" and not item["evaluation"]["critical_fact_failure"]:
                        commands.apply_command({"type": "approve", "content_id": item["id"]}, actor, settings)
                        publish = True
                    else:
                        rec.warn(f"{item['id']}: still has a critical fact-check failure; left pending")
            elif follow["op"] == "regenerate":
                pipeline.run_manual(ctx, topic=follow["topic"], fmt=follow["format"], tone=follow["tone"],
                                    instructions=follow["instructions"], regenerate_of=follow["content_id"],
                                    feedback=follow["feedback"])
        _github_output(publish="true" if publish else "false", ok="true")
    return 0


def cmd_accounts(_: argparse.Namespace) -> int:
    from integrations.zernio_client import ZernioClient, ZernioError

    try:
        accounts = ZernioClient().list_accounts("threads")
    except ZernioError as exc:
        print(f"error: {exc}")
        return 1
    if not accounts:
        print("No Threads accounts connected in Zernio. Connect @tektizen in the Zernio dashboard first.")
        return 1
    for a in accounts:
        print(f"{a['id']}  @{a['username']}  active={a['is_active']}  needs_reconnection={a['needs_reconnection']}")
    print("\nPut the ID of @tektizen into Settings → Publishing → Threads account ID.")
    return 0


def cmd_merge_driver(args: argparse.Namespace) -> int:
    from .merge import run_driver

    return run_driver(args.base, args.ours, args.theirs, args.path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tektizen", description="TektiZen Content Intelligence engine")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create missing data files (never overwrites)").set_defaults(func=cmd_init)
    sub.add_parser("check", help="validate data files, prompts, and config").set_defaults(func=cmd_check)

    g = sub.add_parser("generate", help="run the content pipeline")
    g.add_argument("--mode", choices=["daily", "manual", "ideas"], default="daily")
    g.add_argument("--topic")
    g.add_argument("--format", default="single", choices=["single", "thread", "question", "opinion", "educational",
                                                          "storytelling", "tools_recommendation", "news_commentary"])
    g.add_argument("--tone")
    g.add_argument("--instructions")
    g.set_defaults(func=cmd_generate)

    p = sub.add_parser("publish", help="publish READY_TO_PUBLISH content via Zernio")
    p.add_argument("--content-id", action="append")
    p.set_defaults(func=cmd_publish)

    sub.add_parser("analyze", help="collect metrics and update learning memory").set_defaults(func=cmd_analyze)

    c = sub.add_parser("command", help="apply a dashboard command")
    src = c.add_mutually_exclusive_group(required=True)
    src.add_argument("--json")
    src.add_argument("--file")
    c.set_defaults(func=cmd_command)

    sub.add_parser("zernio-accounts", help="list connected Threads accounts").set_defaults(func=cmd_accounts)

    m = sub.add_parser("merge-driver", help=argparse.SUPPRESS)
    for name in ("base", "ours", "theirs", "path"):
        m.add_argument(name)
    m.set_defaults(func=cmd_merge_driver)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
