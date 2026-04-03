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

import grpc
from concurrent import futures


class TransactionVerificationService(transaction_verification_grpc.TransactionVerificationServiceServicer):
    def __init__(self):
        self.vector_clocks = {}
        self.SERVICE_INDEX = 0  # TV = index 0
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
        print(f"[TV] InitOrder {order_id} | VC={self.vector_clocks[order_id]}")
        return transaction_verification.TransactionResponse()

    def VerifyItems(self, request, context):
        order_id = request.order_id
        vc = self.update_vc(order_id, request.vector_clock)
        print(f"[TV] Event A (VerifyItems) {order_id} | VC={vc}")

        cached = self.orders[order_id]
        if len(cached.items) == 0:
            return transaction_verification.OrderEventResponse(success=False, reason="No items in order", vector_clock=vc)
        for item in cached.items:
            if item.quantity <= 0:
                return transaction_verification.OrderEventResponse(success=False, reason=f"Invalid quantity for {item.name}", vector_clock=vc)

        return transaction_verification.OrderEventResponse(success=True, reason="Items valid", vector_clock=vc)

    def CheckUserData(self, request, context):
        order_id = request.order_id
        vc = self.update_vc(order_id, request.vector_clock)
        print(f"[TV] Event B (CheckUserData) {order_id} | VC={vc}")

        cached = self.orders[order_id]
        if not cached.user_name or not cached.user_contact:
            return transaction_verification.OrderEventResponse(success=False, reason="Missing user data", vector_clock=vc)

        return transaction_verification.OrderEventResponse(success=True, reason="User data valid", vector_clock=vc)

    def CheckCard(self, request, context):
        order_id = request.order_id
        vc = self.update_vc(order_id, request.vector_clock)
        print(f"[TV] Event C (CheckCard) {order_id} | VC={vc}")

        cached = self.orders[order_id]
        card_number = cached.credit_card.number.replace(" ", "").replace("-", "")

        if not card_number.isdigit() or not (13 <= len(card_number) <= 19):
            return transaction_verification.OrderEventResponse(success=False, reason="Invalid credit card number", vector_clock=vc)
        if not re.match(r'^\d{2}/\d{2}$', cached.credit_card.expiration_date):
            return transaction_verification.OrderEventResponse(success=False, reason="Invalid expiration date format", vector_clock=vc)
        if not re.match(r'^\d{3,4}$', cached.credit_card.cvv):
            return transaction_verification.OrderEventResponse(success=False, reason="Invalid CVV", vector_clock=vc)
        if not cached.terms_accepted:
            return transaction_verification.OrderEventResponse(success=False, reason="Terms and conditions not accepted", vector_clock=vc)

        return transaction_verification.OrderEventResponse(success=True, reason="Card valid", vector_clock=vc)

    def ClearOrder(self, request, context):
        order_id = request.order_id
        final_vc = list(request.vector_clock)

        with self.lock:
            local_vc = self.vector_clocks.get(order_id, [0, 0, 0])
            if any(local_vc[i] > final_vc[i] for i in range(len(local_vc))):
                print(f"[TV] ClearOrder {order_id} | VC mismatch: local={local_vc} final={final_vc}")
                return transaction_verification.ClearOrderResponse(success=False, error="Local VC exceeds final VC")
            self.orders.pop(order_id, None)
            self.vector_clocks.pop(order_id, None)

        print(f"[TV] ClearOrder {order_id} | cleared | final_VC={final_vc}")
        return transaction_verification.ClearOrderResponse(success=True)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor())
    transaction_verification_grpc.add_TransactionVerificationServiceServicer_to_server(
        TransactionVerificationService(), server
    )
    server.add_insecure_port("[::]:50052")
    server.start()
    print("[TransactionVerification] Server started. Listening on port 50052.")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()
