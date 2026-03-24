import sys
import os
import threading

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.
FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")

pb_root_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb'))
sys.path.insert(0, pb_root_path)

suggestions_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/suggestions'))
sys.path.insert(0, suggestions_grpc_path)
import suggestions_pb2 as suggestions
import suggestions_pb2_grpc as suggestions_grpc

common_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/common'))
sys.path.insert(0, common_grpc_path)
import common_pb2 as common
import common_pb2_grpc as common_grpc


import grpc
from concurrent import futures
import random

BOOK_POOL = [
    {'book_id': '123', 'title': 'The Best Book', 'author': 'Author 1'},
    {'book_id': '456', 'title': 'The Second Best Book', 'author': 'Author 2'},
    {'book_id': '789', 'title': 'The Third Best Book', 'author': 'Author 3'}
]


class SuggestionsService(suggestions_grpc.SuggestionsServiceServicer):
    def __init__(self):
        self.vector_clocks = {}
        self.SERVICE_INDEX = 2  # Suggestions = index 2
        self.orders = {}
        self.lock = threading.Lock()

    def merge_clocks(self, local, received):
        return [max(l, r) for l, r in zip(local, received)]
    
    def InitOrder(self, request, context):
        order_id = request.order_id

        self.orders[order_id] = request
        self.vector_clocks[order_id] = list(request.vector_clock)

        print(f"[Suggestions] Init order {order_id} | VC={self.vector_clocks[order_id]}")

        return suggestions.SuggestionsResponse(
            vector_clock=self.vector_clocks[order_id]
        )

    def getSuggestions(self, request, context):
        order_id = request.order_id
        incoming_vc = list(request.vector_clock)

        print(f"[Suggestions] Execute order {order_id} | VC={incoming_vc}")

        # Merge clocks
        self.vector_clocks[order_id] = self.merge_clocks(
            self.vector_clocks.get(order_id, incoming_vc),
            incoming_vc
        )

        # Use cached request from initialization phase
        request = self.orders[order_id]

        # Call Event G
        suggested_books = self.generateSuggestionsEvent(request)

        return suggestions.SuggestionsResponse(
            suggested_books=suggested_books,
            vector_clock=self.vector_clocks[order_id]
        )


    def generateSuggestionsEvent(self, request):
        order_id = request.order_id
        vc = self.vector_clocks[order_id]

        print(f"[Suggestions] Event G started | VC={vc}")

        item_names = list(request.item_names)

        # Dummy logic
        picks = random.sample(BOOK_POOL, 2)
        suggested_books = [common.Book(**b) for b in picks]

        with self.lock:
            vc[self.SERVICE_INDEX] += 1

        print(f"[Suggestions] Event G finished | VC={vc}")

        return suggested_books


def serve():
    server = grpc.server(futures.ThreadPoolExecutor())
    suggestions_grpc.add_SuggestionsServiceServicer_to_server(SuggestionsService(), server)
    port = "50053"
    server.add_insecure_port("[::]:" + port)
    server.start()
    print("[Suggestions] Server started. Listening on port 50053.")
    server.wait_for_termination()


if __name__ == '__main__':
    serve()
