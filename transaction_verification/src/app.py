import sys
import os
import re
import threading

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")

pb_root_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb'))
sys.path.insert(0, pb_root_path)

transaction_verification_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/transaction_verification'))
sys.path.insert(0, transaction_verification_grpc_path)
import transaction_verification_pb2 as transaction_verification
import transaction_verification_pb2_grpc as transaction_verification_grpc

fraud_detection_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/fraud_detection'))
sys.path.insert(0, fraud_detection_grpc_path)
import fraud_detection_pb2 as fraud_detection
import fraud_detection_pb2_grpc as fraud_detection_grpc

import grpc
from concurrent import futures

class TransactionVerificationService(transaction_verification_grpc.TransactionVerificationServiceServicer):
    def __init__(self):
        self.vector_clocks = {}
        self.SERVICE_INDEX = 0  # TV = index 0
        self.orders = {}
        self.lock = threading.Lock()
        self.results_lock = threading.Lock()

    def merge_clocks(self, local, received):
        return [max(l, r) for l, r in zip(local, received)]
    
    def InitOrder(self, request, context):
        order_id = request.order_id

        self.orders[order_id] = request
        self.vector_clocks[order_id] = list(request.vector_clock)

        print(f"[TV] Init order {order_id} | VC={self.vector_clocks[order_id]}")

        return transaction_verification.TransactionResponse()

    def verifyTransaction(self, request, context):
        order_id = request.order_id
        incoming_vc = list(request.vector_clock)

        print(f"[TV] Execute order {order_id} | VC={incoming_vc}")

        # Merge incoming clock with local clock
        self.vector_clocks[order_id] = self.merge_clocks(
            self.vector_clocks.get(order_id, incoming_vc),
            incoming_vc
        )

        # Use cached order data from initialization
        request = self.orders[order_id]

        results = {}

        # A and B run in parallel
        thread_a = threading.Thread(target=self.VerifyItemsEvent, args=(request, results))
        thread_b = threading.Thread(target=self.checkUserDataEvent, args=(request, results))

        thread_a.start()
        thread_b.start()

        # C depends on A
        thread_a.join()

        if "a" not in results or not results["a"][0]:
            return transaction_verification.TransactionResponse(
                is_valid=False,
                reason=results["a"][1] if "a" in results else "Items validation failed",
                vector_clock=self.vector_clocks[order_id]
            )

        self.checkCardEvent(request, results)

        # Wait for B before finalization
        thread_b.join()

        valid, reason = self.finalizeOrderEvent(request, results)

        # Stop if validation failed
        if not valid:
            return transaction_verification.TransactionResponse(
                is_valid=False,
                reason=reason,
                vector_clock=self.vector_clocks[order_id]
            )

        # Pass current VC to Fraud Detection
        vc = list(self.vector_clocks[order_id])

        with grpc.insecure_channel('fraud_detection:50051') as channel:
            stub = fraud_detection_grpc.FraudDetectionServiceStub(channel)

            fd_response = stub.checkFraud(
                fraud_detection.FraudRequest(
                    order_id=order_id,
                    vector_clock=vc,
                    card_number=request.credit_card.number,
                    order_amount=sum(item.quantity for item in request.items),
                    item_names=[item.name for item in request.items]
                )
            )

        # Merge VC after downstream service responds
        self.vector_clocks[order_id] = self.merge_clocks(
            self.vector_clocks[order_id],
            list(fd_response.vector_clock)
        )

        if fd_response.is_fraud:
            return transaction_verification.TransactionResponse(
                is_valid=False,
                reason="Fraud detected",
                vector_clock=self.vector_clocks[order_id]
            )

        return transaction_verification.TransactionResponse(
            is_valid=True,
            reason="OK",
            vector_clock=self.vector_clocks[order_id],
            suggested_books=fd_response.suggested_books
        )

    def VerifyItemsEvent(self, request, results):
        order_id = request.order_id
        vc = self.vector_clocks[order_id]

        print(f"[TV] Event A started | VC={vc}")

        if len(request.items) == 0:
            with self.results_lock:
                results["a"] = (False, "No items in order")
            return

        for item in request.items:
            if item.quantity <= 0:
                with self.results_lock:
                    results["a"] = (False, f"Invalid quantity for item {item.name}")
                return

        with self.lock:
            vc[self.SERVICE_INDEX] += 1

        print(f"[TV] Event A finished | VC={vc}")

        with self.results_lock:
            results["a"] = (True, "Items valid")
    
    def checkUserDataEvent(self, request, results):
        order_id = request.order_id
        vc = self.vector_clocks[order_id]

        print(f"[TV] Event B started | VC={vc}")

        if not request.user_name or not request.user_contact:
            with self.results_lock:
                results["b"] = (False, "Missing user data")
            return

        with self.lock:
            vc[self.SERVICE_INDEX] += 1

        print(f"[TV] Event B finished | VC={vc}")

        with self.results_lock:
            results["b"] = (True, "User data valid")

    def checkCardEvent(self, request, results):
        order_id = request.order_id
        vc = self.vector_clocks[order_id]

        print(f"[TV] Event C started | VC={vc}")

        card_number = request.credit_card.number.replace(" ", "").replace("-", "")

        if not card_number.isdigit() or not (13 <= len(card_number) <= 19):
            with self.results_lock:
                results["c"] = (False, "Invalid credit card number")
            return

        if not re.match(r'^\d{2}/\d{2}$', request.credit_card.expiration_date):
            with self.results_lock:
                results["c"] = (False, "Invalid expiration date format")
            return

        if not re.match(r'^\d{3,4}$', request.credit_card.cvv):
            with self.results_lock:
                results["c"] = (False, "Invalid CVV")
            return

        with self.lock:
            vc[self.SERVICE_INDEX] += 1

        print(f"[TV] Event C finished | VC={vc}")

        with self.results_lock:
            results["c"] = (True, "Card valid")

    def finalizeOrderEvent(self, request, results):
        order_id = request.order_id
        vc = self.vector_clocks[order_id]

        print(f"[TV] Event D started | VC={vc}")

        for key in ["a", "b", "c"]:
            if key not in results or results[key][0] is False:
                return False, results[key][1]

        if not request.terms_accepted:
            print("[TV] Event D failed: terms not accepted")
            return False, "Terms and conditions not accepted"

        with self.lock:
            vc[self.SERVICE_INDEX] += 1

        print(f"[TV] Event D finished | VC={vc}")

        return True, "OK"

def serve():
    server = grpc.server(futures.ThreadPoolExecutor())
    transaction_verification_grpc.add_TransactionVerificationServiceServicer_to_server(
        TransactionVerificationService(), server
    )
    port = "50052"
    server.add_insecure_port("[::]:" + port)
    server.start()
    print("[TransactionVerification] Server started. Listening on port 50052.")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()
