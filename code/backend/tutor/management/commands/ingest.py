"""
Django management command: python manage.py ingest

Runs the full RAG ingestion pipeline — parses SEP HTML files and VTT
transcripts, chunks them, embeds via Ollama (nomic-embed-text), and
stores in ChromaDB.
"""

from django.core.management.base import BaseCommand

from tutor.ingestion.pipeline import run_ingestion


class Command(BaseCommand):
    help = "Ingest SEP articles and transcripts into ChromaDB for RAG retrieval."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-wipe",
            action="store_true",
            default=False,
            help="Append to the existing collection instead of rebuilding it.",
        )

    def handle(self, *args, **options):
        wipe = not options["no_wipe"]

        if wipe:
            self.stdout.write("Rebuilding ChromaDB collection from scratch...")
        else:
            self.stdout.write("Appending to existing ChromaDB collection...")

        self.stdout.write("")

        summary = run_ingestion(wipe=wipe)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Ingestion complete."))
        self.stdout.write(f"  SEP chunks:        {summary['sep_chunks']:>4}")
        self.stdout.write(f"  Transcript chunks: {summary['transcript_chunks']:>4}")
        self.stdout.write(f"  Total stored:      {summary['total_stored']:>4}")
        self.stdout.write("")
        self.stdout.write("Per source:")

        # sources keys are "source_type:source_id"
        for key, count in summary["sources"].items():
            source_type, source_id = key.split(":", 1)
            label = f"{source_id:<24}({source_type}):"
            self.stdout.write(f"  {label} {count:>6}")
