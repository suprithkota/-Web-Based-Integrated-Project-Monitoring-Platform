import re
import sys
import requests

BASE_URL = "http://127.0.0.1:5000"

def get_csrf_token(session, url):
    resp = session.get(url)
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch {url}: {resp.status_code}")
    match = re.search(r'name=["\']csrf_token["\']\s+value=["\']([^"\']+)["\']', resp.text)
    if match:
        return match.group(1)
    match2 = re.search(r'content=["\']([^"\']+)["\']\s+name=["\']csrf-token["\']', resp.text)
    if match2:
        return match2.group(1)
    # Also check meta name="csrf-token" content="..."
    match3 = re.search(r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']', resp.text)
    if match3:
        return match3.group(1)
    return None

def login(session, username, password):
    login_url = f"{BASE_URL}/login"
    token = get_csrf_token(session, login_url)
    data = {
        'username': username,
        'password': password
    }
    if token:
        data['csrf_token'] = token
    resp = session.post(login_url, data=data, allow_redirects=True)
    if resp.status_code != 200 or "/login" in resp.url:
        print(f"FAILED LOGIN for {username}: status={resp.status_code}, url={resp.url}")
        return False
    return True

def test_endpoints():
    errors = []
    print("Testing Public Routes...")
    public_session = requests.Session()
    public_routes = [
        ('/login', 200),
        ('/register', 200),
        ('/forgot-password', 200),
        ('/resend-verification', 200),
        ('/static/css/style.css', 200),
        ('/static/js/app.js', 200),
        ('/static/js/dashboard.js', 200),
        ('/non-existent-page-xyz', 404),
    ]
    for path, expected in public_routes:
        url = f"{BASE_URL}{path}"
        try:
            r = public_session.get(url)
            if r.status_code != expected:
                errors.append(f"Public route {path}: expected {expected}, got {r.status_code}")
            else:
                print(f"  [OK] {path} -> {r.status_code}")
        except Exception as e:
            errors.append(f"Public route {path} exception: {e}")

    print("\nTesting Officer Authenticated Routes...")
    officer_session = requests.Session()
    if not login(officer_session, 'officer', 'officer123'):
        errors.append("Failed to authenticate as officer")
    else:
        officer_routes = [
            ('/dashboard', 200),
            ('/projects', 200),
            ('/projects/1', 200),
            ('/alerts', 200),
            ('/analytics', 200),
            ('/simulator', 200),
            ('/assistant', 200),
            ('/map', 200),
            ('/api/dashboard', 200),
            ('/api/projects', 200),
            ('/api/projects/1', 200),
            ('/api/risk/1', 200),
            ('/api/alerts', 200),
            ('/api/map-data', 200),
            ('/api/ml/models', 200),
            ('/api/ml/comparison', 200),
            ('/api/ml/explanation/1', 200),
            ('/api/ml/anomaly/1', 200),
            ('/api/ml/cluster/1', 200),
        ]
        for path, expected in officer_routes:
            url = f"{BASE_URL}{path}"
            try:
                r = officer_session.get(url)
                if r.status_code != expected:
                    errors.append(f"Officer route {path}: expected {expected}, got {r.status_code}")
                else:
                    print(f"  [OK] {path} -> {r.status_code}")
            except Exception as e:
                errors.append(f"Officer route {path} exception: {e}")

    print("\nTesting Admin Authenticated Routes...")
    admin_session = requests.Session()
    if not login(admin_session, 'admin', 'admin123'):
        errors.append("Failed to authenticate as admin")
    else:
        admin_routes = [
            ('/admin/users', 200),
            ('/admin/audit-logs', 200),
            ('/admin/settings', 200),
            ('/data-import', 200),
        ]
        for path, expected in admin_routes:
            url = f"{BASE_URL}{path}"
            try:
                r = admin_session.get(url)
                if r.status_code != expected:
                    errors.append(f"Admin route {path}: expected {expected}, got {r.status_code}")
                else:
                    print(f"  [OK] {path} -> {r.status_code}")
            except Exception as e:
                errors.append(f"Admin route {path} exception: {e}")

    print("\n" + "="*50)
    if errors:
        print(f"FAILED: {len(errors)} error(s) found:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("ALL ROUTES AND ENDPOINTS TESTED SUCCESSFULLY WITH ZERO ERRORS!")
        print("="*50)

if __name__ == '__main__':
    test_endpoints()
