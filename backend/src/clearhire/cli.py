"""Command line: `clearhire synth | eval | parse | seed | create-user | openapi`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_MODEL = "intfloat/multilingual-e5-small"


def cmd_synth(args: argparse.Namespace) -> int:
    from clearhire.synth.dataset import build_dataset

    summary = build_dataset(Path(args.out), count=args.count, seed=args.seed)
    print(json.dumps(summary, indent=2))
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    from clearhire.embeddings import load_embedder
    from clearhire.eval.runner import run, save, to_markdown
    from clearhire.ingest import TesseractOcr
    from clearhire.skills import load_taxonomy

    ocr = TesseractOcr(args.ocr_languages)
    report = run(Path(args.dataset), load_taxonomy(), load_embedder(args.model), ocr if ocr.available else None,
                 progress=lambda message: print(message, file=sys.stderr))  # fmt: skip
    if args.out:
        save(report, Path(args.out))
    print(to_markdown(report))
    return 0


def cmd_eval_assistant(args: argparse.Namespace) -> int:
    """Score the AI assistant against the configured model (CLEARHIRE_LLM_URL) on the synthetic dataset."""
    import asyncio

    from clearhire.eval.assistant import run_assistant, save, to_markdown
    from clearhire.tasks import build_services

    services = build_services()
    if services.llm is None:
        print("set CLEARHIRE_LLM_URL to evaluate the assistant", file=sys.stderr)
        return 2
    report = asyncio.run(run_assistant(Path(args.dataset), services.matcher.taxonomy, services.matcher.embedder,
                                       services.ocr, services.llm, pairs=args.pairs,
                                       progress=lambda message: print(message, file=sys.stderr)))  # fmt: skip
    if args.out:
        save(report, Path(args.out))
    print(to_markdown(report))
    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    """Read one CV and print what Clearhire extracts from it."""
    from clearhire.cv.profile import extract_profile
    from clearhire.ingest import TesseractOcr, read_document
    from clearhire.skills import load_taxonomy

    ocr = TesseractOcr(args.ocr_languages)
    document = read_document(Path(args.file).read_bytes(), ocr=ocr if ocr.available else None)
    taxonomy = load_taxonomy()
    profile = extract_profile(document.text, taxonomy)
    print(json.dumps({
        "media_type": document.media_type,
        "ocr_pages": document.ocr_pages,
        "name": profile.name,
        "total_months": profile.total_months,
        "positions": [{"title": p.title, "start": p.start, "end": p.end, "months": p.months} for p in profile.positions],
        "skills": {taxonomy.name(s): {"months": e.months, "named": e.explicit} for s, e in sorted(profile.skills.items())},
        "languages": {code: lang.level for code, lang in profile.languages.items()},
        "degree": profile.education.degree if profile.education else 0,
    }, ensure_ascii=False, indent=2))  # fmt: skip
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    """Fill the database with the synthetic dataset as a working demo."""
    import asyncio

    from clearhire.db.session import sessions
    from clearhire.services.seed import reset, seed
    from clearhire.tasks import build_services

    async def go() -> dict[str, int]:
        async with sessions()() as session:
            if args.reset:
                await reset(session)
            return await seed(session, build_services(), Path(args.dataset), password=args.password,
                              log=lambda message: print(message, file=sys.stderr))  # fmt: skip

    print(json.dumps(asyncio.run(go()), indent=2))
    return 0


def cmd_create_user(args: argparse.Namespace) -> int:
    import asyncio
    import getpass

    from clearhire.db.models import Role, User
    from clearhire.db.session import sessions
    from clearhire.security import hash_password

    password = getpass.getpass("Password: ")
    if len(password) < 12:
        print("use at least 12 characters", file=sys.stderr)
        return 1

    async def go() -> None:
        async with sessions()() as session:
            session.add(
                User(
                    email=args.email,
                    name=args.name,
                    role=Role(args.role),
                    password_hash=hash_password(password),
                )
            )
            await session.commit()

    asyncio.run(go())
    print(f"created {args.role} {args.email}")
    return 0


def cmd_openapi(args: argparse.Namespace) -> int:
    """Write the API schema the console and the portal generate their TypeScript types from."""
    from clearhire.api.app import create_app
    from clearhire.config import Settings

    spec = create_app(Settings(debug=True)).openapi()  # the schema does not depend on any setting
    text = json.dumps(spec, indent=2, ensure_ascii=False) + "\n"
    if args.out == "-":
        sys.stdout.write(text)
    else:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    return 0


def cmd_deploy_anchor(args: argparse.Namespace) -> int:
    """Deploy AuditAnchor with the configured key as owner and publisher; prints the address."""
    import asyncio

    from clearhire.config import get_settings
    from clearhire.tasks import chain_from

    chain = chain_from(get_settings())
    if chain is None or chain.address is None:
        print("set CLEARHIRE_CHAIN_RPC_URL and CLEARHIRE_ANCHOR_PRIVATE_KEY", file=sys.stderr)
        return 2

    async def go() -> str:
        address, receipt = await chain.deploy(args.publisher or chain.address or "")
        await chain.close()
        print(f"deployed in block {receipt.block}, tx {receipt.tx_hash}", file=sys.stderr)
        return address

    print(asyncio.run(go()))
    return 0


def cmd_anchor(args: argparse.Namespace) -> int:
    """Anchor the audit log: once, or every period with --loop (the `anchor` service runs that)."""
    import asyncio
    import time
    from datetime import UTC, datetime

    from clearhire.anchoring.chain import ChainError
    from clearhire.anchoring.service import anchor_pending, period_of, period_start
    from clearhire.config import get_settings
    from clearhire.db.session import sessions
    from clearhire.tasks import chain_from

    settings = get_settings()
    chain = chain_from(settings)
    if chain is None or chain.address is None or not chain.contract:
        print(
            "set CLEARHIRE_CHAIN_RPC_URL, CLEARHIRE_ANCHOR_PRIVATE_KEY and CLEARHIRE_ANCHOR_CONTRACT",
            file=sys.stderr,
        )
        return 2
    seconds = settings.anchor_period_seconds

    async def once(close_current: bool) -> None:
        async with sessions()() as session:
            row = await anchor_pending(session, chain, seconds, close_current=close_current)
        if row is None:
            print("nothing to anchor", file=sys.stderr)
        else:
            print(f"anchored period {row.period}: entries {row.first_id}..{row.last_id} ({row.entries}), "
                  f"root 0x{row.root.hex()}, tx {row.tx_hash}", file=sys.stderr)  # fmt: skip

    if not args.loop:
        asyncio.run(once(args.now))
        return 0
    while True:  # wake a minute after each period ends; a failure is retried at the next wake-up
        try:
            asyncio.run(once(False))
        except ChainError as exc:
            print(f"anchoring failed, retrying next period: {exc}", file=sys.stderr)
        except Exception as exc:  # the chain or the database is not there yet, or no contract at the address
            print(f"anchoring failed, retrying next period: {type(exc).__name__}: {exc}", file=sys.stderr)
        now = datetime.now(UTC)
        wake = period_start(period_of(now, seconds) + 1, seconds).timestamp() + 60
        time.sleep(max(30.0, wake - now.timestamp()))


def cmd_wait_db(args: argparse.Namespace) -> int:
    """Wait for the database to answer, and with --migrated for its schema to be current.

    Kubernetes init containers run this, so the API and the worker start only on a migrated database.
    """
    import asyncio
    import time

    from clearhire.db import schema
    from clearhire.db.session import engine, sessions

    async def go() -> int:
        deadline, last = time.monotonic() + args.timeout, ""
        while True:
            try:
                async with sessions()() as session:
                    done = await schema.applied(session)
                if not args.migrated or schema.is_current(done):
                    print("database ready" + (f" at {', '.join(sorted(done))}" if args.migrated else ""))
                    return 0
                need = sorted(schema.heads())
                state = f"waiting for migrations: at {sorted(done) or 'nothing'}, need {need}"
            except Exception as exc:  # not up yet, or not resolvable yet
                state = f"waiting for the database: {type(exc).__name__}"
            if state != last:
                print(state, file=sys.stderr)
                last = state
            if time.monotonic() > deadline:
                print("gave up", file=sys.stderr)
                return 1
            await asyncio.sleep(2)

    async def run() -> int:
        try:
            return await go()
        finally:
            await engine().dispose()

    return asyncio.run(run())


def cmd_anchor_fixture(args: argparse.Namespace) -> int:
    from clearhire.anchoring.fixture import write

    write(Path(args.out))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clearhire", description="Explainable AI recruiting.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("synth", help="generate the synthetic CV dataset")
    p.add_argument("--out", default="../datasets/synthetic")
    p.add_argument("--count", type=int, default=312)
    p.add_argument("--seed", type=int, default=42)
    p.set_defaults(func=cmd_synth)

    p = sub.add_parser("eval", help="score extraction, ranking and fairness on the synthetic dataset")
    p.add_argument("--dataset", default="../datasets/synthetic")
    p.add_argument("--out", default="../eval")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--ocr-languages", default="eng+rus")
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("eval-assistant", help="score the AI assistant against the configured language model")
    p.add_argument("--dataset", default="../datasets/synthetic")
    p.add_argument("--out", default="../eval/assistant")
    p.add_argument("--pairs", type=int, default=30)
    p.set_defaults(func=cmd_eval_assistant)

    p = sub.add_parser("parse", help="print what Clearhire reads from one CV file")
    p.add_argument("file")
    p.add_argument("--ocr-languages", default="eng+rus")
    p.set_defaults(func=cmd_parse)

    p = sub.add_parser("seed", help="load the synthetic dataset into the database as a demo")
    p.add_argument("--dataset", default="../datasets/synthetic")
    p.add_argument("--password", default="clearhire-demo", help="password for the three demo accounts")
    p.add_argument("--reset", action="store_true", help="empty every table first")
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("create-user", help="add a staff account (asks for the password)")
    p.add_argument("email")
    p.add_argument("name")
    p.add_argument("--role", choices=["admin", "recruiter", "hiring_manager"], default="recruiter")
    p.set_defaults(func=cmd_create_user)

    p = sub.add_parser("openapi", help="write the OpenAPI schema (for the TypeScript clients)")
    p.add_argument("--out", default="../api/openapi.json", help="a file, or - for stdout")
    p.set_defaults(func=cmd_openapi)

    p = sub.add_parser("deploy-anchor", help="deploy the AuditAnchor contract (prints its address)")
    p.add_argument("--publisher", help="the address allowed to anchor (default: the deployer)")
    p.set_defaults(func=cmd_deploy_anchor)

    p = sub.add_parser("anchor", help="anchor the audit log on the chain")
    p.add_argument(
        "--now", action="store_true", help="include the current period up to now (a first demo run)"
    )
    p.add_argument("--loop", action="store_true", help="keep anchoring every finished period")
    p.set_defaults(func=cmd_anchor)

    p = sub.add_parser("wait-db", help="wait for the database (Kubernetes init containers run this)")
    p.add_argument("--migrated", action="store_true", help="also wait until the schema is current")
    p.add_argument("--timeout", type=float, default=600, help="seconds before giving up")
    p.set_defaults(func=cmd_wait_db)

    p = sub.add_parser("anchor-fixture", help="write the Merkle fixture the contract test replays")
    p.add_argument("--out", default="../contracts/test/fixtures/merkle.json")
    p.set_defaults(func=cmd_anchor_fixture)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
