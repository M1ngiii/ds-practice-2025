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

import grpc


class ExecutorService(order_executor_grpc.OrderExecutorServiceServicer):
    def __init__(self, queue_address):
        self.executor_id = str(uuid.uuid4())
        self.queue_address = queue_address

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

            if resp.is_leader and not was_leader:
                print(f"[Executor {self.executor_id}] Became leader")
            elif not resp.is_leader and was_leader:
                print(f"[Executor {self.executor_id}] Lost leadership to {resp.leader_id}")

            return resp

        except Exception as e:
            print(f"[Executor {self.executor_id}] TryBecomeLeader failed: {e}")
            with self.state_lock:
                self.is_leader = False
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

    def execute_order(self, order_id):
        print(f"[Executor {self.executor_id}] Starting execution of order {order_id}")
        time.sleep(1)  # simulate work
        print(f"[Executor {self.executor_id}] Finished execution of order {order_id}")

    def election_loop(self):
        while self.running:
            time.sleep(2.0)
            self.try_become_leader()

    def leader_loop(self):
        while self.running:
            time.sleep(1.0)

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

            self.execute_order(dequeue_resp.order.order_id)

    def run(self):
        election_thread = threading.Thread(target=self.election_loop, daemon=True)
        leader_thread = threading.Thread(target=self.leader_loop, daemon=True)

        election_thread.start()
        leader_thread.start()

        while self.running:
            time.sleep(10)


def serve():
    queue_address = os.getenv("ORDER_QUEUE_ADDRESS", "order_queue:50054")

    service = ExecutorService(queue_address=queue_address)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    order_executor_grpc.add_OrderExecutorServiceServicer_to_server(service, server)
    server.add_insecure_port("[::]:50061")
    server.start()

    print(f"[Executor {service.executor_id}] Server started. Listening on port 50061.")
    print(f"[Executor {service.executor_id}] Queue address: {queue_address}")

    try:
        service.run()
    except KeyboardInterrupt:
        print(f"[Executor {service.executor_id}] Shutting down")
        service.running = False
        server.stop(0)

    server.wait_for_termination()


if __name__ == '__main__':
    serve()