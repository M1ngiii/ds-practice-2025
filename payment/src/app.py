import sys
import os
import threading
from concurrent import futures

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")

pb_root_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb'))
sys.path.insert(0, pb_root_path)

payment_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/payment'))
sys.path.insert(0, payment_grpc_path)
import payment_pb2 as payment
import payment_pb2_grpc as payment_grpc

import grpc


class PaymentService(payment_grpc.PaymentServiceServicer):
    def __init__(self):
        self.pending = {}  # {order_id: amount}
        self.lock = threading.Lock()

    def Prepare(self, request, context):
        with self.lock:
            self.pending[request.order_id] = request.amount
        print(f"[Payment] Prepare order={request.order_id} amount={request.amount} — voted Yes")
        return payment.PrepareResponse(success=True)

    def Commit(self, request, context):
        with self.lock:
            amount = self.pending.pop(request.order_id, None)
        if amount is not None:
            print(f"[Payment] Commit order={request.order_id} — payment of {amount} executed")
        else:
            print(f"[Payment] Commit order={request.order_id} — no pending transaction found")
        return payment.CommitResponse(success=True)

    def Abort(self, request, context):
        with self.lock:
            self.pending.pop(request.order_id, None)
        print(f"[Payment] Abort order={request.order_id} — transaction discarded")
        return payment.AbortResponse(success=True)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    payment_grpc.add_PaymentServiceServicer_to_server(PaymentService(), server)
    server.add_insecure_port("[::]:50058")
    server.start()
    print("[Payment] Server started. Listening on port 50058.")
    server.wait_for_termination()


if __name__ == '__main__':
    serve()
