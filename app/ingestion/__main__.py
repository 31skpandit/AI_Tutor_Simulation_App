"""Command-line ingestion (does the same work as the Syllabus Library page).

uv run python -m app.ingestion scan                      # register new files in source/ and extract them
uv run python -m app.ingestion status                    # list documents and progress
uv run python -m app.ingestion approve <id|all>          # mark all extracted pages as reviewed
uv run python -m app.ingestion index <id|all> [--include-unreviewed]
uv run python -m app.ingestion ask "question" [--language English|Hindi|Marathi]
uv run python -m app.ingestion clean <id|all>            # apply latest OCR clean-up to pages you did not edit
uv run python -m app.ingestion reindex <id|all>          # rebuild search entries (adds summaries/descriptions)
uv run python -m app.ingestion cloud <id> [--pages 4,5]  # re-read pages with the cloud model (default: pages
                                                         # with tables/figures); costs ~$0.005 per page
"""

import argparse
import sys

from app.core.config import get_settings
from app.ingestion.service import IngestionService
from app.jobs.runner import run_until_empty
from app.llm.service import build_router


def _service() -> IngestionService:
    settings = get_settings()
    router = build_router(settings)
    return IngestionService(router.engine, router, settings)


def _ids(service: IngestionService, target: str) -> list[int]:
    return [d.id for d in service.documents()] if target == "all" else [int(target)]


def _print_status(service: IngestionService) -> None:
    documents = service.documents()
    if not documents:
        print(f"No documents yet. Put files in {service.settings.source_dir} and run: scan")
        return
    print(f"{'ID':>3}  {'STATUS':10} {'PAGES':>5} {'DONE':>4} {'REVIEWED':>8} {'INDEXED':>7}  FILE")
    for d in documents:
        c = service.page_counts(d.id)
        print(
            f"{d.id:>3}  {d.status:10} {d.page_count:>5} {c['done']:>4} {c['reviewed']:>8} {c['indexed']:>7}  "
            f"{d.filename}  [Class {d.class_level or '?'} | {d.subject or '?'} | Ch {d.chapter_no or '?'}]"
        )
        if d.error:
            print(f"     ! {d.error}")


def _run_queue(service: IngestionService) -> None:
    def show(job):
        print(f"-> job {job.id}: {job.kind} document {job.document_id}", flush=True)

    count = run_until_empty(service, on_job=show)
    print(f"Processed {count} job(s).")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.ingestion",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan")
    sub.add_parser("status")
    approve = sub.add_parser("approve")
    approve.add_argument("target")
    index = sub.add_parser("index")
    index.add_argument("target")
    index.add_argument("--include-unreviewed", action="store_true")
    ask = sub.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--language", default="English", choices=["English", "Hindi", "Marathi"])
    clean = sub.add_parser("clean")
    clean.add_argument("target")
    reindex = sub.add_parser("reindex")
    reindex.add_argument("target")
    cloud = sub.add_parser("cloud")
    cloud.add_argument("target")
    cloud.add_argument("--pages", default="", help="comma-separated page numbers (default: suggested pages)")
    args = parser.parse_args(argv)

    service = _service()
    if args.command == "scan":
        report = service.scan_source()
        print(f"Source folder: {service.settings.source_dir}")
        print(
            f"New: {len(report.new)} | already registered: {report.known} | duplicates: {len(report.duplicates)} "
            f"| unsupported: {len(report.unsupported)} | errors: {len(report.errors)}"
        )
        for item in report.duplicates:
            print(f"  duplicate (skipped): {item.path.name} - {item.message}")
        for item in report.errors:
            print(f"  error: {item.path.name} - {item.message}")
        _run_queue(service)
        _print_status(service)
    elif args.command == "status":
        _print_status(service)
    elif args.command == "approve":
        for document_id in _ids(service, args.target):
            print(f"Document {document_id}: {service.mark_all_reviewed(document_id)} page(s) marked reviewed")
    elif args.command == "index":
        for document_id in _ids(service, args.target):
            service.enqueue(
                "index", document_id, options="include_unreviewed" if args.include_unreviewed else ""
            )
        _run_queue(service)
        _print_status(service)
    elif args.command == "clean":
        for document_id in _ids(service, args.target):
            print(f"Document {document_id}: {service.clean_extracted_text(document_id)} page(s) cleaned")
    elif args.command == "reindex":
        for document_id in _ids(service, args.target):
            print(f"Document {document_id}: re-indexing {service.reindex_document(document_id)} page(s)")
        _run_queue(service)
        _print_status(service)
    elif args.command == "cloud":
        document_id = int(args.target)
        pages = [int(p) for p in args.pages.split(",") if p.strip()] or service.pages_suggested_for_cloud(
            document_id
        )
        if not pages:
            print("No pages with tables or figures found; pass --pages to choose pages.")
            return 0
        print(f"Re-reading pages {pages} with the cloud model (about ${0.005 * len(pages):.3f})...")
        service.enqueue("reread_cloud", document_id, options="pages=" + ",".join(map(str, pages)))
        _run_queue(service)
        _print_status(service)
    elif args.command == "ask":
        from app.rag.tutor import answer

        result = answer(service.router, service.store, args.question, language=args.language)
        print(result.text)
        print("\nSources:")
        for n, hit in enumerate(result.hits, start=1):
            print(f"  [{n}] {hit.citation} (relevance {hit.score:.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
