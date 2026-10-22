"""
uc1-search/ingestion/scanner.py
Directory scanner and batch ingestion pipeline for UC1.
Scans Samba shares, S3 buckets, and local directories, extracts CAD/BIM/text,
redacts PII with Presidio, vectorizes, and indexes into OpenSearch.
"""

import os
import sys
import time
import logging
from typing import Dict, Any, Optional

# Ensure enrichment and indexing packages are in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from enrichment.extractor import DocumentExtractor
from enrichment.anonymizer import PIIAnonymizer
from indexing.indexer import OpenSearchIndexer

logger = logging.getLogger("uc1.scanner")
logging.basicConfig(level=logging.INFO)


class IngestionScanner:
    def __init__(
        self,
        tika_url: Optional[str] = None,
        opensearch_host: Optional[str] = None
    ):
        self.extractor = DocumentExtractor(tika_url=tika_url)
        self.anonymizer = PIIAnonymizer()
        self.indexer = OpenSearchIndexer(host=opensearch_host)

    def scan_and_ingest(self, target_dir: str) -> Dict[str, Any]:
        """Scans a directory recursively and indexes all valid engineering files."""
        if not os.path.exists(target_dir):
            logger.warning(f"Scan path does not exist: {target_dir}")
            return {"scanned": 0, "indexed": 0, "errors": 0}

        scanned = 0
        indexed = 0
        errors = 0
        redacted_total = 0

        logger.info(f"Starting document scan on: {target_dir}")
        self.indexer.ensure_index_and_pipeline()

        for root, _, files in os.walk(target_dir):
            for file in files:
                if file.startswith(".") or file.endswith(".tmp"):
                    continue

                full_path = os.path.join(root, file)
                scanned += 1
                try:
                    with open(full_path, "rb") as f:
                        file_bytes = f.read()

                    # 1. Extraction
                    doc_data = self.extractor.process_file(file_bytes, full_path)

                    # 2. PII Anonymization on extracted text
                    raw_text = doc_data.get("raw_content", "")
                    clean_text, detected_pii = self.anonymizer.process(raw_text)
                    doc_data["raw_content"] = clean_text
                    doc_data["pii_redacted_count"] = len(detected_pii)
                    redacted_total += len(detected_pii)

                    if detected_pii:
                        logger.info(f"Redacted {len(detected_pii)} PII entities in {file}")

                    # 3. Indexing & Vectorization
                    chunks_indexed = self.indexer.index_document(doc_data)
                    if chunks_indexed > 0:
                        indexed += 1
                except Exception as e:
                    logger.error(f"Failed to process file {full_path}: {e}")
                    errors += 1

        summary = {
            "target_dir": target_dir,
            "scanned": scanned,
            "indexed": indexed,
            "errors": errors,
            "pii_redactions": redacted_total,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        logger.info(f"Ingestion scan completed: {summary}")
        return summary


def run_standalone():
    """CLI runner to trigger ingestion on default mounts."""
    samba_eng = os.environ.get("SAMBA_MOUNT_DIR", "/mnt/share/engineering-docs")
    sample_dir = os.environ.get("SAMPLE_DOCS_DIR", "./data/sample_docs")

    scanner = IngestionScanner()
    # Check if sample docs exist; if not, generate them
    if not os.path.exists(sample_dir) or not os.listdir(sample_dir):
        from ingestion.sample_generator import generate_all_samples
        logger.info(f"Generating initial sample documents into {sample_dir}")
        generate_all_samples(sample_dir)

    # Ingest samples
    scanner.scan_and_ingest(sample_dir)

    # Ingest Samba share if mounted
    if os.path.exists(samba_eng):
        scanner.scan_and_ingest(samba_eng)


if __name__ == "__main__":
    run_standalone()
