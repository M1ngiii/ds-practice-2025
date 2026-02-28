import sys
import os

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")
fraud_detection_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/fraud_detection'))
sys.path.insert(0, fraud_detection_grpc_path)
import fraud_detection_pb2 as fraud_detection
import fraud_detection_pb2_grpc as fraud_detection_grpc

import grpc
import threading
from flask import Flask, request
from flask_cors import CORS
import json

app = Flask(__name__)
CORS(app, resources={r'/*': {'origins': '*'}})

def check_fraud(card_number, order_amount, results):
    print(f"[Orchestrator] Thread started: check_fraud")
    with grpc.insecure_channel('fraud_detection:50051') as channel:
        stub = fraud_detection_grpc.FraudDetectionServiceStub(channel)
        response = stub.checkFraud(fraud_detection.FraudRequest(
            card_number=card_number,
            order_amount=order_amount
        ))
    print(f"[Orchestrator] check_fraud result: {response.is_fraud}")
    results['fraud'] = response.is_fraud

# Placeholders — replace once you build those services
def check_transaction(order_data, results):
    print(f"[Orchestrator] Thread started: check_transaction")
    # TODO: gRPC call to transaction_verification:50052
    results['transaction_valid'] = True

def get_suggestions(order_data, results):
    print(f"[Orchestrator] Thread started: get_suggestions")
    # TODO: gRPC call to suggestions:50053
    results['suggestions'] = [
        {'bookId': '123', 'title': 'The Best Book', 'author': 'Author 1'},
        {'bookId': '456', 'title': 'The Second Best Book', 'author': 'Author 2'}
    ]

@app.route('/checkout', methods=['POST'])
def checkout():
    request_data = json.loads(request.data)
    print(f"[Orchestrator] Received checkout request: {request_data.get('items')}")

    card_number = request_data.get('creditCard', {}).get('number', '')
    order_amount = sum(item.get('quantity', 0) * item.get('price', 0) 
                       for item in request_data.get('items', []))

    results = {}

    threads = [
        threading.Thread(target=check_fraud, args=(card_number, order_amount, results)),
        threading.Thread(target=check_transaction, args=(request_data, results)),
        threading.Thread(target=get_suggestions, args=(request_data, results)),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"[Orchestrator] All threads finished. Results: {results}")

    if results.get('fraud') or not results.get('transaction_valid'):
        status = 'Order Rejected'
    else:
        status = 'Order Approved'

    return {
        'orderId': '12345',
        'status': status,
        'suggestedBooks': results.get('suggestions', [])
    }

@app.route('/', methods=['GET'])
def index():
    return "Orchestrator is running."

if __name__ == '__main__':
    app.run(host='0.0.0.0')
