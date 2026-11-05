"""Command line: `clearhire synth | eval | parse`."""

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

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
