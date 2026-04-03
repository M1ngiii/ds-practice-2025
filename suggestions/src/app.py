import sys
import os
import threading
import random

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")

pb_root_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb'))
sys.path.insert(0, pb_root_path)

suggestions_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/suggestions'))
sys.path.insert(0, suggestions_grpc_path)
import suggestions_pb2 as suggestions
import suggestions_pb2_grpc as suggestions_grpc

common_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/common'))
sys.path.insert(0, common_path)
import common_pb2 as common

import grpc
from concurrent import futures

BOOK_POOL = [
    {'book_id': '123', 'title': 'The Best Book', 'author': 'Author 1'},
    {'book_id': '456', 'title': 'The Second Best Book', 'author': 'Author 2'},
    {'book_id': '789', 'title': 'The Third Best Book', 'author': 'Author 3'},
]


class SuggestionsService(suggestions_grpc.SuggestionsServiceServicer):
    def __init__(self):
        self.vector_clocks = {}
        self.SERVICE_INDEX = 2  # SG = index 2
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
        print(f"[SG] InitOrder {order_id} | VC={self.vector_clocks[order_id]}")
        return suggestions.SuggestionsResponse(vector_clock=self.vector_clocks[order_id])

    def GenerateSuggestions(self, request, context):
        order_id = request.order_id
        vc = self.update_vc(order_id, request.vector_clock)
        print(f"[SG] Event F (GenerateSuggestions) {order_id} | VC={vc}")

        picks = random.sample(BOOK_POOL, 2)
        suggested_books = [common.Book(**b) for b in picks]

        return suggestions.OrderEventResponse(success=True, reason="OK", vector_clock=vc, suggested_books=suggested_books)

    def ClearOrder(self, request, context):
        order_id = request.order_id
        final_vc = list(request.vector_clock)

        with self.lock:
            local_vc = self.vector_clocks.get(order_id, [0, 0, 0])
            if any(local_vc[i] > final_vc[i] for i in range(len(local_vc))):
                print(f"[SG] ClearOrder {order_id} | VC mismatch: local={local_vc} final={final_vc}")
                return suggestions.ClearOrderResponse(success=False, error="Local VC exceeds final VC")
            self.orders.pop(order_id, None)
            self.vector_clocks.pop(order_id, None)

        print(f"[SG] ClearOrder {order_id} | cleared | final_VC={final_vc}")
        return suggestions.ClearOrderResponse(success=True)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor())
    suggestions_grpc.add_SuggestionsServiceServicer_to_server(SuggestionsService(), server)
    server.add_insecure_port("[::]:50053")
    server.start()
    print("[Suggestions] Server started. Listening on port 50053.")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()
