"""
uc1-search/enrichment/extractor.py
Multi-format document extractor for Dar Al-Handasah Data Lakehouse.
Extracts structured text, technical metadata, and spatial/CAD attributes from:
  - PDF, Office (DOCX, XLSX, PPTX, TXT) via Apache Tika
  - AutoCAD drawings via ezdxf (.dxf) + header fallback (.dwg)
  - BIM models via ifcopenshell (.ifc) + header fallback (.rvt)
  - Emails (.msg via extract_msg, .eml via standard email library)
"""

import os
import io
import re
import hashlib
import logging
from typing import Dict, Any, Optional
from email import policy
from email.parser import BytesParser
import httpx

logger = logging.getLogger("uc1.extractor")
logging.basicConfig(level=logging.INFO)

TIKA_HOST = os.environ.get("TIKA_HOST", "http://dar-tika:9998")

# Try importing specialized CAD/BIM/Email packages with safe fallbacks
try:
    import ezdxf
    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False

try:
    import ifcopenshell
    HAS_IFCOPENSHELL = True
except ImportError:
    HAS_IFCOPENSHELL = False

try:
    import extract_msg
    HAS_EXTRACT_MSG = True
except ImportError:
    HAS_EXTRACT_MSG = False


class DocumentExtractor:
    def __init__(self, tika_url: Optional[str] = None):
        self.tika_url = (tika_url or TIKA_HOST).rstrip("/")

    def compute_hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def infer_metadata_from_path(self, file_path: str) -> Dict[str, str]:
        """Infers project_code, discipline, and document type from directory conventions."""
        norm = file_path.replace("\\", "/").strip("/")
        parts = norm.split("/")
        filename = parts[-1] if parts else ""
        ext = os.path.splitext(filename)[1].lower()

        project_code = "DAR-GEN"
        discipline = "General"
        doc_type = "Document"

        # Regex checks for project patterns: e.g. METRO-01, BRIDGE-02, HOSP-03, HIGHRISE-05
        proj_match = re.search(r"\b([A-Z]{3,8}-\d{2})\b", norm, re.IGNORECASE)
        if proj_match:
            project_code = proj_match.group(1).upper()

        lower_path = norm.lower()
        if "struct" in lower_path or "-s-" in lower_path:
            discipline = "Structural"
        elif "arch" in lower_path or "-a-" in lower_path:
            discipline = "Architectural"
        elif "mep" in lower_path or "mech" in lower_path or "elec" in lower_path or "-m-" in lower_path:
            discipline = "MEP"
        elif "civil" in lower_path or "infra" in lower_path:
            discipline = "Civil"
        elif "contract" in lower_path or "legal" in lower_path:
            discipline = "Contracts"
        elif "pm" in lower_path or "evm" in lower_path or "sched" in lower_path:
            discipline = "Project Management"

        if ext in [".dwg", ".dxf"]:
            doc_type = "CAD Drawing"
        elif ext in [".ifc", ".rvt"]:
            doc_type = "BIM Model"
        elif ext in [".msg", ".eml"]:
            doc_type = "Correspondence"
        elif ext in [".pdf"]:
            doc_type = "Report/Specification"
        elif ext in [".xlsx", ".xls", ".csv"]:
            doc_type = "Spreadsheet/BOQ"
        elif ext in [".docx", ".doc"]:
            doc_type = "Specification/Memo"

        return {
            "project_code": project_code,
            "discipline": discipline,
            "doc_type": doc_type,
            "file_name": filename,
            "extension": ext,
        }

    def extract_tika(self, content_bytes: bytes, filename: str) -> Dict[str, Any]:
        """Extract text and metadata using Apache Tika."""
        extracted_text = ""
        meta = {}
        try:
            with httpx.Client(timeout=30.0) as client:
                # 1. Extract plain text
                tika_text_url = f"{self.tika_url}/tika"
                headers = {
                    "Accept": "text/plain",
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
                resp = client.put(tika_text_url, content=content_bytes, headers=headers)
                if resp.status_code == 200:
                    extracted_text = resp.text.strip()

                # 2. Extract metadata
                meta_url = f"{self.tika_url}/meta"
                meta_resp = client.put(meta_url, content=content_bytes, headers={"Accept": "application/json"})
                if meta_resp.status_code == 200:
                    meta = meta_resp.json()
        except Exception as e:
            logger.warning(f"Tika extraction failed for {filename}: {e}. Falling back to basic text decoding.")
            try:
                extracted_text = content_bytes.decode("utf-8", errors="ignore")
            except Exception:
                extracted_text = ""

        return {"content": extracted_text, "tika_meta": meta}

    def extract_dxf(self, content_bytes: bytes, filename: str) -> Dict[str, Any]:
        """Extract CAD text, layer names, and block definitions via ezdxf."""
        layers = []
        texts = []
        block_names = []

        if HAS_EZDXF:
            try:
                text_stream = io.StringIO(content_bytes.decode("utf-8", errors="ignore"))
                doc = ezdxf.read(text_stream)
                layers = [layer.dxf.name for layer in doc.layers]

                # Extract text and mtext entities
                msp = doc.modelspace()
                for entity in msp:
                    dxftype = entity.dxftype()
                    if dxftype in ("TEXT", "MTEXT"):
                        text_val = entity.dxf.text if dxftype == "TEXT" else entity.text
                        if text_val and text_val.strip():
                            texts.append(text_val.strip())
                    elif dxftype == "INSERT":
                        block_names.append(entity.dxf.name)

                # Blocks
                for block in doc.blocks:
                    block_names.append(block.name)
            except Exception as e:
                logger.warning(f"ezdxf parse error for {filename}: {e}")
                # Simple regex fallback over raw bytes
                raw = content_bytes.decode("ascii", errors="ignore")
                matches = re.findall(r"\b(LAYER|TEXT|MTEXT|LINE|CIRCLE|ARC)\b", raw)
                texts.append("Raw DXF entities: " + ", ".join(set(matches)))
        else:
            raw = content_bytes.decode("ascii", errors="ignore")
            texts.append(f"AutoCAD DXF file ({len(content_bytes)} bytes)")

        combined_content = (
            f"AutoCAD DXF Drawing: {filename}\n"
            f"Layers: {', '.join(layers[:30])}\n"
            f"Blocks: {', '.join(set(block_names[:20]))}\n"
            f"Extracted Text & Annotations:\n" + "\n".join(texts[:100])
        )

        return {
            "content": combined_content,
            "cad_meta": {
                "format": "DXF",
                "layer_count": len(layers),
                "layers": layers[:50],
                "block_count": len(set(block_names)),
                "text_annotations_count": len(texts)
            }
        }

    def extract_ifc(self, content_bytes: bytes, filename: str) -> Dict[str, Any]:
        """Extract BIM model spatial hierarchies, element types, and properties via ifcopenshell."""
        summary = []
        bim_meta = {"format": "IFC"}

        if HAS_IFCOPENSHELL:
            try:
                temp_path = f"/tmp/{filename}"
                with open(temp_path, "wb") as f:
                    f.write(content_bytes)
                ifc_file = ifcopenshell.open(temp_path)
                project = ifc_file.by_type("IfcProject")
                proj_name = project[0].Name if project else "Unnamed IFC Project"
                bim_meta["project_name"] = str(proj_name)

                elements = {}
                for elem_type in ["IfcWall", "IfcSlab", "IfcColumn", "IfcBeam", "IfcDoor", "IfcWindow", "IfcSpace"]:
                    count = len(ifc_file.by_type(elem_type))
                    if count > 0:
                        elements[elem_type] = count
                bim_meta["element_counts"] = elements

                summary.append(f"BIM Model (IFC): {filename}")
                summary.append(f"IFC Project Title: {proj_name}")
                summary.append("Elements in Model:")
                for k, v in elements.items():
                    summary.append(f" - {k}: {v}")
                os.remove(temp_path)
            except Exception as e:
                logger.warning(f"ifcopenshell parse error for {filename}: {e}")
                summary.append(f"BIM Model IFC File: {filename} ({len(content_bytes)} bytes)")
        else:
            # Parse IFC headers from raw text
            raw = content_bytes[:4096].decode("utf-8", errors="ignore")
            summary.append(f"BIM Model (IFC): {filename}")
            if "FILE_DESCRIPTION" in raw:
                summary.append(f"Header snippet:\n{raw[:500]}")

        return {
            "content": "\n".join(summary),
            "bim_meta": bim_meta
        }

    def extract_email(self, content_bytes: bytes, filename: str) -> Dict[str, Any]:
        """Extract subject, sender, recipients, and message body from .msg and .eml files."""
        ext = os.path.splitext(filename)[1].lower()
        subject = ""
        sender = ""
        to = []
        body = ""

        if ext == ".msg" and HAS_EXTRACT_MSG:
            try:
                msg = extract_msg.Message(io.BytesIO(content_bytes))
                subject = str(msg.subject or "")
                sender = str(msg.sender or "")
                to = [str(msg.to or "")]
                body = str(msg.body or "")
            except Exception as e:
                logger.warning(f"extract_msg error: {e}")

        if not body:
            # Process as standard MIME .eml
            try:
                msg = BytesParser(policy=policy.default).parsebytes(content_bytes)
                subject = msg.get("Subject", "")
                sender = msg.get("From", "")
                to = [msg.get("To", "")]
                body_part = msg.get_body(preferencelist=('plain', 'html'))
                if body_part:
                    body = body_part.get_content()
                else:
                    body = msg.get_payload() if isinstance(msg.get_payload(), str) else ""
            except Exception as e:
                logger.warning(f"email parser error: {e}")
                body = content_bytes.decode("utf-8", errors="ignore")

        content = (
            f"Project Email Correspondence: {filename}\n"
            f"Subject: {subject}\n"
            f"From: {sender}\n"
            f"To: {', '.join(to)}\n"
            f"Body:\n{body}"
        )
        return {
            "content": content,
            "email_meta": {
                "subject": subject,
                "from": sender,
                "to": to
            }
        }

    def extract_proprietary_fallback(self, content_bytes: bytes, filename: str) -> Dict[str, Any]:
        """Metadata-only extraction badge for proprietary AutoCAD .dwg and Revit .rvt files."""
        ext = os.path.splitext(filename)[1].lower()
        file_hash = self.compute_hash(content_bytes)
        size_kb = round(len(content_bytes) / 1024, 2)

        content = (
            f"Proprietary Engineering Binary File: {filename}\n"
            f"Format: {ext.upper()} (Metadata-Only Indexing)\n"
            f"File Size: {size_kb} KB\n"
            f"SHA256 Hash: {file_hash}\n"
            f"Notice: Binary content is indexed with structural and project metadata. Full geometry rendering requires native CAD/BIM viewers."
        )

        return {
            "content": content,
            "cad_meta": {
                "is_proprietary_binary": True,
                "extension": ext,
                "size_kb": size_kb,
                "sha256": file_hash
            }
        }

    def process_file(self, content_bytes: bytes, file_path: str) -> Dict[str, Any]:
        """Unified extraction entry point."""
        path_meta = self.infer_metadata_from_path(file_path)
        ext = path_meta["extension"]
        filename = path_meta["file_name"]

        meta: Dict[str, Any] = {}
        content_text = ""

        if ext == ".dxf":
            res = self.extract_dxf(content_bytes, filename)
            content_text = res["content"]
            meta.update(res.get("cad_meta", {}))
        elif ext == ".ifc":
            res = self.extract_ifc(content_bytes, filename)
            content_text = res["content"]
            meta.update(res.get("bim_meta", {}))
        elif ext in [".dwg", ".rvt"]:
            res = self.extract_proprietary_fallback(content_bytes, filename)
            content_text = res["content"]
            meta.update(res.get("cad_meta", {}))
        elif ext in [".msg", ".eml"]:
            res = self.extract_email(content_bytes, filename)
            content_text = res["content"]
            meta.update(res.get("email_meta", {}))
        else:
            # Fallback to Apache Tika for PDFs, DOCX, XLSX, etc.
            res = self.extract_tika(content_bytes, filename)
            content_text = res["content"]
            meta.update(res.get("tika_meta", {}))

        # Dynamic default ACLs based on project & discipline
        allowed_roles = ["dar_admin", "pm_executive"]
        if path_meta["project_code"] != "DAR-GEN":
            allowed_roles.append(f"pm_{path_meta['project_code'].lower()}")
            allowed_roles.append(f"team_{path_meta['project_code'].lower()}")
        else:
            allowed_roles.append("all_staff")
        if path_meta["discipline"]:
            allowed_roles.append(f"eng_{path_meta['discipline'].lower()}")
        if "public" in filename.lower():
            allowed_roles.append("all_staff")
            allowed_roles.append("external_auditor")
        elif "audit" in filename.lower():
            allowed_roles.append("external_auditor")

        is_tier_b = ext in [".dwg", ".rvt"]
        file_tier = "B" if is_tier_b else "A"
        metadata_only = is_tier_b

        if is_tier_b:
            # Metadata-only indexing for proprietary binary files (DWG/RVT)
            content_text = ""

        return {
            "doc_id": hashlib.md5(file_path.encode()).hexdigest(),
            "file_name": filename,
            "file_path": file_path,
            "project_code": path_meta["project_code"],
            "discipline": path_meta["discipline"],
            "doc_type": path_meta["doc_type"],
            "extension": ext,
            "file_tier": file_tier,
            "metadata_only": metadata_only,
            "file_size": len(content_bytes),
            "hash": self.compute_hash(content_bytes),
            "raw_content": content_text,
            "extracted_metadata": meta,
            "allowed_roles": list(set(allowed_roles)),
            "allowed_users": ["admin@dar.demo"]
        }
