#!/usr/bin/env python3
"""
End-to-end test suite.
Run with: python tests/test_orders.py

Requires the full stack to be running:
    docker-compose up --build
"""
import requests
import threading
import time

BASE_URL = "http://localhost:8081"
CHECKOUT_URL = f"{BASE_URL}/checkout"


def make_order(name, card_number, items, price=10):
    return {
        "user": {
            "name": name,
            "contact": f"{name.lower().replace(' ', '.')}@test.com",
        },
        "creditCard": {
            "number": card_number,
            "expirationDate": "12/26",
            "cvv": "123",
        },
        "userComment": "",
        "items": [
            {"name": book, "quantity": qty, "price": price}
            for book, qty in items
        ],
        "billingAddress": {
            "street": "123 Test St",
            "city": "Tartu",
            "state": "TA",
            "zip": "51000",
            "country": "Estonia",
        },
        "shippingMethod": "Standard",
        "giftWrapping": False,
        "termsAccepted": True,
    }


def send_order(order):
    try:
        resp = requests.post(CHECKOUT_URL, json=order, timeout=15)
        return resp.status_code, resp.json()
    except Exception as e:
        return None, {"error": str(e)}


def send_concurrent(orders):
    results = [None] * len(orders)

    def run(idx, payload):
        results[idx] = send_order(payload)

    threads = [threading.Thread(target=run, args=(i, o)) for i, o in enumerate(orders)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# Test 1 — single non-fraudulent order

def test_single_valid_order():
    header("TEST 1: Single non-fraudulent order")

    order = make_order("Alice Smith", "4111111111111111", [("Book A", 1)])
    status, body = send_order(order)

    print(f"  HTTP {status}")
    print(f"  status:       {body.get('status')}")
    print(f"  orderId:      {body.get('orderId', '')[:16]}...")
    print(f"  suggestions:  {[b.get('title') for b in body.get('suggestedBooks', [])]}")

    assert status == 200, f"Expected HTTP 200, got {status}"
    assert body.get("status") == "Order Approved", f"Expected approved: {body}"
    assert body.get("orderId"), "Missing orderId"
    assert isinstance(body.get("suggestedBooks"), list), "Missing suggestedBooks"

    print("  PASS")


# Test 2 — multiple non-conflicting concurrent orders

def test_multiple_non_conflicting():
    header("TEST 2: Multiple non-conflicting concurrent orders")

    orders = [
        make_order("Bob Jones",   "4111111111111111", [("Book A", 1)]),
        make_order("Carol White", "4222222222222222", [("Book B", 1)]),
        make_order("Dave Brown",  "4333333333333333", [("Book C", 1)]),
    ]

    t0 = time.time()
    results = send_concurrent(orders)
    elapsed = time.time() - t0

    print(f"  All 3 orders completed in {elapsed:.2f}s")
    for i, (status, body) in enumerate(results):
        label = body.get("status", "?")
        reason = body.get("reason", "")
        print(f"  Order {i+1}: HTTP {status} | {label}" + (f" | {reason}" if reason else ""))
        assert status == 200
        assert body.get("status") == "Order Approved", f"Order {i+1} rejected: {body}"

    print("  PASS — all 3 approved")


# Test 3 — mixed fraudulent and non-fraudulent orders

def test_mixed_orders():
    header("TEST 3: Mixed fraudulent and non-fraudulent orders")

    orders = [
        make_order("Eve Green",   "4111111111111111", [("Book A", 1)]),          # valid
        make_order("Frank Black", "9991234567890123", [("Book B", 1)]),          # fraud: card prefix 999
        make_order("Grace Lee",   "4444444444444444", [("Book C", 1)], price=1500),  # fraud: amount > 1000
        make_order("Hank Miller", "4555555555555555", [("Book A", 1)]),          # valid
    ]

    expected_statuses = [
        "Order Approved",
        "Order Rejected",
        "Order Rejected",
        "Order Approved",
    ]

    results = send_concurrent(orders)

    for i, ((status, body), expected) in enumerate(zip(results, expected_statuses)):
        actual = body.get("status", "?")
        reason = body.get("reason", "")
        marker = "OK" if actual == expected else "FAIL"
        print(f"  Order {i+1}: {actual:15s}  (expected {expected:15s})  [{marker}]"
              + (f"  reason: {reason}" if reason else ""))
        assert actual == expected, f"Order {i+1}: expected '{expected}', got '{actual}'"

    print("  PASS — fraud correctly detected")


# Test 4 — conflicting orders (same book, stock exhaustion)

def test_conflicting_orders():
    header("TEST 4: Conflicting orders — same book, stock exhaustion")

    print("  Sending 3 orders for Book C qty=4 each (stock=10).")
    print("  All 3 pass verification — stock is not checked there.")
    print("  The executor resolves the conflict via 2PC:")
    print("    order 1: stock 10→6  (commit)")
    print("    order 2: stock 6→2   (commit)")
    print("    order 3: needs 4, only 2 left → DB votes No → Abort")
    print()

    orders = [
        make_order(f"Conflict User {i}", "4111111111111111", [("Book C", 4)])
        for i in range(3)
    ]

    results = send_concurrent(orders)

    approved = 0
    for i, (status, body) in enumerate(results):
        s = body.get("status", "?")
        print(f"  Order {i+1}: HTTP {status} | {s} | id={body.get('orderId','')[:8]}...")
        if s == "Order Approved":
            approved += 1

    assert approved == 3, (
        f"All 3 should pass verification (got {approved}/3). "
        "Stock conflicts are handled asynchronously by the executor."
    )

    print()
    print("  PASS — all 3 passed verification and were enqueued")
    print("  To confirm 2PC abort: docker-compose logs order_executor | grep -E 'Commit|Abort'")


# Test 5 — validation rejections

def test_validation_rejections():
    header("TEST 5: Validation rejections")

    cases = [
        ("Empty items list",   make_order("A", "4111111111111111", [])),
        ("Quantity zero",      make_order("B", "4111111111111111", [("Book A", 0)])),
        ("Bad card number",    make_order("C", "not-a-card",       [("Book A", 1)])),
        ("Terms not accepted", {
            **make_order("D", "4111111111111111", [("Book A", 1)]),
            "termsAccepted": False,
        }),
        ("Missing user name",  {
            **make_order("E", "4111111111111111", [("Book A", 1)]),
            "user": {"name": "", "contact": "e@test.com"},
        }),
    ]

    for label, order in cases:
        _, body = send_order(order)
        actual = body.get("status", "?")
        reason = body.get("reason", "")
        marker = "OK" if actual == "Order Rejected" else "FAIL"
        print(f"  {label:25s}: {actual:15s} [{marker}]  reason: {reason}")
        assert actual == "Order Rejected", f"'{label}' should be rejected, got: {actual}"

    print("  PASS")


def run_all():
    print(f"\nBookstore Distributed System — End-to-End Tests")
    print(f"Target: {CHECKOUT_URL}")

    try:
        r = requests.get(BASE_URL, timeout=5)
        print(f"Orchestrator: HTTP {r.status_code} — online\n")
    except Exception as e:
        print(f"\nERROR: Cannot reach orchestrator at {BASE_URL}")
        print(f"  {e}")
        print("  Make sure the stack is up: docker-compose up --build")
        raise SystemExit(1)

    tests = [
        test_single_valid_order,
        test_multiple_non_conflicting,
        test_mixed_orders,
        test_conflicting_orders,
        test_validation_rejections,
    ]

    passed = failed = 0
    for fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"  Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print(f"{'='*60}\n")
    return failed == 0


if __name__ == "__main__":
    ok = run_all()
    raise SystemExit(0 if ok else 1)
