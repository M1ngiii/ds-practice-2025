import sys
import os
import threading
from concurrent import futures

FILE = __file__ if '__file__' in globals() else os.getenv("PYTHONFILE", "")

pb_root_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb'))
sys.path.insert(0, pb_root_path)

books_database_grpc_path = os.path.abspath(os.path.join(FILE, '../../../utils/pb/books_database'))
sys.path.insert(0, books_database_grpc_path)
import books_database_pb2 as books_db
import books_database_pb2_grpc as books_db_grpc

import grpc

INITIAL_STOCK = {
    "Book A": 10,
    "Book B": 10,
    "Book C": 10,
}


class BooksDatabaseServicer(books_db_grpc.BooksDatabaseServicer):
    def __init__(self):
        self.store = dict(INITIAL_STOCK)
        self.pending = {}  # {order_id: [(title, new_stock)]}
        self.lock = threading.Lock()

    def Read(self, request, context):
        with self.lock:
            stock = self.store.get(request.title, 0)
        return books_db.ReadResponse(stock=stock)

    def Write(self, request, context):
        with self.lock:
            self.store[request.title] = request.new_stock
        return books_db.WriteResponse(success=True)

    def Prepare(self, request, context):
        if request.new_stock < 0:
            print(f"[DB] Prepare REJECTED order={request.order_id} title={request.title} — insufficient stock")
            return books_db.PrepareResponse(success=False, reason=f"Insufficient stock for '{request.title}'")
        with self.lock:
            if request.order_id not in self.pending:
                self.pending[request.order_id] = []
            self.pending[request.order_id].append((request.title, request.new_stock))
        print(f"[DB] Prepare order={request.order_id} title={request.title} new_stock={request.new_stock} — voted Yes")
        return books_db.PrepareResponse(success=True)

    def Commit(self, request, context):
        with self.lock:
            writes = self.pending.pop(request.order_id, [])
            for title, new_stock in writes:
                self.store[title] = new_stock
        print(f"[DB] Commit order={request.order_id} applied={writes}")
        return books_db.CommitResponse(success=True)

    def Abort(self, request, context):
        with self.lock:
            self.pending.pop(request.order_id, None)
        print(f"[DB] Abort order={request.order_id} — staged writes discarded")
        return books_db.AbortResponse(success=True)


class PrimaryReplica(BooksDatabaseServicer):
    def __init__(self, backup_addresses):
        super().__init__()
        self.backup_addresses = backup_addresses

    def Write(self, request, context):
        with self.lock:
            self.store[request.title] = request.new_stock
        for addr in self.backup_addresses:
            try:
                with grpc.insecure_channel(addr) as channel:
                    stub = books_db_grpc.BooksDatabaseStub(channel)
                    stub.Write(request, timeout=2.0)
            except Exception as e:
                print(f"[DB Primary] Replication to {addr} failed: {e}")
        return books_db.WriteResponse(success=True)

    def Commit(self, request, context):
        with self.lock:
            writes = self.pending.pop(request.order_id, [])
            for title, new_stock in writes:
                self.store[title] = new_stock
        print(f"[DB Primary] Commit order={request.order_id} applied={writes}")
        for title, new_stock in writes:
            write_req = books_db.WriteRequest(title=title, new_stock=new_stock)
            for addr in self.backup_addresses:
                try:
                    with grpc.insecure_channel(addr) as channel:
                        stub = books_db_grpc.BooksDatabaseStub(channel)
                        stub.Write(write_req, timeout=2.0)
                except Exception as e:
                    print(f"[DB Primary] Replication to {addr} failed: {e}")
        return books_db.CommitResponse(success=True)


def serve():
    role = os.getenv("DB_ROLE", "backup")
    port = os.getenv("DB_PORT", "50055")
    raw_backups = os.getenv("DB_BACKUP_ADDRESSES", "")
    backup_addresses = [a.strip() for a in raw_backups.split(",") if a.strip()]

    if role == "primary":
        servicer = PrimaryReplica(backup_addresses)
        print(f"[DB Primary] Starting on port {port} | backups={backup_addresses}")
    else:
        servicer = BooksDatabaseServicer()
        print(f"[DB Backup] Starting on port {port}")

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    books_db_grpc.add_BooksDatabaseServicer_to_server(servicer, server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"[DB] Server started. Listening on port {port}.")
    server.wait_for_termination()


if __name__ == '__main__':
    serve()
