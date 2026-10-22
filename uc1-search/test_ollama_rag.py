import requests
import time

prompt = """You are the Dar Al-Handasah Engineering Knowledge Assistant.
Answer the user's technical question based STRICTLY and FACTUALLY on the retrieved engineering document excerpts below.
Extract and state exact engineering parameters, grades, and strengths (e.g. concrete compressive strength fcu in MPa, cement type, water-cement ratio) clearly when specified in the excerpts.
If the excerpts do NOT contain the information requested, you MUST state explicitly:
"Information not found in the retrieved documents."

=== CONTEXT EXCERPTS ===
[Source 1 - HOSP03_Piling_Spec.txt (HOSP-03, Structural)]:
SECTION 2: CONCRETE MATERIALS & MIX SPECIFICATIONS
2.1 Concrete Grade & Characteristic Strength:
- Characteristic compressive cylinder/cube strength at 28 days: fcu = 50 MPa (C40/50).
- Minimum cementitious content: 400 kg/m³.
- Maximum free water/cement ratio: 0.38 by weight.
2.2 Cement & Mineral Admixtures:
- Cement Type: Sulfate Resisting Portland Cement (SRPC) Type V conforming to ASTM C150 or BS EN 197-1 CEM I-SR5.
- Silica Fume: 7% by weight of cementitious materials for chloride attack resistance.

=== QUESTION ===
What is the concrete strength and cement type specified for HOSP-03 piles?

=== ANSWER ===:"""

t0 = time.time()
resp = requests.post(
    "http://ollama:11434/api/generate",
    json={
        "model": "qwen2.5:7b-instruct-q4_K_M",
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 128}
    },
    timeout=60
)
t1 = time.time()
print(f"Elapsed: {t1-t0:.2f}s")
print(resp.json().get("response"))
