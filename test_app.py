# -*- coding: utf-8 -*-
"""
Phase 5: Automated Integration Test Suite for AlphaFinder
Run with: python test_app.py
"""
import sys
import traceback
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

PASS = 0
FAIL = 0
ERRORS = []

def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        ERRORS.append(f"{name}: {detail}")
        try:
            print(f"  [FAIL] {name} - {detail}")
        except UnicodeEncodeError:
            print(f"  [FAIL] {name} - (encoding error in detail)")


def get_auth_headers():
    """Helper: register a temp user and get auth token."""
    client.post('/api/register', json={'username': 'test_auto', 'password': 'test1234'})
    r = client.post('/api/token', data={'username': 'test_auto', 'password': 'test1234'},
                     headers={'Content-Type': 'application/x-www-form-urlencoded'})
    token = r.json().get('access_token', '')
    return {'Authorization': f'Bearer {token}'}


# ============================================================
# Section 1: Page Rendering Tests
# ============================================================
def test_pages():
    print("\n--- 1. Page Rendering ---")
    pages = {
        '/': 'Dashboard',
        '/seasonality': 'Seasonality',
        '/themes': 'Themes',
        '/leaderboard': 'Leaderboard',
        '/review': 'Review (default)',
        '/review?ticker=005930': 'Review (Samsung)',
        '/portfolio': 'Portfolio',
        '/policies': 'Policies',
    }
    for url, name in pages.items():
        r = client.get(url)
        test(f"GET {name}", r.status_code == 200, f"status={r.status_code}")


# ============================================================
# Section 2: SEO Endpoints
# ============================================================
def test_seo():
    print("\n--- 2. SEO ---")
    r = client.get('/sitemap.xml')
    test("Sitemap status", r.status_code == 200)
    test("Sitemap content-type", 'xml' in r.headers.get('content-type', ''), r.headers.get('content-type'))
    test("Sitemap has urlset", '<urlset' in r.text)
    test("Sitemap has 6 URLs", r.text.count('<url>') == 6, f"found {r.text.count('<url>')}")

    r = client.get('/robots.txt')
    test("robots.txt status", r.status_code == 200)
    test("robots.txt has Sitemap", 'Sitemap:' in r.text)
    test("robots.txt disallows /api/", 'Disallow: /api/' in r.text)

    r = client.get('/ads.txt')
    test("ads.txt status", r.status_code == 200)


# ============================================================
# Section 3: Auth Tests
# ============================================================
def test_auth():
    print("\n--- 3. Authentication ---")
    # Register (may already exist from a previous run)
    r = client.post('/api/register', json={'username': 'test_auth_user', 'password': 'pass123'})
    test("Register new user", r.status_code in (200, 400))

    # Duplicate register
    r = client.post('/api/register', json={'username': 'test_auth_user', 'password': 'pass123'})
    test("Duplicate register rejected", r.status_code == 400)

    # Login
    r = client.post('/api/token', data={'username': 'test_auth_user', 'password': 'pass123'},
                     headers={'Content-Type': 'application/x-www-form-urlencoded'})
    test("Login success", r.status_code == 200 and 'access_token' in r.json())

    # Wrong password
    r = client.post('/api/token', data={'username': 'test_auth_user', 'password': 'wrongpass'},
                     headers={'Content-Type': 'application/x-www-form-urlencoded'})
    test("Wrong password rejected", r.status_code == 401)

    # Unauthenticated access
    r = client.get('/api/membership')
    test("Membership w/o auth = 401", r.status_code == 401)

    r = client.get('/api/pnl-card')
    test("PnL card w/o auth = 401", r.status_code == 401)

    r = client.get('/api/alerts')
    test("Alerts w/o auth = 401", r.status_code == 401)


# ============================================================
# Section 4: Community Features (Phase 2)
# ============================================================
def test_community():
    print("\n--- 4. Community (Phase 2) ---")
    headers = get_auth_headers()

    # Comments
    r = client.post('/api/comments/005930', json={'ticker': '005930', 'content': 'Auto test comment'}, headers=headers)
    test("Create comment", r.status_code == 200)
    test("Comment has username", 'username' in r.json())

    r = client.get('/api/comments/005930')
    test("Get comments", r.status_code == 200 and len(r.json()) > 0)

    # Votes
    r = client.post('/api/votes/005930', json={'ticker': '005930', 'vote_type': 'BULL'}, headers=headers)
    test("Cast vote BULL", r.status_code == 200)

    r = client.get('/api/votes/005930')
    data = r.json()
    test("Get votes", r.status_code == 200 and 'bull' in data)
    test("Vote ratios sum to 100", data['bull_ratio'] + data['bear_ratio'] == 100 or data['total'] == 0,
         f"bull={data.get('bull_ratio')}, bear={data.get('bear_ratio')}")

    # Leaderboard
    r = client.get('/api/leaderboard')
    test("Leaderboard API", r.status_code == 200)


# ============================================================
# Section 5: Alert System (Phase 3)
# ============================================================
def test_alerts():
    print("\n--- 5. Alerts (Phase 3) ---")
    headers = get_auth_headers()

    # Create
    r = client.post('/api/alerts', json={'ticker': '005930', 'target_price': 80000, 'condition_type': 'ABOVE'}, headers=headers)
    test("Create alert", r.status_code == 200)
    alert_id = r.json().get('id')

    # Bad condition_type
    r = client.post('/api/alerts', json={'ticker': '005930', 'target_price': 80000, 'condition_type': 'INVALID'}, headers=headers)
    test("Invalid condition rejected", r.status_code == 400)

    # List
    r = client.get('/api/alerts', headers=headers)
    test("List alerts", r.status_code == 200 and len(r.json()) >= 1)

    # Delete
    if alert_id:
        r = client.delete(f'/api/alerts/{alert_id}', headers=headers)
        test("Delete alert", r.status_code == 200)

    # Delete non-existent
    r = client.delete('/api/alerts/99999', headers=headers)
    test("Delete non-existent = 404", r.status_code == 404)


# ============================================================
# Section 6: Monetization (Phase 4)
# ============================================================
def test_monetization():
    print("\n--- 6. Monetization (Phase 4) ---")
    headers = get_auth_headers()

    # Membership
    r = client.get('/api/membership', headers=headers)
    test("Get membership", r.status_code == 200)
    test("Has features dict", 'features' in r.json())

    # Upgrade
    r = client.post('/api/membership/upgrade', headers=headers)
    test("Upgrade to premium", r.status_code == 200 and r.json()['membership'] == 'premium')

    # Verify premium features
    r = client.get('/api/membership', headers=headers)
    test("Premium features enabled", r.json()['features']['alerts'] == True)

    # Downgrade
    r = client.post('/api/membership/downgrade', headers=headers)
    test("Downgrade to basic", r.status_code == 200 and r.json()['membership'] == 'basic')

    # Payment - empty rejected
    r = client.post('/api/payment/confirm', json={})
    test("Payment empty = 400", r.status_code == 400)

    # Payment - valid
    r = client.post('/api/payment/confirm', json={'paymentKey': 'pk_test', 'orderId': 'ORD-1', 'amount': 9900})
    test("Payment valid = 200", r.status_code == 200)

    # OG Image
    r = client.get('/api/og-image/005930')
    test("OG image data", r.status_code == 200 and 'title' in r.json())

    # P&L Card
    r = client.get('/api/pnl-card', headers=headers)
    test("PnL card data", r.status_code == 200 and 'username' in r.json())


# ============================================================
# Section 7: Portfolio CRUD
# ============================================================
def test_portfolio():
    print("\n--- 7. Portfolio ---")
    headers = get_auth_headers()

    r = client.post('/api/portfolio', json={'ticker': '005930', 'target_price': 70000, 'qty': 5}, headers=headers)
    test("Add portfolio item", r.status_code == 200)

    r = client.get('/api/portfolio', headers=headers)
    test("Get portfolio", r.status_code == 200)


# ============================================================
# Run All Tests
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  AlphaFinder Integration Test Suite")
    print("=" * 60)

    try:
        test_pages()
        test_seo()
        test_auth()
        test_community()
        test_alerts()
        test_monetization()
        test_portfolio()
    except Exception as e:
        print(f"\n[CRITICAL ERROR] Test suite crashed: {e}")
        traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"  RESULTS: {PASS} passed, {FAIL} failed, {PASS + FAIL} total")
    print("=" * 60)

    if ERRORS:
        print("\nFailed tests:")
        for e in ERRORS:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("\n  ALL TESTS PASSED!")
        sys.exit(0)
