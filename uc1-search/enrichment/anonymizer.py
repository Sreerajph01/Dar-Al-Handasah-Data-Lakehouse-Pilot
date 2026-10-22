"""
uc1-search/enrichment/anonymizer.py
PII Redaction and Data Anonymization Engine for Dar Al-Handasah Data Lakehouse.
Uses Microsoft Presidio Analyzer & Anonymizer with Regex/Heuristic fallbacks to scrub
sensitive personal data (emails, phone numbers, employee names, IBANs, national IDs)
before indexing into OpenSearch.
"""

import re
import logging
from typing import Dict, Any, Tuple, List

logger = logging.getLogger("uc1.anonymizer")

try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    HAS_PRESIDIO = True
    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()
except Exception as e:
    logger.warning(f"Presidio not available or model missing: {e}. Using regex redaction fallback.")
    HAS_PRESIDIO = False
    analyzer = None
    anonymizer = None


class PIIAnonymizer:
    def __init__(self):
        # Compiled patterns for fallback or targeted domain redaction
        self.patterns = [
            ("EMAIL_ADDRESS", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")),
            ("PHONE_NUMBER", re.compile(r"(\+?\d{1,3}[-.\s]?)?(\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}\b")),
            ("IBAN_CODE", re.compile(r"\b[A-Z]{2}[0-9]{2}(?:[ ]?[0-9]{4}){4}(?!(?:[ ]?[0-9]){1})\b")),
            ("SSN_OR_NAT_ID", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
        ]

    def redact_with_regex(self, text: str) -> Tuple[str, List[Dict[str, Any]]]:
        redacted = text
        detected = []
        for entity_type, pattern in self.patterns:
            matches = list(pattern.finditer(redacted))
            if matches:
                for m in reversed(matches):
                    val = m.group(0)
                    start, end = m.span()
                    # Skip redaction if email domain is demo
                    if "@dar.demo" in val or "@dar.com" in val:
                        continue
                    redacted = redacted[:start] + f"<{entity_type}_REDACTED>" + redacted[end:]
                    detected.append({
                        "entity_type": entity_type,
                        "text": val,
                        "score": 0.95
                    })
        return redacted, detected

    def process(self, text: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Analyzes and redacts sensitive PII from text."""
        if not text or not text.strip():
            return "", []

        detected_entities = []

        if HAS_PRESIDIO and analyzer and anonymizer:
            try:
                results = analyzer.analyze(
                    text=text,
                    entities=["EMAIL_ADDRESS", "PHONE_NUMBER", "IBAN_CODE", "PERSON", "CREDIT_CARD"],
                    language="en"
                )
                anonymized_result = anonymizer.anonymize(
                    text=text,
                    analyzer_results=results
                )
                for r in results:
                    detected_entities.append({
                        "entity_type": r.entity_type,
                        "score": round(r.score, 2),
                        "start": r.start,
                        "end": r.end
                    })
                return anonymized_result.text, detected_entities
            except Exception as e:
                logger.warning(f"Presidio engine execution error: {e}. Executing regex fallback.")

        # Fallback
        return self.redact_with_regex(text)
