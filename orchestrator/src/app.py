import sys
import os

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")

pb_root_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb'))
sys.path.insert(0, pb_root_path)

fraud_detection_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/fraud_detection'))
sys.path.insert(0, fraud_detection_grpc_path)
import fraud_detection_pb2 as fraud_detection
import fraud_detection_pb2_grpc as fraud_detection_grpc

transaction_verification_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/transaction_verification'))
sys.path.insert(0, transaction_verification_grpc_path)
import transaction_verification_pb2 as transaction_verification
import transaction_verification_pb2_grpc as transaction_verification_grpc

suggestions_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/suggestions'))
sys.path.insert(0, suggestions_grpc_path)
import suggestions_pb2 as suggestions
import suggestions_pb2_grpc as suggestions_grpc

import grpc
import uuid
import threading
from flask import Flask, request
from flask_cors import CORS
import json

app = Flask(__name__)
CORS(app, resources={r'/*': {'origins': '*'}})

# Execution funcs
def check_fraud(card_number, order_amount, order_id, vector_clock):
    with grpc.insecure_channel('fraud_detection:50051') as channel:
        stub = fraud_detection_grpc.FraudDetectionServiceStub(channel)

        response = stub.checkFraud(
            fraud_detection.FraudRequest(
                order_id=order_id,
                vector_clock=vector_clock,
                card_number=card_number,
                order_amount=order_amount
            )
        )

    return response

def check_transaction(order_data, order_id, vector_clock):
    with grpc.insecure_channel('transaction_verification:50052') as channel:
        stub = transaction_verification_grpc.TransactionVerificationServiceStub(channel)

        items = [
            transaction_verification.Item(
                name=item.get('name', ''),
                quantity=item.get('quantity', 0)
            )
            for item in order_data.get('items', [])
        ]

        credit_card = transaction_verification.CreditCard(
            number=order_data.get('creditCard', {}).get('number', ''),
            expiration_date=order_data.get('creditCard', {}).get('expirationDate', ''),
            cvv=order_data.get('creditCard', {}).get('cvv', '')
        )

        response = stub.verifyTransaction(
            transaction_verification.TransactionRequest(
                order_id=order_id,
                vector_clock=vector_clock,
                user_name=order_data.get('user', {}).get('name', ''),
                user_contact=order_data.get('user', {}).get('contact', ''),
                items=items,
                credit_card=credit_card,
                terms_accepted=order_data.get('termsAccepted', False)
            )
        )

    return response

def get_suggestions(order_data, order_id, vector_clock):
    item_names = [item.get('name', '') for item in order_data.get('items', [])]

    with grpc.insecure_channel('suggestions:50053') as channel:
        stub = suggestions_grpc.SuggestionsServiceStub(channel)

        response = stub.getSuggestions(
            suggestions.SuggestionsRequest(
                order_id=order_id,
                vector_clock=vector_clock,
                item_names=item_names
            )
        )

    return response


# Initialization funcs
def init_transaction(order_data, order_id, vector_clock):
    with grpc.insecure_channel('transaction_verification:50052') as channel:
        stub = transaction_verification_grpc.TransactionVerificationServiceStub(channel)

        items = [
            transaction_verification.Item(
                name=item.get('name', ''),
                quantity=item.get('quantity', 0)
            )
            for item in order_data.get('items', [])
        ]

        credit_card = transaction_verification.CreditCard(
            number=order_data.get('creditCard', {}).get('number', ''),
            expiration_date=order_data.get('creditCard', {}).get('expirationDate', ''),
            cvv=order_data.get('creditCard', {}).get('cvv', '')
        )

        stub.InitOrder(
            transaction_verification.TransactionRequest(
                order_id=order_id,
                vector_clock=vector_clock,
                user_name=order_data.get('user', {}).get('name', ''),
                user_contact=order_data.get('user', {}).get('contact', ''),
                items=items,
                credit_card=credit_card,
                terms_accepted=order_data.get('termsAccepted', False)
            )
        )

def init_fraud(card_number, order_amount, order_id, vector_clock):
    with grpc.insecure_channel('fraud_detection:50051') as channel:
        stub = fraud_detection_grpc.FraudDetectionServiceStub(channel)

        stub.InitOrder(
            fraud_detection.FraudRequest(
                order_id=order_id,
                vector_clock=vector_clock,
                card_number=card_number,
                order_amount=order_amount,
                item_names=[]
            )
        )

def init_suggestions(order_data, order_id, vector_clock):
    with grpc.insecure_channel('suggestions:50053') as channel:
        stub = suggestions_grpc.SuggestionsServiceStub(channel)

        stub.InitOrder(
            suggestions.SuggestionsRequest(
                order_id=order_id,
                vector_clock=vector_clock,
                item_names=[item.get('name', '') for item in order_data.get('items', [])]
            )
        )

@app.route('/checkout', methods=['POST'])
def checkout():
    request_data = json.loads(request.data)

    order_id = str(uuid.uuid4())
    vector_clock = [0, 0, 0]

    print(f"[Orchestrator] Starting order {order_id}")

    card_number = request_data.get('creditCard', {}).get('number', '')
    order_amount = sum(
        item.get('quantity', 0) * item.get('price', 0)
        for item in request_data.get('items', [])
    )

    # INITIALIZATION
    init_threads = [
        threading.Thread(target=init_transaction, args=(request_data, order_id, vector_clock)),
        threading.Thread(target=init_fraud, args=(card_number, order_amount, order_id, vector_clock)),
        threading.Thread(target=init_suggestions, args=(request_data, order_id, vector_clock)),
    ]

    for thread in init_threads:
        thread.start()

    for thread in init_threads:
        thread.join()

    print(f"[Orchestrator] Initialization complete")

    # EXECUTION
    tv_response = check_transaction(request_data, order_id, vector_clock)

    print(f"[Orchestrator] Final VC: {list(tv_response.vector_clock)}")

    if not tv_response.is_valid:
        return {
            'orderId': order_id,
            'status': 'Order Rejected',
            'reason': tv_response.reason
        }

    return {
        'orderId': order_id,
        'status': 'Order Approved',
        'suggestedBooks': [
            {'bookId': b.book_id, 'title': b.title, 'author': b.author}
            for b in tv_response.suggested_books
        ]
    }

@app.route('/', methods=['GET'])
def index():
    return "Orchestrator is running."

if __name__ == '__main__':
    app.run(host='0.0.0.0')
