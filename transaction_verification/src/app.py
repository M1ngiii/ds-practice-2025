import sys
import os
import re

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
transaction_verification_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/transaction_verification'))
sys.path.insert(0, transaction_verification_grpc_path)
import transaction_verification_pb2 as transaction_verification
import transaction_verification_pb2_grpc as transaction_verification_grpc

import grpc
from concurrent import futures

class TransactionVerificationService(transaction_verification_grpc.TransactionVerificationServiceServicer):

    def verifyTransaction(self, request, context):
        print(f"[TransactionVerification] Received verification request for user: {request.user_name}")

        # Check user data
        if not request.user_name or not request.user_contact:
            print("[TransactionVerification] Invalid: missing user data")
            return transaction_verification.TransactionResponse(is_valid=False, reason="Missing user data")

        # Check items not empty
        if len(request.items) == 0:
            print("[TransactionVerification] Invalid: no items in order")
            return transaction_verification.TransactionResponse(is_valid=False, reason="No items in order")

        # Check all items have valid quantity
        for item in request.items:
            if item.quantity <= 0:
                print(f"[TransactionVerification] Invalid: item {item.name} has invalid quantity")
                return transaction_verification.TransactionResponse(is_valid=False, reason=f"Invalid quantity for item {item.name}")

        # Check credit card number (basic Luhn or just format)
        card_number = request.credit_card.number.replace(" ", "").replace("-", "")
        if not card_number.isdigit() or not (13 <= len(card_number) <= 19):
            print("[TransactionVerification] Invalid: bad credit card number")
            return transaction_verification.TransactionResponse(is_valid=False, reason="Invalid credit card number")

        # Check expiration date format MM/YY
        if not re.match(r'^\d{2}/\d{2}$', request.credit_card.expiration_date):
            print("[TransactionVerification] Invalid: bad expiration date format")
            return transaction_verification.TransactionResponse(is_valid=False, reason="Invalid expiration date format")

        # Check CVV (3 or 4 digits)
        if not re.match(r'^\d{3,4}$', request.credit_card.cvv):
            print("[TransactionVerification] Invalid: bad CVV")
            return transaction_verification.TransactionResponse(is_valid=False, reason="Invalid CVV")

        # Check terms accepted
        if not request.terms_accepted:
            print("[TransactionVerification] Invalid: terms not accepted")
            return transaction_verification.TransactionResponse(is_valid=False, reason="Terms and conditions not accepted")

        print("[TransactionVerification] Transaction is valid")
        return transaction_verification.TransactionResponse(is_valid=True, reason="OK")


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
