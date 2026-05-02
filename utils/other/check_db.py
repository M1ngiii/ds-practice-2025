import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(__file__, '../../pb')))
sys.path.insert(0, os.path.abspath(os.path.join(__file__, '../../pb/books_database')))

import grpc
import books_database_pb2 as books_db
import books_database_pb2_grpc as books_db_grpc

REPLICAS = [
    ("Primary", "localhost:50055"),
    ("Backup 1", "localhost:50056"),
    ("Backup 2", "localhost:50057"),
]

BOOKS = ["Book A", "Book B", "Book C"]

for label, addr in REPLICAS:
    print(f"\n[{label}] ({addr})")
    try:
        with grpc.insecure_channel(addr) as channel:
            stub = books_db_grpc.BooksDatabaseStub(channel)
            for title in BOOKS:
                resp = stub.Read(books_db.ReadRequest(title=title), timeout=2.0)
                print(f"  {title}: {resp.stock}")
    except Exception as e:
        print(f"  unreachable: {e}")
