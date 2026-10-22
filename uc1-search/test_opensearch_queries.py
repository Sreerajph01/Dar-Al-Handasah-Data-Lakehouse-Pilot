import requests

url = 'http://opensearch:9200/uc1_documents/_search'
auth = ('admin', 'DarLakehouseAdmin123!')

# 1. Raw BM25 Query
bm25_q = {
    'query': {'match': {'content': 'concrete piles'}},
    'size': 2,
    '_source': ['doc_id', 'project_code', 'discipline', 'file_name']
}
r1 = requests.post(url, json=bm25_q, auth=auth)
res1 = r1.json()
print('=== RAW BM25 QUERY RESULT ===')
print(f"Status: {r1.status_code}, Hits: {res1['hits']['total']['value']}")
for h in res1['hits']['hits']:
    print(f"Score: {h['_score']:.4f}, Doc: {h['_source']['doc_id']}, File: {h['_source']['file_name']}")

# 2. Real Vector Embedding from Ollama
emb_r = requests.post('http://ollama:11434/api/embed', json={'model': 'nomic-embed-text:1.5', 'input': 'concrete piles'})
vec = emb_r.json()['embeddings'][0]
print(f"\n=== REAL VECTOR EMBEDDING ===\nDimension: {len(vec)}, First 5 components: {vec[:5]}")

# 3. Raw k-NN Vector Query
knn_q = {
    'query': {'knn': {'content_vector': {'vector': vec, 'k': 2}}},
    'size': 2,
    '_source': ['doc_id', 'project_code', 'discipline', 'file_name']
}
r2 = requests.post(url, json=knn_q, auth=auth)
res2 = r2.json()
print('\n=== RAW k-NN QUERY RESULT ===')
print(f"Status: {r2.status_code}, Hits: {res2['hits']['total']['value']}")
for h in res2['hits']['hits']:
    print(f"Score: {h['_score']:.4f}, Doc: {h['_source']['doc_id']}, File: {h['_source']['file_name']}")

# 4. Hybrid Search Query via Pipeline
hybrid_url = 'http://opensearch:9200/uc1_documents/_search?search_pipeline=uc1_hybrid_pipeline'
hybrid_q = {
    '_source': {'exclude': ['content_vector']},
    'query': {
        'hybrid': {
            'queries': [
                {'match': {'content': {'query': 'concrete piles'}}},
                {'knn': {'content_vector': {'vector': vec, 'k': 2}}}
            ]
        }
    },
    'size': 2
}
r3 = requests.post(hybrid_url, json=hybrid_q, auth=auth)
res3 = r3.json()
print('\n=== HYBRID SEARCH QUERY RESULT (BM25 + k-NN Lucene HNSW) ===')
print(f"Status: {r3.status_code}, Hits: {res3['hits']['total']['value']}")
for h in res3['hits']['hits']:
    print(f"Normalized Score: {h['_score']:.4f}, Doc: {h['_source']['doc_id']}, File: {h['_source']['file_name']}")
