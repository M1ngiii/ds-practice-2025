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
