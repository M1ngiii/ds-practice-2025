import sys
import os
import threading

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.
FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")

pb_root_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb'))
sys.path.insert(0, pb_root_path)

fraud_detection_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/fraud_detection'))
sys.path.insert(0, fraud_detection_grpc_path)
import fraud_detection_pb2 as fraud_detection
import fraud_detection_pb2_grpc as fraud_detection_grpc

suggestions_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/suggestions'))
sys.path.insert(0, suggestions_grpc_path)
import suggestions_pb2 as suggestions
import suggestions_pb2_grpc as suggestions_grpc

import grpc
from concurrent import futures

class FraudDetectionService(fraud_detection_grpc.FraudDetectionServiceServicer):
    def __init__(self):
        self.vector_clocks = {}
        self.SERVICE_INDEX = 1  # FD = index 1
        self.orders = {}
        self.lock = threading.Lock()
        self.results_lock = threading.Lock()

    def merge_clocks(self, local, received):
        return [max(l, r) for l, r in zip(local, received)]

    def InitOrder(self, request, context):
        order_id = request.order_id

        self.orders[order_id] = request
        self.vector_clocks[order_id] = list(request.vector_clock)

        print(f"[FD] Init order {order_id} | VC={self.vector_clocks[order_id]}")

        return fraud_detection.FraudResponse(
            is_fraud=False,
            vector_clock=self.vector_clocks[order_id]
        )
    
    def checkFraud(self, request, context):
        order_id = request.order_id
        incoming_vc = list(request.vector_clock)

        print(f"[FD] Execute order {order_id} | VC={incoming_vc}")

        # Merge clocks
        self.vector_clocks[order_id] = self.merge_clocks(
            self.vector_clocks.get(order_id, incoming_vc),
            incoming_vc
        )

        # Use cached request from initialization phase
        request = self.orders[order_id]

        results = {}

        # Event E
        self.checkUserFraudEvent(request, results)

        if "e" not in results or not results["e"][0]:
            return fraud_detection.FraudResponse(
                is_fraud=True,
                vector_clock=self.vector_clocks[order_id]
            )

        # Event F depends on E
        self.checkCardFraudEvent(request, results)

        if "f" not in results or not results["f"][0]:
            return fraud_detection.FraudResponse(
                is_fraud=True,
                vector_clock=self.vector_clocks[order_id]
            )

        # CALL SUGGESTIONS
        vc = list(self.vector_clocks[order_id])

        with grpc.insecure_channel('suggestions:50053') as channel:
            stub = suggestions_grpc.SuggestionsServiceStub(channel)

            sg_response = stub.getSuggestions(
                suggestions.SuggestionsRequest(
                    order_id=order_id,
                    vector_clock=vc,
                    item_names=list(request.item_names)
                )
            )

        # Merge/update vector clock after Suggestions
        self.vector_clocks[order_id] = self.merge_clocks(
            self.vector_clocks[order_id],
            list(sg_response.vector_clock)
        )

        return fraud_detection.FraudResponse(
            is_fraud=False,
            vector_clock=self.vector_clocks[order_id],
            suggested_books=sg_response.suggested_books
        )

    def checkUserFraudEvent(self, request, results):
        order_id = request.order_id
        vc = self.vector_clocks[order_id]

        print(f"[FD] Event E started | VC={vc}")

        order_amount = request.order_amount

        if order_amount > 1000:
            with self.results_lock:
                results["e"] = (False, "High amount flagged as fraud")
            return

        with self.lock:
            vc[self.SERVICE_INDEX] += 1

        print(f"[FD] Event E finished | VC={vc}")

        with self.results_lock:
            results["e"] = (True, "Amount OK")

    def checkCardFraudEvent(self, request, results):
        order_id = request.order_id
        vc = self.vector_clocks[order_id]

        print(f"[FD] Event F started | VC={vc}")

        card_number = request.card_number

        if card_number.startswith("999"):
            with self.results_lock:
                results["f"] = (False, "Suspicious card prefix")
            return

        with self.lock:
            vc[self.SERVICE_INDEX] += 1

        print(f"[FD] Event F finished | VC={vc}")

        with self.results_lock:
            results["f"] = (True, "Card OK")

def serve():
    server = grpc.server(futures.ThreadPoolExecutor())
    fraud_detection_grpc.add_FraudDetectionServiceServicer_to_server(
        FraudDetectionService(), server
    )
    port = "50051"
    server.add_insecure_port("[::]:" + port)
    server.start()
    print("[FraudDetection] Server started. Listening on port 50051.")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()
