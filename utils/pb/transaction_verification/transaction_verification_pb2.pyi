from common import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Item(_message.Message):
    __slots__ = ("name", "quantity")
    NAME_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    name: str
    quantity: int
    def __init__(self, name: _Optional[str] = ..., quantity: _Optional[int] = ...) -> None: ...

class CreditCard(_message.Message):
    __slots__ = ("number", "expiration_date", "cvv")
    NUMBER_FIELD_NUMBER: _ClassVar[int]
    EXPIRATION_DATE_FIELD_NUMBER: _ClassVar[int]
    CVV_FIELD_NUMBER: _ClassVar[int]
    number: str
    expiration_date: str
    cvv: str
    def __init__(self, number: _Optional[str] = ..., expiration_date: _Optional[str] = ..., cvv: _Optional[str] = ...) -> None: ...

class TransactionRequest(_message.Message):
    __slots__ = ("order_id", "vector_clock", "user_name", "user_contact", "items", "credit_card", "terms_accepted")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    VECTOR_CLOCK_FIELD_NUMBER: _ClassVar[int]
    USER_NAME_FIELD_NUMBER: _ClassVar[int]
    USER_CONTACT_FIELD_NUMBER: _ClassVar[int]
    ITEMS_FIELD_NUMBER: _ClassVar[int]
    CREDIT_CARD_FIELD_NUMBER: _ClassVar[int]
    TERMS_ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    vector_clock: _containers.RepeatedScalarFieldContainer[int]
    user_name: str
    user_contact: str
    items: _containers.RepeatedCompositeFieldContainer[Item]
    credit_card: CreditCard
    terms_accepted: bool
    def __init__(self, order_id: _Optional[str] = ..., vector_clock: _Optional[_Iterable[int]] = ..., user_name: _Optional[str] = ..., user_contact: _Optional[str] = ..., items: _Optional[_Iterable[_Union[Item, _Mapping]]] = ..., credit_card: _Optional[_Union[CreditCard, _Mapping]] = ..., terms_accepted: bool = ...) -> None: ...

class TransactionResponse(_message.Message):
    __slots__ = ("is_valid", "reason", "vector_clock", "suggested_books")
    IS_VALID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    VECTOR_CLOCK_FIELD_NUMBER: _ClassVar[int]
    SUGGESTED_BOOKS_FIELD_NUMBER: _ClassVar[int]
    is_valid: bool
    reason: str
    vector_clock: _containers.RepeatedScalarFieldContainer[int]
    suggested_books: _containers.RepeatedCompositeFieldContainer[_common_pb2.Book]
    def __init__(self, is_valid: bool = ..., reason: _Optional[str] = ..., vector_clock: _Optional[_Iterable[int]] = ..., suggested_books: _Optional[_Iterable[_Union[_common_pb2.Book, _Mapping]]] = ...) -> None: ...

class OrderFlowRequest(_message.Message):
    __slots__ = ("order_id", "vector_clock")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    VECTOR_CLOCK_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    vector_clock: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, order_id: _Optional[str] = ..., vector_clock: _Optional[_Iterable[int]] = ...) -> None: ...

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
