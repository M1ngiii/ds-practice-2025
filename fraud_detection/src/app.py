import sys
import os
import threading

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")

pb_root_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb'))
sys.path.insert(0, pb_root_path)

fraud_detection_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/fraud_detection'))
sys.path.insert(0, fraud_detection_grpc_path)
import fraud_detection_pb2 as fraud_detection
import fraud_detection_pb2_grpc as fraud_detection_grpc

import grpc
from concurrent import futures


class FraudDetectionService(fraud_detection_grpc.FraudDetectionServiceServicer):
    def __init__(self):
        self.vector_clocks = {}
        self.SERVICE_INDEX = 1  # FD = index 1
        self.orders = {}
        self.lock = threading.Lock()

    def merge_clocks(self, local, received):
        return [max(l, r) for l, r in zip(local, received)]

    def update_vc(self, order_id, received):
        with self.lock:
            merged = self.merge_clocks(self.vector_clocks[order_id], list(received))
            merged[self.SERVICE_INDEX] += 1
            self.vector_clocks[order_id] = merged
            return list(merged)

    def InitOrder(self, request, context):
        order_id = request.order_id
        with self.lock:
            self.orders[order_id] = request
            self.vector_clocks[order_id] = list(request.vector_clock)
        print(f"[FD] InitOrder {order_id} | VC={self.vector_clocks[order_id]}")
        return fraud_detection.FraudResponse(is_fraud=False, vector_clock=self.vector_clocks[order_id])

    def CheckUserFraud(self, request, context):
        order_id = request.order_id
        vc = self.update_vc(order_id, request.vector_clock)
        print(f"[FD] Event D (CheckUserFraud) {order_id} | VC={vc}")

        cached = self.orders[order_id]
        if cached.order_amount > 1000:
            return fraud_detection.OrderEventResponse(success=False, reason="High amount flagged as fraud", vector_clock=vc)

        return fraud_detection.OrderEventResponse(success=True, reason="Amount OK", vector_clock=vc)

    def CheckCardFraud(self, request, context):
        order_id = request.order_id
        vc = self.update_vc(order_id, request.vector_clock)
        print(f"[FD] Event E (CheckCardFraud) {order_id} | VC={vc}")

        cached = self.orders[order_id]
        if cached.card_number.startswith("999"):
            return fraud_detection.OrderEventResponse(success=False, reason="Suspicious card prefix", vector_clock=vc)

        return fraud_detection.OrderEventResponse(success=True, reason="Card OK", vector_clock=vc)

    def ClearOrder(self, request, context):
        order_id = request.order_id
        final_vc = list(request.vector_clock)

        with self.lock:
            local_vc = self.vector_clocks.get(order_id, [0, 0, 0])
            if any(local_vc[i] > final_vc[i] for i in range(len(local_vc))):
                print(f"[FD] ClearOrder {order_id} | VC mismatch: local={local_vc} final={final_vc}")
                return fraud_detection.ClearOrderResponse(success=False, error="Local VC exceeds final VC")
            self.orders.pop(order_id, None)
            self.vector_clocks.pop(order_id, None)

        print(f"[FD] ClearOrder {order_id} | cleared | final_VC={final_vc}")
        return fraud_detection.ClearOrderResponse(success=True)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor())
    fraud_detection_grpc.add_FraudDetectionServiceServicer_to_server(
        FraudDetectionService(), server
    )
    server.add_insecure_port("[::]:50051")
    server.start()
    print("[FraudDetection] Server started. Listening on port 50051.")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()
