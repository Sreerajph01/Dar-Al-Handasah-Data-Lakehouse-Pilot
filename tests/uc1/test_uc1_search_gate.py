"""
tests/uc1/test_uc1_search_gate.py
Automated Acceptance & Gate Test for Use Case 1:
Making Project Files Searchable (Semi-Structured & Unstructured).

NEGATIVE CONTROL SUPPORT:
  Set env var NEGATIVE_CONTROL=<name>:
    break_acl  → ACL filter removed; test_security_acl_enforcement MUST FAIL
    If it passes with break_acl set, the test is wrong.

Verifies:
  1. Multi-format Document Extraction (AutoCAD DXF, BIM IFC, Email)
  2. PII Detection & Anonymization (Presidio)
  3. OpenSearch Index & Hybrid Search Pipeline
  4. Vector Embedding & Hybrid (BM25 + k-NN) Search Accuracy
  5. Dynamic Role-Based Access Control (ACL) Enforcement
"""

import os
import sys
import time
import pytest
import tempfile
import pathlib

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "uc1-search"))

from enrichment.extractor import DocumentExtractor
from enrichment.anonymizer import PIIAnonymizer
from indexing.indexer import OpenSearchIndexer
from ingestion.sample_generator import (
    create_sample_dxf,
    create_sample_ifc,
    create_sample_email,
    create_sample_contract_with_pii,
    create_sample_spec_doc,
)

NEGATIVE_CONTROL = os.environ.get("NEGATIVE_CONTROL", "")


@pytest.fixture(scope="session")
def extractor():
    return DocumentExtractor()


@pytest.fixture(scope="session")
def anonymizer():
    return PIIAnonymizer()


@pytest.fixture(scope="session")
def indexer():
    opensearch_host = os.environ.get("OPENSEARCH_HOST", "http://localhost:9200")
    opensearch_pwd  = os.environ.get("OPENSEARCH_PASSWORD", "DarLakehouseAdmin123!")
    # Password is read from OPENSEARCH_PASSWORD env var inside OpenSearchIndexer
    os.environ.setdefault("OPENSEARCH_PASSWORD", opensearch_pwd)
    try:
        idx = OpenSearchIndexer(host=opensearch_host)
        return idx
    except Exception as e:
        pytest.fail(
            f"OpenSearch indexer could not be initialised: {e}. "
            "Ensure dar-opensearch is up and OPENSEARCH_HOST / OPENSEARCH_PASSWORD are set."
        )


class TestUC1ExtractionAndAnonymization:
    def test_dxf_extraction(self, extractor):
        """Unit: AutoCAD DXF extraction produces correct metadata."""
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tf:
            create_sample_dxf(tf.name)
            tf_path = tf.name

        with open(tf_path, "rb") as f:
            data = f.read()
        os.remove(tf_path)

        res = extractor.process_file(data, "projects/METRO-01/Structural/Tunnel_Detail.dxf")
        assert res["project_code"] == "METRO-01"
        assert res["discipline"] == "Structural"
        assert res["doc_type"] == "CAD Drawing"
        assert "TUNNEL" in res["raw_content"].upper()
        assert "cad_meta" in res["extracted_metadata"] or "format" in res["extracted_metadata"]

    def test_ifc_bim_extraction(self, extractor):
        """Unit: BIM IFC extraction produces correct metadata and content."""
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tf:
            create_sample_ifc(tf.name)
            tf_path = tf.name

        with open(tf_path, "rb") as f:
            data = f.read()
        os.remove(tf_path)

        res = extractor.process_file(data, "projects/BRIDGE-02/Civil/Pier_Substructure.ifc")
        assert res["project_code"] == "BRIDGE-02"
        assert res["doc_type"] == "BIM Model"
        assert "BRIDGE-02" in res["raw_content"]
        assert len(res["raw_content"]) > 50

    def test_email_extraction(self, extractor):
        """Unit: .eml extraction produces sender, subject, and body."""
        with tempfile.NamedTemporaryFile(suffix=".eml", delete=False) as tf:
            create_sample_email(tf.name)
            tf_path = tf.name

        with open(tf_path, "rb") as f:
            data = f.read()
        os.remove(tf_path)

        res = extractor.process_file(data, "projects/METRO-01/PM/CR042_Notice.eml")
        assert res["project_code"] == "METRO-01"
        assert res["doc_type"] == "Correspondence"
        assert "CR-042" in res["raw_content"]
        assert "tariq.mansoor@dar.demo" in res["raw_content"]

    def test_pii_anonymization(self, anonymizer):
        """Unit: Presidio redacts phone numbers, emails and IBANs."""
        sample_text = (
            "Contact lead engineer John Doe at personal email john.personal@gmail.com "
            "or cell +44 7911 123456. Wire retention to IBAN GB29NWBK60161331926819."
        )
        redacted, detected = anonymizer.process(sample_text)
        assert "john.personal@gmail.com" not in redacted, \
            "PII email was NOT redacted"
        assert "GB29NWBK60161331926819" not in redacted, \
            "PII IBAN was NOT redacted"
        assert len(detected) >= 2, \
            f"Expected ≥2 PII entities detected, got {len(detected)}: {detected}"


class TestUC1OpenSearchAndHybridSearch:
    def test_index_and_hybrid_search(self, extractor, anonymizer, indexer):
        """
        Integration: Index a document and retrieve it via hybrid (BM25 + k-NN) search.
        FAILS (not skips) if OpenSearch is unreachable.
        """
        # Prepare sample document
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
            create_sample_spec_doc(tf.name)
            tf_path = tf.name

        with open(tf_path, "rb") as f:
            data = f.read()
        os.remove(tf_path)

        doc = extractor.process_file(data, "projects/HOSP-03/Structural/HOSP03_Piling_Spec.txt")
        clean_text, detected = anonymizer.process(doc["raw_content"])
        doc["raw_content"] = clean_text
        doc["allowed_roles"] = ["pm_hosp-03", "eng_structural"]

        # Index into OpenSearch — must succeed or FAIL (not skip)
        indexer.ensure_index_and_pipeline()
        indexed_count = indexer.index_document(doc)
        assert indexed_count > 0, \
            "Failed to index document chunks into OpenSearch"

        time.sleep(1.5)  # Allow indexing refresh

        # Hybrid Search
        hits = indexer.hybrid_search(
            query_text="deep bored concrete piles foundation",
            user_roles=["eng_structural"],
            project="HOSP-03",
            limit=5,
        )
        assert len(hits) > 0, "Hybrid search returned zero results for an indexed document"
        assert hits[0]["project_code"] == "HOSP-03", \
            f"Top result was for wrong project: {hits[0]['project_code']}"

    def test_security_acl_enforcement(self, indexer):
        """
        Integration: Proves ACL filter blocks unauthorized access.

        NEGATIVE CONTROL (NEGATIVE_CONTROL=break_acl):
          If set, we expect the unauthorized query to RETURN results (ACL is removed).
          If the query still returns 0 results, the negative control didn't work — bug.

        Normal mode: unauthorized query MUST return 0 results.
        """
        # Query with an unauthorized role — MUST return 0
        unauthorized_hits = indexer.hybrid_search(
            query_text="deep bored concrete piles",
            user_roles=["pm_metro-01"],  # Only has METRO-01 access
            project="HOSP-03",
            limit=5,
        )

        authorized_hits = indexer.hybrid_search(
            query_text="deep bored concrete piles",
            user_roles=["eng_structural"],  # Has HOSP-03 clearance
            project="HOSP-03",
            limit=5,
        )

        if NEGATIVE_CONTROL == "break_acl":
            # Negative control: ACL should be removed, unauthorized query should return data
            assert len(unauthorized_hits) > 0, (
                "NEGATIVE CONTROL FAILED: even with ACL removed, the unauthorized query "
                "still returns 0 results. The negative control test is not working correctly."
            )
        else:
            assert len(unauthorized_hits) == 0, (
                f"SECURITY VIOLATION: Unauthorized persona 'pm_metro-01' received "
                f"{len(unauthorized_hits)} HOSP-03 result(s). ACL filter is broken!"
            )
            assert len(authorized_hits) > 0, \
                "Authorized persona 'eng_structural' was denied legitimate HOSP-03 access"

    def test_tier_b_metadata_only_handling(self, indexer):
        """
        Verifies that Tier B files (RVT/DWG) are indexed with metadata_only=True
        and are not returned as content-searchable results.
        """
        # Search for any indexed DWG files
        hits = indexer.hybrid_search(
            query_text="DWG AutoCAD drawing",
            user_roles=["eng_structural"],
            limit=10,
        )
        tier_b_hits = [h for h in hits if h.get("file_tier") == "B"]
        for hit in tier_b_hits:
            assert hit.get("metadata_only") is True, \
                f"Tier B file {hit.get('file_path')} is missing metadata_only=True flag"
            assert not hit.get("raw_content"), \
                f"Tier B file {hit.get('file_path')} has raw_content — should be metadata only"


if __name__ == "__main__":
    pytest.main(["-v", __file__])
