import sys
import os
import re
import threading
import urllib.request
import json as json_lib

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

ORCHESTRATOR_ADDRESS = os.getenv('ORCHESTRATOR_ADDRESS', 'orchestrator:5000')


def _post_result(order_id, success, reason, vector_clock):
    try:
        payload = json_lib.dumps({
            'order_id': order_id,
            'success': success,
            'reason': reason,
            'vector_clock': list(vector_clock),
            'books': []
        }).encode()
        req = urllib.request.Request(
            f'http://{ORCHESTRATOR_ADDRESS}/order_result',
            data=payload,
            headers={'Content-Type': 'application/json'}
        )
        urllib.request.urlopen(req, timeout=5.0)
    except Exception as e:
        print(f"[TV] Failed to post result: {e}")


class TransactionVerificationService(transaction_verification_grpc.TransactionVerificationServiceServicer):
    def __init__(self):
        self.vector_clocks = {}
        self.SERVICE_INDEX = 0
        self.orders = {}
        self.lock = threading.Lock()

    def _get_vc(self, order_id):
        with self.lock:
            return list(self.vector_clocks[order_id])

    def _merge_and_increment(self, order_id, received):
        with self.lock:
            local = self.vector_clocks[order_id]
            merged = [max(l, r) for l, r in zip(local, list(received))]
            merged[self.SERVICE_INDEX] += 1
            self.vector_clocks[order_id] = merged
            return list(merged)

    def _increment(self, order_id):
        with self.lock:
            self.vector_clocks[order_id][self.SERVICE_INDEX] += 1
            return list(self.vector_clocks[order_id])

    def InitOrder(self, request, context):
        order_id = request.order_id
        with self.lock:
            self.orders[order_id] = request
            self.vector_clocks[order_id] = list(request.vector_clock)
        print(f"[TV] InitOrder {order_id} | VC={self.vector_clocks[order_id]}")
        return transaction_verification.TransactionResponse()

    def ExecuteFlow(self, request, context):
        order_id = request.order_id
        vc = self._merge_and_increment(order_id, request.vector_clock)
        print(f"[TV] ExecuteFlow received {order_id} | VC={vc}")

        failure = threading.Event()

        def event_a():
            vc_a = self._increment(order_id)
            print(f"[TV] Event A (VerifyItems) {order_id} | VC={vc_a}")
            cached = self.orders[order_id]
            if len(cached.items) == 0:
                _post_result(order_id, False, "No items in order", vc_a)
                failure.set()
                return
            for item in cached.items:
                if item.quantity <= 0:
                    _post_result(order_id, False, f"Invalid quantity for {item.name}", vc_a)
                    failure.set()
                    return

        def event_b():
            vc_b = self._increment(order_id)
            print(f"[TV] Event B (CheckUserData) {order_id} | VC={vc_b}")
            cached = self.orders[order_id]
            if not cached.user_name or not cached.user_contact:
                _post_result(order_id, False, "Missing user data", vc_b)
                failure.set()

        def event_c():
            vc_c = self._increment(order_id)
            print(f"[TV] Event C (CheckCard) {order_id} | VC={vc_c}")
            cached = self.orders[order_id]
            card_number = cached.credit_card.number.replace(" ", "").replace("-", "")
            if not card_number.isdigit() or not (13 <= len(card_number) <= 19):
                _post_result(order_id, False, "Invalid credit card number", vc_c)
                failure.set()
                return
            if not re.match(r'^\d{2}/\d{2}$', cached.credit_card.expiration_date):
                _post_result(order_id, False, "Invalid expiration date format", vc_c)
                failure.set()
                return
            if not re.match(r'^\d{3,4}$', cached.credit_card.cvv):
                _post_result(order_id, False, "Invalid CVV", vc_c)
                failure.set()
                return
            if not cached.terms_accepted:
                _post_result(order_id, False, "Terms and conditions not accepted", vc_c)
                failure.set()

        def thread_a_c():
            event_a()
            if failure.is_set():
                return
            event_c()

        def thread_b_d():
            event_b()
            if failure.is_set():
                return
            vc_send = self._get_vc(order_id)
            try:
                with grpc.insecure_channel('fraud_detection:50051') as ch:
                    stub = fraud_detection_grpc.FraudDetectionServiceStub(ch)
                    resp = stub.RunEventD(fraud_detection.OrderEventRequest(
                        order_id=order_id, vector_clock=vc_send
                    ))
                if not resp.success:
                    # FD posted the failure directly; set flag to skip RunEventE
                    failure.set()
            except Exception as e:
                _post_result(order_id, False, str(e), self._get_vc(order_id))
                failure.set()

        t1 = threading.Thread(target=thread_a_c)
        t2 = threading.Thread(target=thread_b_d)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        if failure.is_set():
            return transaction_verification.OrderFlowResponse(success=True)

        vc_send = self._get_vc(order_id)
        try:
            with grpc.insecure_channel('fraud_detection:50051') as ch:
                stub = fraud_detection_grpc.FraudDetectionServiceStub(ch)
                stub.RunEventE(fraud_detection.OrderEventRequest(
                    order_id=order_id, vector_clock=vc_send
                ))
        except Exception as e:
            _post_result(order_id, False, str(e), self._get_vc(order_id))

        return transaction_verification.OrderFlowResponse(success=True)

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
