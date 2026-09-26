"""Unit 4 smoke test for ComplianceTrack.

Exercises the two implemented core functionalities end to end against a real
PostgreSQL database: the authentication / authorisation service and the Control
Register. Run with the app already started on http://127.0.0.1:5000.

    python tests/smoke_test.py
"""
import re
import sys

import requests

BASE = "http://127.0.0.1:5000"
PASSWORD = "ChangeMe#2026"
results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition), detail))
    print(f"  {'PASS' if condition else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def csrf(session, url):
    html = session.get(url).text
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else None


def login(session, username, password=PASSWORD):
    token = csrf(session, f"{BASE}/login")
    return session.post(f"{BASE}/login",
                        data={"username": username, "password": password,
                              "csrf_token": token},
                        allow_redirects=False)


def main():
    print("\nAuthentication and authorisation")
    s = requests.Session()

    r = s.get(f"{BASE}/controls/", allow_redirects=False)
    check("anonymous request to a protected page is redirected to sign in",
          r.status_code == 302 and "/login" in r.headers.get("Location", ""),
          f"HTTP {r.status_code}")

    r = login(s, "a.rashid", "wrong-password")
    check("wrong password is rejected", r.status_code == 401, f"HTTP {r.status_code}")

    r = login(s, "no.such.user")
    check("unknown username is rejected the same way", r.status_code == 401,
          f"HTTP {r.status_code}")

    r = login(s, "a.rashid")
    check("valid credentials establish a session",
          r.status_code == 302, f"HTTP {r.status_code}")

    body = s.get(f"{BASE}/").text
    check("dashboard greets the signed-in user", "Aisha Al-Rashid" in body)
    check("dashboard states the no-certification boundary",
          "does not certify compliance" in body)

    print("\nControl Register")
    body = s.get(f"{BASE}/controls/?tier=all").text
    check("register lists controls", "1-1-1" in body)

    body = s.get(f"{BASE}/controls/?tier=in_scope").text
    m = re.search(r"([\d,]+) records? match", body)
    check("tracked scope reports 56 controls", m and m.group(1) == "56",
          m.group(1) if m else "not found")

    body = s.get(f"{BASE}/controls/?tier=catalog_only").text
    m = re.search(r"([\d,]+) records? match", body)
    check("catalogue scope reports 52 controls", m and m.group(1) == "52",
          m.group(1) if m else "not found")
    check("catalogue entries are labelled as not assessed",
          "not tracked, evidenced or assessed" in body)

    body = s.get(f"{BASE}/controls/?q=cryptography&tier=all").text
    check("free-text search returns matches", "2-8-" in body)

    body = s.get(f"{BASE}/controls/?q=%27%20OR%201%3D1%20--&tier=all").text
    check("SQL metacharacters in search are treated as data",
          "No controls match that filter" in body)

    print("\nControl Register: status workflow")
    detail = s.get(f"{BASE}/controls/3").text
    check("control detail renders the ECC requirement text",
          "ctrl-text" in detail and "1-1-3" in detail)

    token = csrf(s, f"{BASE}/controls/3")
    r = s.post(f"{BASE}/controls/3/status",
               data={"status": "Implemented", "csrf_token": token})
    check("Implemented is refused while no approved evidence exists",
          "cannot be marked Implemented" in r.text, "design rule enforced")

    token = csrf(s, f"{BASE}/controls/3")
    r = s.post(f"{BASE}/controls/3/status",
               data={"status": "Partially Implemented", "csrf_token": token})
    check("a permitted status change is accepted",
          "moved from" in r.text)
    check("the change is written to the audit trail",
          "STATUS_CHANGE" in r.text)

    token = csrf(s, f"{BASE}/controls/3")
    r = s.post(f"{BASE}/controls/3/status",
               data={"status": "Nonsense", "csrf_token": token})
    check("an invalid status value is refused",
          "not a valid implementation status" in r.text)

    print("\nRole-based access control")
    m = requests.Session()
    login(m, "f.qahtani")                     # Management: read-only
    body = m.get(f"{BASE}/controls/3").text
    check("read-only role can view a control", "1-1-3" in body)
    check("read-only role is not offered the update form",
          "Update implementation status" not in body)

    r = m.post(f"{BASE}/controls/3/status",
               data={"status": "Not Implemented", "csrf_token": csrf(m, f"{BASE}/controls/3")})
    check("read-only role is refused the update even when posted directly",
          r.status_code == 403, f"HTTP {r.status_code}")

    r = m.post(f"{BASE}/controls/3/status", data={"status": "Not Implemented"})
    check("a request without a CSRF token is rejected",
          r.status_code == 400, f"HTTP {r.status_code}")

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} checks passed\n")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
