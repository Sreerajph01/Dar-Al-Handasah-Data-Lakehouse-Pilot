"""
uc1-search/ingestion/sample_generator.py
Generates realistic engineering files and documents for Dar Al-Handasah Pilot.
Produces CAD (.dxf), BIM (.ifc), Technical Reports (.pdf/.txt), Project Correspondence (.eml),
and PII-containing Contracts to demonstrate search, extraction, and PII anonymization.
"""

import os
import io
import time
import logging

logger = logging.getLogger("uc1.sample_gen")
logging.basicConfig(level=logging.INFO)

try:
    import ezdxf
    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False


def create_sample_dxf(output_path: str):
    """Creates a real AutoCAD DXF drawing file."""
    if HAS_EZDXF:
        doc = ezdxf.new("R2010")
        msp = doc.modelspace()
        doc.layers.add("S-COLS", color=1)
        doc.layers.add("S-BEAMS", color=2)
        doc.layers.add("A-WALLS", color=3)
        doc.layers.add("ANNO-TEXT", color=7)

        # Add geometry and text annotations
        msp.add_line((0, 0), (10000, 0), dxfattribs={"layer": "A-WALLS"})
        msp.add_line((10000, 0), (10000, 5000), dxfattribs={"layer": "A-WALLS"})
        msp.add_line((10000, 5000), (0, 5000), dxfattribs={"layer": "A-WALLS"})
        msp.add_line((0, 5000), (0, 0), dxfattribs={"layer": "A-WALLS"})

        msp.add_text("METRO-01 TUNNEL PORTAL EXTENSION - STRUCTURAL GRID A-4", dxfattribs={"layer": "ANNO-TEXT", "height": 250}).set_placement((500, 4500))
        msp.add_text("REINFORCED CONCRETE GRADE C40/50 SPECIFICATION", dxfattribs={"layer": "ANNO-TEXT", "height": 180}).set_placement((500, 4000))
        msp.add_text("MINIMUM COVER TO REINFORCEMENT: 50MM EXPOSED AGGRESSIVE ENVIRONMENT", dxfattribs={"layer": "ANNO-TEXT", "height": 180}).set_placement((500, 3500))
        doc.saveas(output_path)
    else:
        # Minimal valid ASCII DXF template fallback
        content = """0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nSECTION\n2\nTABLES\n0\nTABLE\n2\nLAYER\n0\nLAYER\n2\nS-WALL\n70\n0\n62\n7\n6\nCONTINUOUS\n0\nENDTAB\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n0\nTEXT\n8\nS-WALL\n10\n100.0\n20\n200.0\n30\n0.0\n40\n25.0\n1\nMETRO-01 TUNNEL STRUCTURAL REINFORCEMENT SPECIFICATION\n0\nENDSEC\n0\nEOF\n"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
    logger.info(f"Created sample DXF: {output_path}")


def create_sample_ifc(output_path: str):
    """Creates a valid open BIM IFC model file."""
    ifc_content = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView_V2.0]'),'2;1');
FILE_NAME('BRIDGE-02_Pier_Design.ifc','2026-10-09T12:00:00',('Dar Al-Handasah Bridge Engineering Team'),('Dar Al-Handasah Consultancy'),'IfcOpenShell','Revit 2024','Approved');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCPROJECT('2vXq8R8W1A9vN5Y4H6Z8W0',#2,'BRIDGE-02 Viaduct Substructure',$,$,$,$,$,#3);
#2=IFCOWNERHISTORY(#4,#5,$,.ADDED.,$,$,$,$);
#3=IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-05,#6,$);
#4=IFCPERSONANDORGANIZATION(#7,#8,$);
#5=IFCAPPLICATION(#8,'2024','Dar Design Suite','DarSuite');
#6=IFCAXIS2PLACEMENT3D(#9,#10,#11);
#7=IFCPERSON($,'Al-Mansoor','Tariq',$,$,$,$,$);
#8=IFCORGANIZATION($,'Dar Al-Handasah Consultants',$,$,$);
#9=IFCCARTESIANPOINT((0.,0.,0.));
#10=IFCDIRECTION((0.,0.,1.));
#11=IFCDIRECTION((1.,0.,0.));
#12=IFCSITE('3xN2qW3A5B8xO7Z9K1M3P5',#2,'Bridge Pier Site Zone B',$,$,#6,$,$,.ELEMENT.,$,$,$,$,$);
#13=IFCBUILDING('1aB2cD3eF4gH5iJ6kL7mN8',#2,'Pier Segment P-04 Pierhead',$,$,#6,$,$,.ELEMENT.,$,$,$);
#14=IFCCOLUMN('0zY1xW2vU3tS4rQ5pP6oO7',#2,'RC Column Quad 2200mm Dia',$,$,#6,$,$);
#15=IFCBEAM('9mN8bV7cX6zL5kM4jH3gG2',#2,'Prestressed Box Girder Span 45m',$,$,#6,$,$);
#16=IFCWALL('8uI7yT6rE5wQ4eR3tY2uI1',#2,'Abutment Retaining Wall Grade C50',$,$,#6,$,$);
ENDSEC;
END-10303-21;
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ifc_content)
    logger.info(f"Created sample IFC: {output_path}")


def create_sample_email(output_path: str):
    """Creates a project engineering correspondence email (.eml format)."""
    email_content = """From: tariq.mansoor@dar.demo
To: john.smith@client-metro.gov, sara.hassan@dar.demo
Subject: METRO-01: Urgent Change Request CR-042 - Ground Anchor Load Test Discrepancy
Date: Thu, 08 Oct 2026 14:22:10 +0300
Message-ID: <METRO01-CR042-20261008@dar.demo>
MIME-Version: 1.0
Content-Type: text/plain; charset="utf-8"

Dear Project Director,

During yesterday's continuous load test on the south diaphragm wall ground anchors for METRO-01 Station (Zone 3), geotechnical monitoring instruments registered a 6.2mm settlement deviation beyond the 5.0mm allowable tolerance.

Our Chief Geotechnical Engineer, Dr. Youssef Nader, recommends issuing Change Request CR-042:
1. Increase anchor pre-stress load by 15% across anchors GA-101 through GA-118.
2. Extend pressure grouting depth by 3.5 meters into the sound bedrock stratum.
3. Budget impact is estimated at $85,000 USD, covered under project contingency WBS 1.03.04.

Please find the detailed geotechnical telemetry data in the attached report and confirm formal approval before Friday's scheduled concrete pour.

Sincerely,
Eng. Tariq Al-Mansoor
Senior Project Manager — Dar Al-Handasah Infrastructure & Tunnels Division
Mobile: +971-50-8472910
Email: tariq.mansoor@dar.demo
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(email_content)
    logger.info(f"Created sample Email: {output_path}")


def create_sample_contract_with_pii(output_path: str):
    """Creates a subcontractor agreement containing sensitive PII to demonstrate Presidio redaction."""
    text = """CONFIDENTIAL SUBCONTRACT AGREEMENT
PROJECT CODE: HIGHRISE-05
PROJECT NAME: AL-NOOR COMMERCIAL TOWER (48 FLOORS)

PARTIES TO CONTRACT:
Contractor: Dar Al-Handasah Project Supervision Consultancy
Subcontractor: Apex Façade & Curtain Wall Systems Ltd.

LEAD REPRESENTATIVE & PERSONNEL (CONFIDENTIAL):
Lead Project Engineer: Michael Robert Vance
National Identity / SSN: 482-19-4820
Personal Contact Phone: +44 7911 123456
Private Email: mvance.personal.contact@gmail.com
Banking Details for Wire Transfers:
Bank: First International Commercial Bank
IBAN: GB29NWBK60161331926819
Account Holder: Michael Vance

SCOPE OF WORK:
Subcontractor shall supply and erect double-glazed structural silicone glazed curtain wall panels meeting wind tunnel load test parameters of 3.8 kPa.
Retention percentage: 10%
Warranty period: 10 Years against thermal degradation and water penetration.
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    logger.info(f"Created sample Contract with PII: {output_path}")


def create_sample_spec_doc(output_path: str):
    """Creates a technical specification document."""
    text = """DAR AL-HANDASAH TECHNICAL SPECIFICATION
PROJECT: HOSP-03 — AL-KHALEEJ SPECIALIZED HOSPITAL
DISCIPLINE: STRUCTURAL & FOUNDATION ENGINEERING
DOCUMENT REF: DAR-HOSP03-SPEC-STR-001-REV-C

1. SCOPE AND DESIGN CRITERIA
This specification covers the design, testing, and construction of deep bored cast-in-situ concrete piles supporting the 600-bed hospital superstructure.
Seismic zone design spectral acceleration: Ss = 0.42g, S1 = 0.16g in compliance with IBC 2024 and ACI 318-22.

2. CONCRETE PROPERTIES
- Concrete characteristic compressive cube strength at 28 days: fcu = 50 MPa (C40/50).
- Cement type: Sulfate Resisting Portland Cement (SRPC) Type V.
- Water-cement ratio: Maximum 0.38 by weight.
- Silica Fume content: 7% by weight of cementitious materials.

3. WORK BREAKDOWN STRUCTURE ALLOCATION
- WBS Code: 2.01.03 (Deep Foundation System)
- Approved Subcontractor: Bauer Foundation Specialist Ltd.
- QA/QC Inspection Hold Point: Integrity testing by sonic logging (CSL) on 100% of working piles.
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    logger.info(f"Created sample Specification: {output_path}")


def generate_all_samples(base_dir: str):
    """Generates all engineering files structured by project directories."""
    projects = {
        "METRO-01": os.path.join(base_dir, "METRO-01", "Structural"),
        "BRIDGE-02": os.path.join(base_dir, "BRIDGE-02", "Civil"),
        "HOSP-03": os.path.join(base_dir, "HOSP-03", "Structural"),
        "HIGHRISE-05": os.path.join(base_dir, "HIGHRISE-05", "Contracts"),
        "WTREATING-04": os.path.join(base_dir, "WTREATING-04", "MEP"),
    }

    for path in projects.values():
        os.makedirs(path, exist_ok=True)

    create_sample_dxf(os.path.join(projects["METRO-01"], "METRO-01_Tunnel_Section_RevB.dxf"))
    create_sample_email(os.path.join(projects["METRO-01"], "METRO-01_Change_Request_CR042.eml"))
    create_sample_ifc(os.path.join(projects["BRIDGE-02"], "BRIDGE-02_Pier_Design_BIM.ifc"))
    create_sample_spec_doc(os.path.join(projects["HOSP-03"], "HOSP-03_Foundation_Piling_Spec.txt"))
    create_sample_contract_with_pii(os.path.join(projects["HIGHRISE-05"], "HIGHRISE-05_Façade_Agreement_Confidential.txt"))

    # Add a mock DWG and RVT to test proprietary metadata badge
    with open(os.path.join(projects["METRO-01"], "METRO-01_General_Arrangement.dwg"), "wb") as f:
        f.write(b"AC1032\x00\x00\x00\x00AUTOCAD_2024_BINARY_DATA_METRO01_DAR_AL_HANDASAH")

    with open(os.path.join(projects["BRIDGE-02"], "BRIDGE-02_Full_Bridge_Model.rvt"), "wb") as f:
        f.write(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1AUTODESK_REVIT_2024_COMPOUND_DOCUMENT_DAR")

    logger.info("All sample engineering documents generated successfully.")


if __name__ == "__main__":
    target = os.environ.get("DEMO_DOCS_DIR", "./data/sample_docs")
    generate_all_samples(target)
