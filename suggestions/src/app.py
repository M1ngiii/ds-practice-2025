import sys
import os

# This set of lines are needed to import the gRPC stubs.
# The path of the stubs is relative to the current file, or absolute inside the container.
# Change these lines only if strictly needed.
FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
suggestions_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/suggestions'))
sys.path.insert(0, suggestions_grpc_path)
import suggestions_pb2 as suggestions
import suggestions_pb2_grpc as suggestions_grpc

import grpc
from concurrent import futures
import random

BOOK_POOL = [
    {'book_id': '123', 'title': 'The Best Book', 'author': 'Author 1'},
    {'book_id': '456', 'title': 'The Second Best Book', 'author': 'Author 2'},
    {'book_id': '789', 'title': 'The Third Best Book', 'author': 'Author 3'}
]


class SuggestionsService(suggestions_grpc.SuggestionsServiceServicer):

    def getSuggestions(self, request, context):
        item_names = list(request.item_names)

        print(f"[Suggestions] Received request — items: {item_names}")

        picks = random.sample(BOOK_POOL, 2)
        suggested_books = [suggestions.Book(**b) for b in picks]

        print(f"[Suggestions] Result — suggested_books: {suggested_books}")
        return suggestions.SuggestionsResponse(suggested_books=suggested_books)


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
