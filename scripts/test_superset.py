import os
import requests

def test():
    s = requests.Session()
    login_url = "http://superset:8088/api/v1/security/login"
    password = os.environ.get("SUPERSET_ADMIN_PASSWORD", "DarLakehouseAdmin123!")
    r = s.post(login_url, json={"username": "admin", "password": password, "provider": "db"})
    print("Login status:", r.status_code)
    data = r.json()
    token = data.get("access_token")
    print("Token present:", bool(token))
    
    s.headers.update({"Authorization": f"Bearer {token}"})
    csrf_resp = s.get("http://superset:8088/api/v1/security/csrf_token/")
    print("CSRF status:", csrf_resp.status_code, csrf_resp.text)
    csrf_token = csrf_resp.json().get("result")
    s.headers.update({"X-CSRFToken": csrf_token})
    
    dashs = s.get("http://superset:8088/api/v1/dashboard/")
    print("Dashboards:", dashs.status_code, dashs.json())

if __name__ == "__main__":
    test()
