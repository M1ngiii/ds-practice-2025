"""
Locust load test

Run: locust -f tests/locustfile.py --host http://localhost:8081

Then open http://localhost:8089 for locust

User types:
  ValidOrderUser      (70%) - normal orders
  FraudulentOrderUser (20%) - fraudulent orders
  ConflictOrderUser   (10%) - races for the same book
"""
import random
from locust import HttpUser, task, between


VALID_CARDS = [
    "4111111111111111",
    "4222222222222222",
    "4333333333333333",
    "4444444444444444",
    "5500005555555559",
]

FRAUD_CARDS = [
    "9991234567890123",
    "9990000000000000",
    "9999999999999999",
]

BOOKS = ["Book A", "Book B", "Book C"]


def _payload(card, items, price=10):
    return {
        "user": {"name": "Load Test User", "contact": "loadtest@example.com"},
        "creditCard": {
            "number": card,
            "expirationDate": "12/26",
            "cvv": "123",
        },
        "userComment": "",
        "items": [
            {"name": book, "quantity": qty, "price": price}
            for book, qty in items
        ],
        "billingAddress": {
            "street": "1 Locust Ave",
            "city": "Tartu",
            "state": "TA",
            "zip": "51000",
            "country": "Estonia",
        },
        "shippingMethod": "Standard",
        "giftWrapping": False,
        "termsAccepted": True,
    }


class ValidOrderUser(HttpUser):
    """Regular user placing one book at a time."""
    weight = 7
    wait_time = between(1, 3)

    @task
    def place_order(self):
        book = random.choice(BOOKS)
        card = random.choice(VALID_CARDS)
        payload = _payload(card, [(book, 1)])

        with self.client.post("/checkout", json=payload, catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
                return
            body = resp.json()
            if body.get("status") == "Order Approved":
                resp.success()
            else:
                resp.failure(f"Unexpected rejection: {body.get('reason', '?')}")


class FraudulentOrderUser(HttpUser):
    """Fraudulent user, expects rejection."""
    weight = 2
    wait_time = between(1, 4)

    @task(2)
    def fraud_card(self):
        # card prefix 999, caught by Event E
        card = random.choice(FRAUD_CARDS)
        payload = _payload(card, [("Book A", 1)])

        with self.client.post("/checkout", json=payload, catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
                return
            body = resp.json()
            if body.get("status") == "Order Rejected":
                resp.success()
            else:
                resp.failure(f"Fraud not detected (card): {body}")

    @task(1)
    def fraud_amount(self):
        # amount > 1000, caught by Event D
        card = random.choice(VALID_CARDS)
        payload = _payload(card, [("Book B", 1)], price=1500)

        with self.client.post("/checkout", json=payload, catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
                return
            body = resp.json()
            if body.get("status") == "Order Rejected":
                resp.success()
            else:
                resp.failure(f"Fraud not detected (amount): {body}")


class ConflictOrderUser(HttpUser):
    """Multiple users racing for the same book, tests 2PC stock contention."""
    weight = 1
    wait_time = between(0.5, 2)

    @task
    def buy_contested_book(self):
        card = random.choice(VALID_CARDS)
        payload = _payload(card, [("Book C", 3)])

        with self.client.post("/checkout", json=payload, catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
                return
            # verification always passes, 2PC handles the actual stock conflict
            body = resp.json()
            if body.get("status") in ("Order Approved", "Order Rejected"):
                resp.success()
            else:
                resp.failure(f"Unexpected response: {body}")
