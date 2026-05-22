import sys
import os
import time
import uuid
import threading
from concurrent import futures

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")

pb_root_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb'))
sys.path.insert(0, pb_root_path)

order_executor_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/order_executor'))
sys.path.insert(0, order_executor_grpc_path)
import order_executor_pb2 as order_executor
import order_executor_pb2_grpc as order_executor_grpc

order_queue_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/order_queue'))
sys.path.insert(0, order_queue_grpc_path)
import order_queue_pb2 as order_queue
import order_queue_pb2_grpc as order_queue_grpc

books_database_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/books_database'))
sys.path.insert(0, books_database_grpc_path)
import books_database_pb2 as books_db
import books_database_pb2_grpc as books_db_grpc

payment_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/payment'))
sys.path.insert(0, payment_grpc_path)
import payment_pb2 as payment
import payment_pb2_grpc as payment_grpc

import grpc


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
_resource = Resource(attributes={"service.name": "order-executor"})

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

tracer = trace.get_tracer("order-executor")
meter  = otel_metrics.get_meter("order-executor")

# Counters — 2PC outcomes
two_pc_committed = meter.create_counter(
    "bookstore.2pc.committed",
    description="Total number of orders successfully committed via 2PC"
)
two_pc_aborted = meter.create_counter(
    "bookstore.2pc.aborted",
    description="Total number of orders aborted via 2PC (e.g. insufficient stock)"
)

# Histograms — latency distributions
two_pc_histogram = meter.create_histogram(
    "bookstore.2pc.duration_ms",
    unit="ms",
    description="Time to complete the full 2PC execution for one order"
)
election_histogram = meter.create_histogram(
    "bookstore.leader.election_duration_ms",
    unit="ms",
    description="Time spent on a single leader election attempt"
)


class ExecutorService(order_executor_grpc.OrderExecutorServiceServicer):
    def __init__(self, queue_address, db_address, payment_address):
        self.executor_id = str(uuid.uuid4())
        self.queue_address = queue_address
        self.db_address = db_address
        self.payment_address = payment_address

        self.is_leader = False
        self.state_lock = threading.Lock()
        self.running = True

    def Ping(self, request, context):
        with self.state_lock:
            return order_executor.PingResponse(
                alive=True,
                executor_id=self.executor_id,
                is_leader=self.is_leader
            )

    def try_become_leader(self):
        t_start = time.time()
        with tracer.start_as_current_span("leader.election") as span:
            span.set_attribute("executor.id", self.executor_id)
            try:
                with grpc.insecure_channel(self.queue_address) as channel:
                    stub = order_queue_grpc.OrderQueueServiceStub(channel)
                    resp = stub.TryBecomeLeader(
                        order_queue.LeaderRequest(executor_id=self.executor_id),
                        timeout=2.0
                    )
                with self.state_lock:
                    was_leader = self.is_leader
                    self.is_leader = resp.is_leader
                span.set_attribute("executor.is_leader", resp.is_leader)
                if resp.is_leader and not was_leader:
                    print(f"[Executor {self.executor_id}] Became leader")
                elif not resp.is_leader and was_leader:
                    print(f"[Executor {self.executor_id}] Lost leadership to {resp.leader_id}")
                election_histogram.record(
                    (time.time() - t_start) * 1000,
                    {"executor_id": self.executor_id}
                )
                return resp
            except Exception as e:
                print(f"[Executor {self.executor_id}] TryBecomeLeader failed: {e}")
                with self.state_lock:
                    self.is_leader = False
                election_histogram.record(
                    (time.time() - t_start) * 1000,
                    {"executor_id": self.executor_id, "error": "true"}
                )
                return None

    def renew_leadership(self):
        try:
            with grpc.insecure_channel(self.queue_address) as channel:
                stub = order_queue_grpc.OrderQueueServiceStub(channel)
                resp = stub.RenewLeadership(
                    order_queue.LeaderRequest(executor_id=self.executor_id),
                    timeout=2.0
                )
            with self.state_lock:
                was_leader = self.is_leader
                self.is_leader = resp.is_leader
            if was_leader and not resp.is_leader:
                print(f"[Executor {self.executor_id}] Leadership renewal failed")
            return resp
        except Exception as e:
            print(f"[Executor {self.executor_id}] RenewLeadership failed: {e}")
            with self.state_lock:
                self.is_leader = False
            return None

    def dequeue_once(self):
        try:
            with grpc.insecure_channel(self.queue_address) as channel:
                stub = order_queue_grpc.OrderQueueServiceStub(channel)
                return stub.Dequeue(
                    order_queue.DequeueRequest(executor_id=self.executor_id),
                    timeout=2.0
                )
        except Exception as e:
            print(f"[Executor {self.executor_id}] Dequeue failed: {e}")
            return None

    def execute_order(self, order_id, items):
        print(f"[Executor {self.executor_id}] 2PC starting for order {order_id}")
        t_start = time.time()

        with tracer.start_as_current_span("2pc.execute_order") as span:
            span.set_attribute("order.id", order_id)
            span.set_attribute("executor.id", self.executor_id)

            # Pre-read: compute proposed new stock values
            writes = []
            try:
                with grpc.insecure_channel(self.db_address) as channel:
                    stub = books_db_grpc.BooksDatabaseStub(channel)
                    for item in items:
                        resp = stub.Read(books_db.ReadRequest(title=item.name), timeout=2.0)
                        writes.append((item.name, resp.stock - item.quantity))
            except Exception as e:
                print(f"[Executor {self.executor_id}] Pre-read failed, skipping order {order_id}: {e}")
                two_pc_aborted.add(1, {"executor_id": self.executor_id, "reason": "pre_read_failed"})
                two_pc_histogram.record((time.time() - t_start) * 1000, {"outcome": "aborted"})
                span.set_attribute("2pc.outcome", "aborted")
                return

            total_amount = float(sum(item.quantity for item in items))

            # Phase 1: Prepare
            all_yes = True

            try:
                with grpc.insecure_channel(self.db_address) as channel:
                    stub = books_db_grpc.BooksDatabaseStub(channel)
                    for title, new_stock in writes:
                        resp = stub.Prepare(
                            books_db.PrepareRequest(order_id=order_id, title=title, new_stock=new_stock),
                            timeout=2.0
                        )
                        if not resp.success:
                            print(f"[Executor {self.executor_id}] DB voted No for '{title}': {resp.reason}")
                            all_yes = False
                            break
            except Exception as e:
                print(f"[Executor {self.executor_id}] DB Prepare failed: {e}")
                all_yes = False

            if all_yes:
                try:
                    with grpc.insecure_channel(self.payment_address) as channel:
                        stub = payment_grpc.PaymentServiceStub(channel)
                        resp = stub.Prepare(
                            payment.PrepareRequest(order_id=order_id, amount=total_amount),
                            timeout=2.0
                        )
                        if not resp.success:
                            print(f"[Executor {self.executor_id}] Payment voted No: {resp.reason}")
                            all_yes = False
                except Exception as e:
                    print(f"[Executor {self.executor_id}] Payment Prepare failed: {e}")
                    all_yes = False

            # Phase 2: Commit or Abort
            if all_yes:
                print(f"[Executor {self.executor_id}] All voted Yes — committing order {order_id}")
                try:
                    with grpc.insecure_channel(self.db_address) as channel:
                        stub = books_db_grpc.BooksDatabaseStub(channel)
                        stub.Commit(books_db.CommitRequest(order_id=order_id), timeout=2.0)
                except Exception as e:
                    print(f"[Executor {self.executor_id}] DB Commit failed: {e}")
                try:
                    with grpc.insecure_channel(self.payment_address) as channel:
                        stub = payment_grpc.PaymentServiceStub(channel)
                        stub.Commit(payment.CommitRequest(order_id=order_id), timeout=2.0)
                except Exception as e:
                    print(f"[Executor {self.executor_id}] Payment Commit failed: {e}")

                two_pc_committed.add(1, {"executor_id": self.executor_id})
                two_pc_histogram.record((time.time() - t_start) * 1000, {"outcome": "committed"})
                span.set_attribute("2pc.outcome", "committed")
            else:
                print(f"[Executor {self.executor_id}] Aborting order {order_id}")
                try:
                    with grpc.insecure_channel(self.db_address) as channel:
                        stub = books_db_grpc.BooksDatabaseStub(channel)
                        stub.Abort(books_db.AbortRequest(order_id=order_id), timeout=2.0)
                except Exception as e:
                    print(f"[Executor {self.executor_id}] DB Abort failed: {e}")
                try:
                    with grpc.insecure_channel(self.payment_address) as channel:
                        stub = payment_grpc.PaymentServiceStub(channel)
                        stub.Abort(payment.AbortRequest(order_id=order_id), timeout=2.0)
                except Exception as e:
                    print(f"[Executor {self.executor_id}] Payment Abort failed: {e}")

                two_pc_aborted.add(1, {"executor_id": self.executor_id, "reason": "voted_no"})
                two_pc_histogram.record((time.time() - t_start) * 1000, {"outcome": "aborted"})
                span.set_attribute("2pc.outcome", "aborted")

            print(f"[Executor {self.executor_id}] 2PC complete for order {order_id} | committed={all_yes}")

    def election_loop(self):
        while self.running:
            time.sleep(2.0)
            self.try_become_leader()

    def leader_loop(self):
        while self.running:
            time.sleep(0.1)

            with self.state_lock:
                am_leader = self.is_leader

            if not am_leader:
                continue

            renew_resp = self.renew_leadership()
            if not renew_resp or not renew_resp.is_leader:
                continue

            dequeue_resp = self.dequeue_once()
            if dequeue_resp is None:
                continue

            if not dequeue_resp.success:
                print(f"[Executor {self.executor_id}] Dequeue rejected: {dequeue_resp.message}")
                continue

            if not dequeue_resp.has_order:
                continue

            self.execute_order(dequeue_resp.order.order_id, dequeue_resp.order.items)

    def run(self):
        election_thread = threading.Thread(target=self.election_loop, daemon=True)
        leader_thread   = threading.Thread(target=self.leader_loop,   daemon=True)

        election_thread.start()
        leader_thread.start()

        while self.running:
            time.sleep(10)


def serve():
    queue_address   = os.getenv("ORDER_QUEUE_ADDRESS", "order_queue:50054")
    db_address      = os.getenv("DB_PRIMARY_ADDRESS",  "books_database_1:50055")
    payment_address = os.getenv("PAYMENT_ADDRESS",     "payment:50058")

    service = ExecutorService(
        queue_address=queue_address,
        db_address=db_address,
        payment_address=payment_address
    )

    # Async Gauge — sampled at export time, reads live state from the service object
    def _is_leader_callback(options):
        with service.state_lock:
            val = 1 if service.is_leader else 0
        yield otel_metrics.Observation(val, {"executor_id": service.executor_id})

    meter.create_observable_gauge(
        "bookstore.executor.is_leader",
        callbacks=[_is_leader_callback],
        description="1 if this executor instance is currently the leader, 0 otherwise"
    )

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    order_executor_grpc.add_OrderExecutorServiceServicer_to_server(service, server)
    server.add_insecure_port("[::]:50061")
    server.start()

    print(f"[Executor {service.executor_id}] Server started. Listening on port 50061.")
    print(f"[Executor {service.executor_id}] Queue: {queue_address} | DB: {db_address} | Payment: {payment_address}")

    try:
        service.run()
    except KeyboardInterrupt:
        print(f"[Executor {service.executor_id}] Shutting down")
        service.running = False
        server.stop(0)

    server.wait_for_termination()


if __name__ == '__main__':
    serve()
