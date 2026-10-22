"""
infra/airflow/webserver_config.py
Airflow webserver configuration stub for M1.
Keycloak OIDC integration will be added in M5.
"""

AUTH_TYPE = 4          # AUTH_DB (local DB auth for dev/M1)
AUTH_ROLE_ADMIN = 'Admin'
AUTH_ROLE_PUBLIC = 'Viewer'
WTF_CSRF_ENABLED = True
OAUTH_PROVIDERS = []
