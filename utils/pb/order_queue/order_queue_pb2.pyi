from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class QueueItem(_message.Message):
    __slots__ = ("order_id",)
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    def __init__(self, order_id: _Optional[str] = ...) -> None: ...

class EnqueueRequest(_message.Message):
    __slots__ = ("order_id",)
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    def __init__(self, order_id: _Optional[str] = ...) -> None: ...

class EnqueueResponse(_message.Message):
    __slots__ = ("success", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ...) -> None: ...

class DequeueRequest(_message.Message):
    __slots__ = ("executor_id",)
    EXECUTOR_ID_FIELD_NUMBER: _ClassVar[int]
    executor_id: str
    def __init__(self, executor_id: _Optional[str] = ...) -> None: ...

class DequeueResponse(_message.Message):
    __slots__ = ("success", "has_order", "order", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    HAS_ORDER_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    has_order: bool
    order: QueueItem
    message: str
    def __init__(self, success: bool = ..., has_order: bool = ..., order: _Optional[_Union[QueueItem, _Mapping]] = ..., message: _Optional[str] = ...) -> None: ...

class LeaderRequest(_message.Message):
    __slots__ = ("executor_id",)
    EXECUTOR_ID_FIELD_NUMBER: _ClassVar[int]
    executor_id: str
    def __init__(self, executor_id: _Optional[str] = ...) -> None: ...

class LeaderResponse(_message.Message):
    __slots__ = ("success", "is_leader", "leader_id", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    IS_LEADER_FIELD_NUMBER: _ClassVar[int]
    LEADER_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    is_leader: bool
    leader_id: str
    message: str
    def __init__(self, success: bool = ..., is_leader: bool = ..., leader_id: _Optional[str] = ..., message: _Optional[str] = ...) -> None: ...

class GetLeaderRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetLeaderResponse(_message.Message):
    __slots__ = ("has_leader", "leader_id")
    HAS_LEADER_FIELD_NUMBER: _ClassVar[int]
    LEADER_ID_FIELD_NUMBER: _ClassVar[int]
    has_leader: bool
    leader_id: str
    def __init__(self, has_leader: bool = ..., leader_id: _Optional[str] = ...) -> None: ...
