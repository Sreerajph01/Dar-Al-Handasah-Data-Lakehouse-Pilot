import requests

session = requests.Session()
login_res = session.post('http://localhost:8088/api/v1/security/login', json={
    'username': 'admin',
    'password': 'admin_password',
    'provider': 'db',
    'refresh': True
})
token = login_res.json().get('access_token')
headers = {'Authorization': f'Bearer {token}'}

dashboards = session.get('http://localhost:8088/api/v1/dashboard/', headers=headers).json()
print("=== SUPERSET DASHBOARDS ===")
for d in dashboards.get('result', []):
    dash_id = d.get('id')
    dash_detail = session.get(f'http://localhost:8088/api/v1/dashboard/{dash_id}', headers=headers).json().get('result', {})
    position_data = dash_detail.get('position_json') or ''
    json_metadata = dash_detail.get('json_metadata') or ''
    has_filter_scopes = 'native_filter_configuration' in json_metadata or 'filter_scopes' in json_metadata or 'FILTER' in position_data
    print(f"ID: {dash_id} | Title: {d.get('dashboard_title')} | Published: {d.get('published')} | Slug: {d.get('slug')} | Native Filter Config: {has_filter_scopes}")

charts = session.get('http://localhost:8088/api/v1/chart/', headers=headers).json()
print("\n=== SUPERSET CHARTS ===")
for c in charts.get('result', []):
    chart_id = c.get('id')
    chart_name = c.get('slice_name')
    viz_type = c.get('viz_type')
    print(f"Chart ID: {chart_id} | Slice Name: {chart_name} | Viz Type: {viz_type}")
    
    # Try fetching chart data
    chart_data_res = session.get(f'http://localhost:8088/api/v1/chart/{chart_id}/data', headers=headers)
    print(f"  Chart GET /data Status: {chart_data_res.status_code}")
