from common import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class FraudRequest(_message.Message):
    __slots__ = ("order_id", "vector_clock", "card_number", "order_amount", "item_names")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    VECTOR_CLOCK_FIELD_NUMBER: _ClassVar[int]
    CARD_NUMBER_FIELD_NUMBER: _ClassVar[int]
    ORDER_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    ITEM_NAMES_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    vector_clock: _containers.RepeatedScalarFieldContainer[int]
    card_number: str
    order_amount: float
    item_names: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, order_id: _Optional[str] = ..., vector_clock: _Optional[_Iterable[int]] = ..., card_number: _Optional[str] = ..., order_amount: _Optional[float] = ..., item_names: _Optional[_Iterable[str]] = ...) -> None: ...

class FraudResponse(_message.Message):
    __slots__ = ("is_fraud", "vector_clock", "suggested_books")
    IS_FRAUD_FIELD_NUMBER: _ClassVar[int]
    VECTOR_CLOCK_FIELD_NUMBER: _ClassVar[int]
    SUGGESTED_BOOKS_FIELD_NUMBER: _ClassVar[int]
    is_fraud: bool
    vector_clock: _containers.RepeatedScalarFieldContainer[int]
    suggested_books: _containers.RepeatedCompositeFieldContainer[_common_pb2.Book]
    def __init__(self, is_fraud: bool = ..., vector_clock: _Optional[_Iterable[int]] = ..., suggested_books: _Optional[_Iterable[_Union[_common_pb2.Book, _Mapping]]] = ...) -> None: ...

class OrderEventRequest(_message.Message):
    __slots__ = ("order_id", "vector_clock")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    VECTOR_CLOCK_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    vector_clock: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, order_id: _Optional[str] = ..., vector_clock: _Optional[_Iterable[int]] = ...) -> None: ...

class OrderEventResponse(_message.Message):
    __slots__ = ("success", "reason", "vector_clock")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    VECTOR_CLOCK_FIELD_NUMBER: _ClassVar[int]
    success: bool
    reason: str
    vector_clock: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, success: bool = ..., reason: _Optional[str] = ..., vector_clock: _Optional[_Iterable[int]] = ...) -> None: ...

class OrderFlowResponse(_message.Message):
    __slots__ = ("success", "reason", "vector_clock", "suggested_books")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    VECTOR_CLOCK_FIELD_NUMBER: _ClassVar[int]
    SUGGESTED_BOOKS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    reason: str
    vector_clock: _containers.RepeatedScalarFieldContainer[int]
    suggested_books: _containers.RepeatedCompositeFieldContainer[_common_pb2.Book]
    def __init__(self, success: bool = ..., reason: _Optional[str] = ..., vector_clock: _Optional[_Iterable[int]] = ..., suggested_books: _Optional[_Iterable[_Union[_common_pb2.Book, _Mapping]]] = ...) -> None: ...

class ClearOrderRequest(_message.Message):
    __slots__ = ("order_id", "vector_clock")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    VECTOR_CLOCK_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    vector_clock: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, order_id: _Optional[str] = ..., vector_clock: _Optional[_Iterable[int]] = ...) -> None: ...

class ClearOrderResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ...) -> None: ...
