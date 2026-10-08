"""
benchmark/locust/locustfile.py
Locust load-test scenarios for the Dar Lakehouse pilot.
Simulates 3 user types:
  - SearchUser: queries the Search API (UC1)
  - AnalyticsUser: queries the Data API (UC2 SQL endpoints)
  - RAGUser: submits NL questions to the NL2SQL and RAG endpoints
"""
from locust import HttpUser, task, between
import random

PROJECTS = ["METRO-01", "BRIDGE-02", "HOSP-03", "WTREATING-04", "HIGHRISE-05"]
SEARCH_TERMS = [
    "metro station structural drawings",
    "foundation design report",
    "MEP specifications",
    "environmental impact assessment",
    "concrete mix design",
    "hospital HVAC plans",
    "bridge load calculations",
]
NL_QUESTIONS = [
    "What is the total budget for METRO-01?",
    "Show me all contracts above 1 million for Bridge project",
    "Which disciplines have the most open RFIs?",
]


class SearchUser(HttpUser):
    """Simulates an engineer searching for engineering documents (UC1)."""
    wait_time = between(1, 5)
    weight = 60   # 60% of virtual users

    @task(5)
    def full_text_search(self):
        q = random.choice(SEARCH_TERMS)
        self.client.get(
            "/v1/search/query",
            params={"q": q, "hybrid": "true", "limit": 20},
            name="/v1/search/query (hybrid)",
        )

    @task(2)
    def filtered_search(self):
        q = random.choice(SEARCH_TERMS)
        proj = random.choice(PROJECTS)
        self.client.get(
            "/v1/search/query",
            params={"q": q, "project": proj, "limit": 10},
            name="/v1/search/query (filtered)",
        )

    @task(1)
    def suggest(self):
        self.client.get(
            "/v1/search/suggest",
            params={"q": "metro", "limit": 5},
            name="/v1/search/suggest",
        )

    @task(1)
    def rag_query(self):
        question = random.choice(SEARCH_TERMS)
        self.client.post(
            "/v1/search/rag",
            json={"question": question},
            name="/v1/search/rag",
        )


class AnalyticsUser(HttpUser):
    """Simulates a manager running self-serve SQL analytics (UC2)."""
    wait_time = between(2, 10)
    weight = 30   # 30% of virtual users

    @task(4)
    def get_project_summary(self):
        proj = random.choice(PROJECTS)
        self.client.get(
            f"/v1/data/projects/{proj}/summary",
            name="/v1/data/projects/{code}/summary",
        )

    @task(2)
    def list_projects(self):
        self.client.get("/v1/data/projects", name="/v1/data/projects")

    @task(1)
    def get_kpis(self):
        self.client.get("/v1/data/kpis/portfolio", name="/v1/data/kpis/portfolio")


class RAGUser(HttpUser):
    """Simulates a power user asking natural-language questions (UC2 NL2SQL)."""
    wait_time = between(5, 20)
    weight = 10   # 10% of virtual users

    @task
    def nl2sql_question(self):
        question = random.choice(NL_QUESTIONS)
        self.client.post(
            "/v1/nl2sql",
            json={"question": question},
            name="/v1/nl2sql",
        )
