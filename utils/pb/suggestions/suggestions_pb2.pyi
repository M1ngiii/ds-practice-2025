from common import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SuggestionsRequest(_message.Message):
    __slots__ = ("order_id", "vector_clock", "item_names")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    VECTOR_CLOCK_FIELD_NUMBER: _ClassVar[int]
    ITEM_NAMES_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    vector_clock: _containers.RepeatedScalarFieldContainer[int]
    item_names: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, order_id: _Optional[str] = ..., vector_clock: _Optional[_Iterable[int]] = ..., item_names: _Optional[_Iterable[str]] = ...) -> None: ...

class SuggestionsResponse(_message.Message):
    __slots__ = ("suggested_books", "vector_clock")
    SUGGESTED_BOOKS_FIELD_NUMBER: _ClassVar[int]
    VECTOR_CLOCK_FIELD_NUMBER: _ClassVar[int]
    suggested_books: _containers.RepeatedCompositeFieldContainer[_common_pb2.Book]
    vector_clock: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, suggested_books: _Optional[_Iterable[_Union[_common_pb2.Book, _Mapping]]] = ..., vector_clock: _Optional[_Iterable[int]] = ...) -> None: ...

class OrderEventRequest(_message.Message):
    __slots__ = ("order_id", "vector_clock")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    VECTOR_CLOCK_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    vector_clock: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, order_id: _Optional[str] = ..., vector_clock: _Optional[_Iterable[int]] = ...) -> None: ...

class OrderEventResponse(_message.Message):
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
