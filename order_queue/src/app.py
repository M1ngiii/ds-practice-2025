import sys
import os
import threading
import time
from collections import deque
from concurrent import futures

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")

pb_root_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb'))
sys.path.insert(0, pb_root_path)

order_queue_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/order_queue'))
sys.path.insert(0, order_queue_grpc_path)
import order_queue_pb2 as order_queue
import order_queue_pb2_grpc as order_queue_grpc

import grpc


LEASE_SECONDS = 5


class OrderQueueService(order_queue_grpc.OrderQueueServiceServicer):
    def __init__(self):
        self.lock = threading.Lock()
        self.queue = deque()

        self.leader_id = None
        self.leader_expiry = 0.0

    def _leader_alive(self):
        return self.leader_id is not None and time.time() < self.leader_expiry

    def Enqueue(self, request, context):
        order_id = request.order_id.strip()

        if not order_id:
            return order_queue.EnqueueResponse(
                success=False,
                message="order_id cannot be empty"
            )

        with self.lock:
            self.queue.append(order_queue.QueueItem(order_id=order_id, items=request.items))
            size = len(self.queue)

        print(f"[OrderQueue] Enqueued order {order_id} | size={size}")

        return order_queue.EnqueueResponse(
            success=True,
            message=f"Order {order_id} enqueued successfully"
        )

    def Dequeue(self, request, context):
        executor_id = request.executor_id.strip()

        with self.lock:
            if not self._leader_alive():
                self.leader_id = None
                self.leader_expiry = 0.0

            if not executor_id or executor_id != self.leader_id:
                return order_queue.DequeueResponse(
                    success=False,
                    has_order=False,
                    message="Only the current leader may dequeue"
                )

            if not self.queue:
                return order_queue.DequeueResponse(
                    success=True,
                    has_order=False,
                    message="Queue is empty"
                )

            item = self.queue.popleft()
            size = len(self.queue)

        print(f"[OrderQueue] Leader {executor_id} dequeued order {item.order_id} | size={size}")

        return order_queue.DequeueResponse(
            success=True,
            has_order=True,
            order=item,
            message=f"Order {item.order_id} dequeued successfully"
        )

    def TryBecomeLeader(self, request, context):
        executor_id = request.executor_id.strip()
        if not executor_id:
            return order_queue.LeaderResponse(
                success=False,
                is_leader=False,
                leader_id=self.leader_id or "",
                message="executor_id cannot be empty"
            )

        with self.lock:
            if not self._leader_alive():
                self.leader_id = executor_id
                self.leader_expiry = time.time() + LEASE_SECONDS
                print(f"[OrderQueue] New leader elected: {executor_id}")

            return order_queue.LeaderResponse(
                success=True,
                is_leader=(self.leader_id == executor_id),
                leader_id=self.leader_id or "",
                message="Leadership checked"
            )

    def RenewLeadership(self, request, context):
        executor_id = request.executor_id.strip()

        with self.lock:
            if self._leader_alive() and self.leader_id == executor_id:
                self.leader_expiry = time.time() + LEASE_SECONDS
                return order_queue.LeaderResponse(
                    success=True,
                    is_leader=True,
                    leader_id=self.leader_id,
                    message="Leadership renewed"
                )

            if not self._leader_alive():
                self.leader_id = None
                self.leader_expiry = 0.0

            return order_queue.LeaderResponse(
                success=False,
                is_leader=False,
                leader_id=self.leader_id or "",
                message="Not current leader"
            )

    def GetLeader(self, request, context):
        with self.lock:
            if not self._leader_alive():
                self.leader_id = None
                self.leader_expiry = 0.0
                return order_queue.GetLeaderResponse(
                    has_leader=False,
                    leader_id=""
                )

            return order_queue.GetLeaderResponse(
                has_leader=True,
                leader_id=self.leader_id
            )


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    order_queue_grpc.add_OrderQueueServiceServicer_to_server(
        OrderQueueService(), server
    )
    server.add_insecure_port("[::]:50054")
    server.start()
    print("[OrderQueue] Server started. Listening on port 50054.")
    server.wait_for_termination()


if __name__ == '__main__':
    serve()