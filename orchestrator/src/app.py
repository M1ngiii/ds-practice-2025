import sys
import os

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")

pb_root_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb'))
sys.path.insert(0, pb_root_path)

fraud_detection_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/fraud_detection'))
sys.path.insert(0, fraud_detection_grpc_path)
import fraud_detection_pb2 as fraud_detection
import fraud_detection_pb2_grpc as fraud_detection_grpc

transaction_verification_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/transaction_verification'))
sys.path.insert(0, transaction_verification_grpc_path)
import transaction_verification_pb2 as transaction_verification
import transaction_verification_pb2_grpc as transaction_verification_grpc

suggestions_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/suggestions'))
sys.path.insert(0, suggestions_grpc_path)
import suggestions_pb2 as suggestions
import suggestions_pb2_grpc as suggestions_grpc

order_queue_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/order_queue'))
sys.path.insert(0, order_queue_grpc_path)
import order_queue_pb2 as order_queue
import order_queue_pb2_grpc as order_queue_grpc

import grpc
import uuid
import threading
from flask import Flask, request
from flask_cors import CORS
import json

app = Flask(__name__)
CORS(app, resources={r'/*': {'origins': '*'}})


# ── Initialization helpers ───────────────────────────────────────────────────

def init_transaction(order_data, order_id, vector_clock):
    with grpc.insecure_channel('transaction_verification:50052') as channel:
        stub = transaction_verification_grpc.TransactionVerificationServiceStub(channel)
        items = [
            transaction_verification.Item(name=item.get('name', ''), quantity=item.get('quantity', 0))
            for item in order_data.get('items', [])
        ]
        credit_card = transaction_verification.CreditCard(
            number=order_data.get('creditCard', {}).get('number', ''),
            expiration_date=order_data.get('creditCard', {}).get('expirationDate', ''),
            cvv=order_data.get('creditCard', {}).get('cvv', '')
        )
        stub.InitOrder(transaction_verification.TransactionRequest(
            order_id=order_id,
            vector_clock=vector_clock,
            user_name=order_data.get('user', {}).get('name', ''),
            user_contact=order_data.get('user', {}).get('contact', ''),
            items=items,
            credit_card=credit_card,
            terms_accepted=order_data.get('termsAccepted', False)
        ))

def init_fraud(order_data, order_id, vector_clock):
    card_number = order_data.get('creditCard', {}).get('number', '')
    order_amount = sum(
        item.get('quantity', 0) * item.get('price', 0)
        for item in order_data.get('items', [])
    )
    with grpc.insecure_channel('fraud_detection:50051') as channel:
        stub = fraud_detection_grpc.FraudDetectionServiceStub(channel)
        stub.InitOrder(fraud_detection.FraudRequest(
            order_id=order_id,
            vector_clock=vector_clock,
            card_number=card_number,
            order_amount=order_amount,
            item_names=[item.get('name', '') for item in order_data.get('items', [])]
        ))

def init_suggestions(order_data, order_id, vector_clock):
    with grpc.insecure_channel('suggestions:50053') as channel:
        stub = suggestions_grpc.SuggestionsServiceStub(channel)
        stub.InitOrder(suggestions.SuggestionsRequest(
            order_id=order_id,
            vector_clock=vector_clock,
            item_names=[item.get('name', '') for item in order_data.get('items', [])]
        ))

def enqueue_order(order_id):
    with grpc.insecure_channel('order_queue:50054') as channel:
        stub = order_queue_grpc.OrderQueueServiceStub(channel)
        resp = stub.Enqueue(order_queue.EnqueueRequest(order_id=order_id))
        return resp


# ── Shared execution state ───────────────────────────────────────────────────

class OrderExecution:
    """Holds shared mutable state for one order's execution."""

    def __init__(self, order_id, initial_vc):
        self.order_id = order_id
        self.vector_clock = list(initial_vc)
        self.vc_lock = threading.Lock()

        self.failure = threading.Event()
        self.failure_reason = None

        self.suggested_books = []

        # Gates — set when an event completes (success or failure)
        self.done_a = threading.Event()
        self.done_b = threading.Event()
        self.done_c = threading.Event()
        self.done_d = threading.Event()
        self.done_e = threading.Event()
        self.done_f = threading.Event()

    def get_vc(self):
        with self.vc_lock:
            return list(self.vector_clock)

    def merge_vc(self, received):
        with self.vc_lock:
            self.vector_clock = [max(l, r) for l, r in zip(self.vector_clock, list(received))]
            return list(self.vector_clock)

    def fail(self, reason):
        self.failure_reason = reason
        self.failure.set()
        # Unblock all gates so waiting threads don't hang
        for gate in (self.done_a, self.done_b, self.done_c, self.done_d, self.done_e, self.done_f):
            gate.set()


# ── Per-event runners ────────────────────────────────────────────────────────

def run_event_a(state: OrderExecution):
    """A: TV.VerifyItems — no prerequisites"""
    if state.failure.is_set():
        state.done_a.set()
        return
    try:
        with grpc.insecure_channel('transaction_verification:50052') as ch:
            stub = transaction_verification_grpc.TransactionVerificationServiceStub(ch)
            resp = stub.VerifyItems(transaction_verification.OrderEventRequest(
                order_id=state.order_id, vector_clock=state.get_vc()
            ))
        state.merge_vc(resp.vector_clock)
        print(f"[Orch] Event A done | VC={state.get_vc()} | ok={resp.success}")
        if not resp.success:
            state.fail(resp.reason)
    except Exception as e:
        state.fail(str(e))
    finally:
        state.done_a.set()


def run_event_b(state: OrderExecution):
    """B: TV.CheckUserData — no prerequisites"""
    if state.failure.is_set():
        state.done_b.set()
        return
    try:
        with grpc.insecure_channel('transaction_verification:50052') as ch:
            stub = transaction_verification_grpc.TransactionVerificationServiceStub(ch)
            resp = stub.CheckUserData(transaction_verification.OrderEventRequest(
                order_id=state.order_id, vector_clock=state.get_vc()
            ))
        state.merge_vc(resp.vector_clock)
        print(f"[Orch] Event B done | VC={state.get_vc()} | ok={resp.success}")
        if not resp.success:
            state.fail(resp.reason)
    except Exception as e:
        state.fail(str(e))
    finally:
        state.done_b.set()


def run_event_c(state: OrderExecution):
    """C: TV.CheckCard — depends on A"""
    state.done_a.wait()
    if state.failure.is_set():
        state.done_c.set()
        return
    try:
        with grpc.insecure_channel('transaction_verification:50052') as ch:
            stub = transaction_verification_grpc.TransactionVerificationServiceStub(ch)
            resp = stub.CheckCard(transaction_verification.OrderEventRequest(
                order_id=state.order_id, vector_clock=state.get_vc()
            ))
        state.merge_vc(resp.vector_clock)
        print(f"[Orch] Event C done | VC={state.get_vc()} | ok={resp.success}")
        if not resp.success:
            state.fail(resp.reason)
    except Exception as e:
        state.fail(str(e))
    finally:
        state.done_c.set()


def run_event_d(state: OrderExecution):
    """D: FD.CheckUserFraud — depends on B"""
    state.done_b.wait()
    if state.failure.is_set():
        state.done_d.set()
        return
    try:
        with grpc.insecure_channel('fraud_detection:50051') as ch:
            stub = fraud_detection_grpc.FraudDetectionServiceStub(ch)
            resp = stub.CheckUserFraud(fraud_detection.OrderEventRequest(
                order_id=state.order_id, vector_clock=state.get_vc()
            ))
        state.merge_vc(resp.vector_clock)
        print(f"[Orch] Event D done | VC={state.get_vc()} | ok={resp.success}")
        if not resp.success:
            state.fail(resp.reason)
    except Exception as e:
        state.fail(str(e))
    finally:
        state.done_d.set()


def run_event_e(state: OrderExecution):
    """E: FD.CheckCardFraud — depends on C and D"""
    state.done_c.wait()
    state.done_d.wait()
    if state.failure.is_set():
        state.done_e.set()
        return
    try:
        with grpc.insecure_channel('fraud_detection:50051') as ch:
            stub = fraud_detection_grpc.FraudDetectionServiceStub(ch)
            resp = stub.CheckCardFraud(fraud_detection.OrderEventRequest(
                order_id=state.order_id, vector_clock=state.get_vc()
            ))
        state.merge_vc(resp.vector_clock)
        print(f"[Orch] Event E done | VC={state.get_vc()} | ok={resp.success}")
        if not resp.success:
            state.fail(resp.reason)
    except Exception as e:
        state.fail(str(e))
    finally:
        state.done_e.set()


def run_event_f(state: OrderExecution):
    """F: SG.GenerateSuggestions — depends on E"""
    state.done_e.wait()
    if state.failure.is_set():
        state.done_f.set()
        return
    try:
        with grpc.insecure_channel('suggestions:50053') as ch:
            stub = suggestions_grpc.SuggestionsServiceStub(ch)
            resp = stub.GenerateSuggestions(suggestions.OrderEventRequest(
                order_id=state.order_id, vector_clock=state.get_vc()
            ))
        state.merge_vc(resp.vector_clock)
        state.suggested_books = list(resp.suggested_books)
        print(f"[Orch] Event F done | VC={state.get_vc()} | books={len(state.suggested_books)}")
    except Exception as e:
        state.fail(str(e))
    finally:
        state.done_f.set()


# ── Broadcast ClearOrder ─────────────────────────────────────────────────────

def broadcast_clear(order_id, final_vc):
    def clear(channel_addr, make_stub, make_request):
        try:
            with grpc.insecure_channel(channel_addr) as ch:
                stub = make_stub(ch)
                resp = stub.ClearOrder(make_request(order_id=order_id, vector_clock=final_vc))
                if not resp.success:
                    print(f"[Orch] ClearOrder warning from {channel_addr}: {resp.error}")
        except Exception as e:
            print(f"[Orch] ClearOrder error from {channel_addr}: {e}")

    threads = [
        threading.Thread(target=clear, args=('transaction_verification:50052',
            transaction_verification_grpc.TransactionVerificationServiceStub,
            transaction_verification.ClearOrderRequest)),
        threading.Thread(target=clear, args=('fraud_detection:50051',
            fraud_detection_grpc.FraudDetectionServiceStub,
            fraud_detection.ClearOrderRequest)),
        threading.Thread(target=clear, args=('suggestions:50053',
            suggestions_grpc.SuggestionsServiceStub,
            suggestions.ClearOrderRequest)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"[Orch] Broadcast ClearOrder complete | final_VC={final_vc}")


# ── Checkout endpoint ────────────────────────────────────────────────────────

@app.route('/checkout', methods=['POST'])
def checkout():
    request_data = json.loads(request.data)
    order_id = str(uuid.uuid4())
    initial_vc = [0, 0, 0]

    print(f"[Orch] Starting order {order_id}")

    # ── Init phase (parallel) ──────────────────────────────────────────────
    init_threads = [
        threading.Thread(target=init_transaction, args=(request_data, order_id, initial_vc)),
        threading.Thread(target=init_fraud,       args=(request_data, order_id, initial_vc)),
        threading.Thread(target=init_suggestions, args=(request_data, order_id, initial_vc)),
    ]
    for t in init_threads:
        t.start()
    for t in init_threads:
        t.join()
    print(f"[Orch] Init complete | order={order_id}")

    # ── Execution phase ────────────────────────────────────────────────────
    state = OrderExecution(order_id, initial_vc)

    exec_threads = [
        threading.Thread(target=run_event_a, args=(state,)),
        threading.Thread(target=run_event_b, args=(state,)),
        threading.Thread(target=run_event_c, args=(state,)),
        threading.Thread(target=run_event_d, args=(state,)),
        threading.Thread(target=run_event_e, args=(state,)),
        threading.Thread(target=run_event_f, args=(state,)),
    ]
    for t in exec_threads:
        t.start()
    for t in exec_threads:
        t.join()

    final_vc = state.get_vc()
    print(f"[Orch] Execution complete | final_VC={final_vc}")

    # ── Broadcast clear ────────────────────────────────────────────────────
    broadcast_clear(order_id, final_vc)

    # ── Respond to client ──────────────────────────────────────────────────
    if state.failure.is_set():
        return {
            'orderId': order_id,
            'status': 'Order Rejected',
            'reason': state.failure_reason
        }

    # ── Enqueue approved order ─────────────────────────────────────────────
    try:
        enqueue_resp = enqueue_order(order_id)
        print(f"[Orch] Enqueue result | order={order_id} | success={enqueue_resp.success} | msg={enqueue_resp.message}")

        if not enqueue_resp.success:
            return {
                'orderId': order_id,
                'status': 'Order Rejected',
                'reason': f"Order verification succeeded, but enqueue failed: {enqueue_resp.message}"
            }
    except Exception as e:
        return {
            'orderId': order_id,
            'status': 'Order Rejected',
            'reason': f"Order verification succeeded, but enqueue failed: {str(e)}"
        }

    return {
        'orderId': order_id,
        'status': 'Order Approved',
        'suggestedBooks': [
            {'bookId': b.book_id, 'title': b.title, 'author': b.author}
            for b in state.suggested_books
        ]
    }


@app.route('/', methods=['GET'])
def index():
    return "Orchestrator is running."


if __name__ == '__main__':
    app.run(host='0.0.0.0')
