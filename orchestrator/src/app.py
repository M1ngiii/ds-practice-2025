import sys
import os
import time

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

# Per-order events and results for the direct service -> Orchestrator callback
_order_events: dict = {}
_order_results: dict = {}
_results_lock = threading.Lock()


# ── OpenTelemetry setup ───────────────────────────────────────

from opentelemetry import trace, metrics as otel_metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

_OTEL_BASE = os.getenv("OTEL_ENDPOINT", "http://observability:4318")
_resource = Resource(attributes={"service.name": "orchestrator"})

_tracer_provider = TracerProvider(resource=_resource)
_tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{_OTEL_BASE}/v1/traces"))
)
trace.set_tracer_provider(_tracer_provider)

_metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=f"{_OTEL_BASE}/v1/metrics"),
    export_interval_millis=5000
)
_meter_provider = MeterProvider(resource=_resource, metric_readers=[_metric_reader])
otel_metrics.set_meter_provider(_meter_provider)

tracer = trace.get_tracer("orchestrator")
meter  = otel_metrics.get_meter("orchestrator")

# Counters — how many orders ended up approved or rejected
orders_approved = meter.create_counter(
    "bookstore.orders.approved",
    description="Total number of orders approved"
)
orders_rejected = meter.create_counter(
    "bookstore.orders.rejected",
    description="Total number of orders rejected"
)

# UpDownCounters — quantities that can rise and fall
orders_in_flight = meter.create_up_down_counter(
    "bookstore.orders.in_flight",
    description="Orders currently being processed by the orchestrator"
)
orders_enqueued = meter.create_up_down_counter(
    "bookstore.orders.enqueued",
    description="Orders successfully enqueued for execution (cumulative live count)"
)

# Histograms — latency distributions
checkout_histogram = meter.create_histogram(
    "bookstore.checkout.duration_ms",
    unit="ms",
    description="End-to-end checkout latency"
)
init_histogram = meter.create_histogram(
    "bookstore.init_phase.duration_ms",
    unit="ms",
    description="Latency of the parallel InitOrder phase"
)

# Async Gauge — sampled at export time via callback
def _pending_callbacks_callback(options):
    with _results_lock:
        yield otel_metrics.Observation(len(_order_events))

meter.create_observable_gauge(
    "bookstore.orders.pending_callbacks",
    callbacks=[_pending_callbacks_callback],
    description="Orders currently waiting for a result callback from downstream services"
)


# ── Initialization helpers ────────────────────────────────────

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

def enqueue_order(order_id, items):
    with grpc.insecure_channel('order_queue:50054') as channel:
        stub = order_queue_grpc.OrderQueueServiceStub(channel)
        queue_items = [order_queue.OrderItem(name=i['name'], quantity=i['quantity']) for i in items]
        resp = stub.Enqueue(order_queue.EnqueueRequest(order_id=order_id, items=queue_items))
        return resp


# ── Broadcast ClearOrder ──────────────────────────────────────

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
    print(f"[Orch] Broadcast ClearOrder complete | final_VC={list(final_vc)}")


# ── Direct result callback from any service ───────────────────

@app.route('/order_result', methods=['POST'])
def order_result():
    data = request.get_json()
    order_id = data.get('order_id', '')
    with _results_lock:
        if order_id in _order_events:
            _order_results[order_id] = data
            _order_events[order_id].set()
    return {'ack': True}


# ── Checkout endpoint ─────────────────────────────────────────

@app.route('/checkout', methods=['POST'])
def checkout():
    request_data = json.loads(request.data)
    order_id = str(uuid.uuid4())
    initial_vc = [0, 0, 0]

    t_checkout_start = time.time()
    orders_in_flight.add(1)

    with tracer.start_as_current_span("checkout") as span:
        span.set_attribute("order.id", order_id)
        print(f"[Orch] Starting order {order_id}")

        # Register event before init so any early callback is not lost
        event = threading.Event()
        with _results_lock:
            _order_events[order_id] = event
            _order_results[order_id] = {}

        # Init phase (parallel)
        t_init_start = time.time()
        with tracer.start_as_current_span("init_phase") as init_span:
            init_span.set_attribute("order.id", order_id)
            init_threads = [
                threading.Thread(target=init_transaction, args=(request_data, order_id, initial_vc)),
                threading.Thread(target=init_fraud,       args=(request_data, order_id, initial_vc)),
                threading.Thread(target=init_suggestions, args=(request_data, order_id, initial_vc)),
            ]
            for t in init_threads:
                t.start()
            for t in init_threads:
                t.join()
        init_histogram.record((time.time() - t_init_start) * 1000)
        print(f"[Orch] Init complete | order={order_id}")

        # Trigger execution flow via TV
        try:
            with grpc.insecure_channel('transaction_verification:50052') as channel:
                stub = transaction_verification_grpc.TransactionVerificationServiceStub(channel)
                stub.ExecuteFlow(transaction_verification.OrderFlowRequest(
                    order_id=order_id,
                    vector_clock=initial_vc
                ))
        except Exception as e:
            with _results_lock:
                _order_events.pop(order_id, None)
                _order_results.pop(order_id, None)
            orders_in_flight.add(-1)
            orders_rejected.add(1, {"reason": "execute_flow_error"})
            checkout_histogram.record((time.time() - t_checkout_start) * 1000, {"outcome": "rejected"})
            return {'orderId': order_id, 'status': 'Order Rejected', 'reason': str(e)}

        event.wait(timeout=5.0)

        with _results_lock:
            _order_events.pop(order_id, None)
            result = _order_results.pop(order_id, {})

        success = result.get('success', False)
        reason  = result.get('reason', 'No result received')
        books   = result.get('books', [])
        final_vc = result.get('vector_clock', initial_vc)

        print(f"[Orch] ExecuteFlow complete | order={order_id} | success={success} | final_VC={final_vc}")
        span.set_attribute("order.success", success)

        broadcast_clear(order_id, final_vc)

        elapsed_ms = (time.time() - t_checkout_start) * 1000
        orders_in_flight.add(-1)

        if not success:
            orders_rejected.add(1, {"reason": reason[:64]})
            checkout_histogram.record(elapsed_ms, {"outcome": "rejected"})
            return {'orderId': order_id, 'status': 'Order Rejected', 'reason': reason}

        # Enqueue approved order
        try:
            enqueue_resp = enqueue_order(order_id, request_data.get('items', []))
            if not enqueue_resp.success:
                orders_rejected.add(1, {"reason": "enqueue_failed"})
                checkout_histogram.record(elapsed_ms, {"outcome": "rejected"})
                return {
                    'orderId': order_id,
                    'status': 'Order Rejected',
                    'reason': f"Order verification succeeded, but enqueue failed: {enqueue_resp.message}"
                }
        except Exception as e:
            orders_rejected.add(1, {"reason": "enqueue_error"})
            checkout_histogram.record(elapsed_ms, {"outcome": "rejected"})
            return {
                'orderId': order_id,
                'status': 'Order Rejected',
                'reason': f"Order verification succeeded, but enqueue failed: {str(e)}"
            }

        orders_approved.add(1)
        orders_enqueued.add(1)
        checkout_histogram.record(elapsed_ms, {"outcome": "approved"})

        return {
            'orderId': order_id,
            'status': 'Order Approved',
            'suggestedBooks': books
        }


@app.route('/', methods=['GET'])
def index():
    return "Orchestrator is running."


if __name__ == '__main__':
    app.run(host='0.0.0.0', threaded=True)
