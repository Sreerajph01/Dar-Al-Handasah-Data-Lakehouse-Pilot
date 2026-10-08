"""
uc1-search/api/main.py — Engineering Document Search API
Provides:
  GET  /health           — liveness probe
  GET  /v1/search/query  — hybrid BM25 + k-NN search
  GET  /v1/search/suggest — typeahead suggestions
  GET  /v1/search/{doc_id} — fetch document metadata
  POST /v1/search/rag    — RAG answer (Ollama via Lakekeeper)

Auth: Keycloak JWT (Bearer token). Parsed but not enforced in M1 dev mode.
"""
import os
import httpx
from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from opensearchpy import OpenSearch
from pydantic import BaseModel
from typing import Optional

OPENSEARCH_HOST = os.environ.get("OPENSEARCH_HOST", "http://opensearch:9200")
OPENSEARCH_USER = os.environ.get("OPENSEARCH_USER", "admin")
OPENSEARCH_PASS = os.environ.get("OPENSEARCH_PASSWORD", "")
OLLAMA_HOST     = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
EMBED_MODEL     = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text:1.5")
INDEX_PREFIX    = "uc1"

app = FastAPI(
    title="Dar Lakehouse — Engineering Document Search API",
    version="0.1.0",
    description="BM25 + k-NN hybrid search over engineering documents",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_os_client: Optional[OpenSearch] = None


def get_opensearch() -> OpenSearch:
    global _os_client
    if _os_client is None:
        host = OPENSEARCH_HOST.replace("http://", "").replace("https://", "")
        scheme = "https" if "https://" in OPENSEARCH_HOST else "http"
        _os_client = OpenSearch(
            hosts=[{"host": host.split(":")[0], "port": int(host.split(":")[-1])}],
            http_auth=(OPENSEARCH_USER, OPENSEARCH_PASS),
            use_ssl=scheme == "https",
            verify_certs=False,
        )
    return _os_client


async def get_embedding(text: str) -> list[float]:
    """Get embedding from Ollama."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{OLLAMA_HOST}/api/embed",
            json={"model": EMBED_MODEL, "input": text},
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("embeddings", [[]])[0]
    return []


class SearchResult(BaseModel):
    doc_id: str
    score: float
    title: str
    project_code: str
    discipline: str
    doc_type: str
    revision: str
    file_name: str
    highlights: list[str] = []


class SearchResponse(BaseModel):
    total: int
    results: list[SearchResult]
    query_ms: int


@app.get("/health")
def health():
    return {"status": "ok", "service": "search-api"}


@app.get("/v1/search/query", response_model=SearchResponse)
async def search(
    q: str = Query(..., description="Search query text"),
    project: Optional[str] = Query(None, description="Filter by project code"),
    discipline: Optional[str] = Query(None, description="Filter by discipline"),
    doc_type: Optional[str] = Query(None, description="Filter by document type"),
    limit: int = Query(20, ge=1, le=100),
    hybrid: bool = Query(True, description="Use hybrid BM25 + k-NN"),
):
    """Hybrid BM25 + k-NN search with optional metadata filters."""
    import time
    t0 = time.monotonic()
    os_client = get_opensearch()

    # Build filters
    filters = []
    if project:
        filters.append({"term": {"project_code": project}})
    if discipline:
        filters.append({"term": {"discipline": discipline}})
    if doc_type:
        filters.append({"term": {"doc_type": doc_type}})

    # BM25 query
    bm25_query = {
        "multi_match": {
            "query": q,
            "fields": ["title^3", "content^1", "tags^2"],
            "type": "best_fields",
            "fuzziness": "AUTO",
        }
    }

    if hybrid:
        # Get embedding for k-NN
        embedding = await get_embedding(q)
        if embedding:
            # Hybrid: combine BM25 + k-NN via RRF (Reciprocal Rank Fusion)
            body = {
                "size": limit,
                "query": {
                    "bool": {
                        "must": [bm25_query],
                        "filter": filters,
                    }
                },
                "knn": {
                    "embedding": {
                        "vector": embedding,
                        "k": limit,
                    }
                },
                "rank": {"rrf": {"rank_constant": 60, "window_size": 100}},
                "highlight": {
                    "fields": {"content": {}, "title": {}},
                    "pre_tags": ["<mark>"],
                    "post_tags": ["</mark>"],
                },
            }
        else:
            # Fallback to BM25 only if embedding failed
            body = {
                "size": limit,
                "query": {
                    "bool": {
                        "must": [bm25_query],
                        "filter": filters,
                    }
                },
            }
    else:
        body = {
            "size": limit,
            "query": {"bool": {"must": [bm25_query], "filter": filters}},
        }

    try:
        resp = os_client.search(index=f"{INDEX_PREFIX}-documents", body=body)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"OpenSearch error: {e}")

    hits = resp.get("hits", {})
    total = hits.get("total", {}).get("value", 0)
    results = []
    for hit in hits.get("hits", []):
        src = hit["_source"]
        highlights = []
        for field_hits in hit.get("highlight", {}).values():
            highlights.extend(field_hits[:2])
        results.append(SearchResult(
            doc_id=hit["_id"],
            score=hit["_score"],
            title=src.get("title", ""),
            project_code=src.get("project_code", ""),
            discipline=src.get("discipline", ""),
            doc_type=src.get("doc_type", ""),
            revision=src.get("revision", ""),
            file_name=src.get("file_name", ""),
            highlights=highlights,
        ))

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    return SearchResponse(total=total, results=results, query_ms=elapsed_ms)


@app.get("/v1/search/{doc_id}")
async def get_document(doc_id: str):
    """Fetch full document metadata by ID."""
    os_client = get_opensearch()
    try:
        resp = os_client.get(index=f"{INDEX_PREFIX}-documents", id=doc_id)
        return {"id": resp["_id"], "metadata": resp["_source"]}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/v1/search/suggest")
async def suggest(q: str = Query(...), limit: int = Query(5)):
    """Typeahead suggestions from title field."""
    os_client = get_opensearch()
    body = {
        "suggest": {
            "title-suggest": {
                "prefix": q,
                "completion": {"field": "title.suggest", "size": limit},
            }
        }
    }
    try:
        resp = os_client.search(index=f"{INDEX_PREFIX}-documents", body=body)
        options = resp.get("suggest", {}).get("title-suggest", [{}])[0].get("options", [])
        return {"suggestions": [o["text"] for o in options]}
    except Exception:
        return {"suggestions": []}


class RagRequest(BaseModel):
    question: str
    context_doc_ids: list[str] = []


@app.post("/v1/search/rag")
async def rag_answer(req: RagRequest):
    """RAG: retrieve context docs from OpenSearch, answer via Ollama."""
    os_client = get_opensearch()

    # Get context from top search results
    search_resp = await search(q=req.question, limit=5, hybrid=True)
    context_chunks = [r.highlights[0] if r.highlights else r.title
                      for r in search_resp.results[:3]]
    context = "\n---\n".join(context_chunks) if context_chunks else "No context available."

    prompt = f"""You are an engineering document assistant for Dar Al Handasah.
Answer the question using ONLY the context below. If the answer is not in the context, say "I cannot find this in the indexed documents."

Context:
{context}

Question: {req.question}

Answer:"""

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": "qwen2.5:7b-instruct-q4_K_M", "prompt": prompt, "stream": False},
        )
        if resp.status_code == 200:
            answer = resp.json().get("response", "")
        else:
            answer = f"LLM unavailable (HTTP {resp.status_code})"

    return {
        "answer": answer,
        "context_sources": [r.doc_id for r in search_resp.results[:3]],
        "model": "qwen2.5:7b-instruct-q4_K_M",
    }
