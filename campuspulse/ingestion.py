"""Isolated upload parsing: byte, time and Linux memory limits."""

import logging
import multiprocessing
import os
import re
from pathlib import PurePosixPath

from campuspulse.config import Settings
from campuspulse.models import DataError, ExtractedTable

logger = logging.getLogger(__name__)


def safe_filename(name: str) -> str:
    return re.sub(r"[^\w.() -]", "_", PurePosixPath(name.replace("\\", "/")).name)[:120] or "upload"


def _worker(connection, data: bytes, filename: str, settings: Settings, separator: str | None):
    try:
        if os.name == "posix":
            import resource

            # Virtual memory already mapped by Python/NumPy is not resident memory.
            # Allow a fixed additional allocation budget in the disposable process.
            if os.path.exists("/proc/self/statm"):
                with open("/proc/self/statm") as statm:
                    current = int(statm.read().split()[0]) * os.sysconf("SC_PAGE_SIZE")
                cap = current + settings.extraction_memory_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
            resource.setrlimit(
                resource.RLIMIT_CPU, (settings.extraction_timeout, settings.extraction_timeout + 1)
            )
        if filename.lower().endswith(".pdf"):
            from campuspulse.pdf_parser import parse_pdf

            result = parse_pdf(data, filename, settings)
        else:
            from campuspulse.csv_parser import parse_csv

            result = parse_csv(data, filename, settings, separator)
        # Objects are produced by trusted parser code, never deserialized from the upload.
        connection.send((True, result))
    except DataError as exc:
        connection.send((False, str(exc)))
    except Exception as exc:  # noqa: BLE001 -- untrusted native parser boundary
        logger.warning("Parser failed: %s", type(exc).__name__)
        connection.send(
            (
                False,
                "The file could not be parsed safely. Re-export it as a structured PDF or UTF-8 CSV.",
            )
        )
    finally:
        connection.close()


def ingest(
    data: bytes, filename: str, settings: Settings, separator: str | None = None
) -> list[ExtractedTable]:
    filename = safe_filename(filename)
    if not filename.lower().endswith((".pdf", ".csv")):
        raise DataError("Only PDF and CSV files are supported.")
    if not data or len(data) > settings.max_upload_mb * 1024 * 1024:
        raise DataError(f"Upload a nonempty file up to {settings.max_upload_mb} MB.")
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_worker, args=(child, data, filename, settings, separator), daemon=True
    )
    process.start()
    child.close()
    try:
        if not parent.poll(settings.extraction_timeout):
            raise DataError(
                "Extraction exceeded its time limit. Upload fewer pages or use a CSV export."
            )
        try:
            success, result = parent.recv()
        except EOFError as exc:
            raise DataError(
                "Extraction exceeded a resource limit or the parser stopped. Try a smaller file."
            ) from exc
        if not success:
            raise DataError(result)
        return result
    finally:
        parent.close()
        process.join(timeout=0.2)
        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
        if process.is_alive():
            process.kill()
            process.join(timeout=1)
