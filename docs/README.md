# Documentation

Note: The mermaid diagram assets were generated with the help of Claude Code.

---

## System Model

### Architecture

The system is a **microservice architecture** deployed as Docker containers on a shared bridge network (`docker compose`). Services are loosely coupled and communicate exclusively over the network. There is no shared memory or shared filesystem.

There are seven distinct services:

| Service | Role | Protocol | Port |
|---------|------|----------|------|
| `frontend` | Serves the web UI (nginx) | HTTP | 8080 |
| `orchestrator` | Entry point; coordinates order processing | HTTP/REST (inbound), gRPC (outbound) | 5000 |
| `transaction_verification` | Validates items, user data, credit card | gRPC | 50052 |
| `fraud_detection` | Checks for user and card fraud | gRPC | 50051 |
| `suggestions` | Generates book recommendations | gRPC | 50053 |
| `order_queue` | In-memory FIFO queue + leader election authority | gRPC | 50054 |
| `order_executor` | Consumes approved orders from the queue (×2 replicas) | gRPC server (`Ping`) + gRPC client (to OrderQueue) | 50061 (internal only) |

### Communication

```
Browser
  │  HTTP/REST (JSON)
  ▼
Orchestrator ──gRPC──► TransactionVerification ──gRPC──► FraudDetection ──gRPC──► Suggestions
             ──gRPC──► FraudDetection      (Init / ClearOrder only)
             ──gRPC──► Suggestions         (Init / ClearOrder only)
             ──gRPC──► OrderQueue          (enqueue approved orders)
             ◄──HTTP── TV / FD / SG        (direct result via POST /order_result)

OrderExecutor ──gRPC──► OrderQueue  (leader election + dequeue)
```

- **Frontend → Orchestrator**: plain HTTP POST `/checkout` with a JSON body.
- **Orchestrator → TransactionVerification**: single `ExecuteFlow` gRPC call that drives the entire event chain (A–F). TV internally calls FD for events D and E; FD internally calls SG for event F. Vector clocks are piggybacked on every request and response in this chain.
- **Services → Orchestrator**: whichever service terminates the flow (TV, FD, or SG) posts the full result (success, reason, vector clock, books) directly to the orchestrator via HTTP POST `/order_result`. The gRPC return chain carries only `{success: bool}` ACKs — no result data travels back through it.
- **Orchestrator → FraudDetection / Suggestions**: gRPC for `InitOrder` and `ClearOrder` only (not for event execution).
- **Orchestrator → OrderQueue**: gRPC `Enqueue` after all verification events pass.
- **OrderExecutor → OrderQueue**: gRPC `TryBecomeLeader`, `RenewLeadership`, `Dequeue`. Two replicas compete; only the elected leader may dequeue.

### Timing and Ordering Guarantees

The system assumes an **asynchronous network** - messages can be delayed arbitrarily but are eventually delivered. There are no timeouts on gRPC calls beyond Python's default. No total ordering of events is guaranteed. Instead, **vector clocks** maintain causal ordering across the three verification services (TV, FD, SG).

Events within one order's lifecycle are partially ordered by `TransactionVerification`'s `ExecuteFlow` method using Python threads:

- A ∥ B (both threads start concurrently)
- A → C (C runs in the same thread as A, after A completes)
- B → D (D runs in the same thread as B, after B - D is a cross-service gRPC call to FD)
- C, D → E (TV calls `FD.RunEventE` only after both threads join; E executes inside FD)
- E → F (FD calls `SG.GenerateSuggestions` from within `RunEventE`; F executes inside SG)

Events A and B are concurrent with respect to each other. All other pairs have a defined happens-before relationship.

### State and Persistence

All state is **in-memory and ephemeral**:
- Each verification service holds a per-order dictionary of vector clocks and cached request data, cleared on `ClearOrder`.
- The order queue holds an in-memory `deque`; it is lost on restart.
- There is no database, no write-ahead log, and no replicated state.

A service restart causes permanent loss of all in-flight order state.

### Failure Modes

| Failure | Effect | Recovery |
|---------|--------|----------|
| Verification service crash (TV, FD, or SG) mid-order | gRPC exception caught by orchestrator → order rejected. Any threads running inside TV die with the process. | Manual restart; no in-flight recovery |
| Orchestrator crash | Client receives no response; order is lost | Manual restart; idempotency not guaranteed |
| Leader executor crash | Lease expires after 5 s; other replica wins `TryBecomeLeader` | Automatic; up to 5 s gap with no dequeuing |
| Both executors crash | Queue accumulates orders; no processing until a replica restarts | Manual restart |
| OrderQueue crash | Enqueue/dequeue calls fail; approved orders lost | Manual restart; queue not durable |
| Network partition between orchestrator and a service | gRPC exception → order fails as above | Resolved when partition heals |

### Fault-Tolerance Properties

- **Single points of failure**: orchestrator, order_queue, and each verification service are each a single instance. Any one crashing halts or rejects all orders touching that service.
- **Limited redundancy**: only `order_executor` runs as two replicas (`scale: 2`), providing failover for order consumption via lease-based election.
- **No split-brain for queue access**: the order_queue service is the single authority for both the queue state and leadership. An executor can only dequeue if it holds the current lease, preventing double-processing.
- **No split-brain for verification**: each verification service is a single instance with an in-memory lock. Concurrent requests for the same order are serialised.

---

## Queue & Executor

**Queue** (`order_queue/src/app.py`)
- Uses Python `deque()` for FIFO ordering
- All critical sections protected by `threading.Lock()`
- **Enqueue**: any caller can add orders
- **Dequeue**: only the current leader can dequeue (enforced at line 63 by comparing `executor_id == self.leader_id`)

**Executor** (`order_executor/src/app.py`)
- Two daemon threads: `election_loop` runs every 2s, `leader_loop` runs every 1s
- Leader dequeues one order per iteration and calls `execute_order()` (simulates work with a 1s sleep)

---

## Leader Election & Mutual Exclusion

Lease-based leader election in `order_queue/src/app.py`:

- **Lease duration**: `LEASE_SECONDS = 5`
- **`TryBecomeLeader()`**: if no live leader, the caller claims leadership and sets expiry to `now + 5s`
- **`RenewLeadership()`**: current leader extends its lease; fails if expired or called by a non-leader
- **Mutual exclusion**: the dequeue RPC rejects any caller that isn't the current `leader_id` - the queue itself is the authority, not a separate lock service

If the leader dies, the lease expires and the next executor to call `TryBecomeLeader` wins. Almost similar to bully algoritm except we don't check for ID, just FCFS

### Execution Sequence

**Initial election.** Both executors start simultaneously and race to claim leadership. The queue grants it to whichever arrives first; the other is told who the current leader is.

```mermaid
sequenceDiagram
    participant E1 as Executor-1
    participant E2 as Executor-2
    participant Q as OrderQueue

    Note over E1,E2: Both start, no leader exists yet
    par
        E1->>Q: TryBecomeLeader(id=E1)
        E2->>Q: TryBecomeLeader(id=E2)
    end
    Note over Q: E1 arrived first — lock acquired
    Q-->>E1: is_leader=true, expiry=now+5s
    Q-->>E2: is_leader=false, leader_id=E1
    Note over E1: Starts leader_loop
    Note over E2: Stays idle, keeps retrying every 2s
```

**Steady state.** The leader dequeues orders and periodically renews its lease. Non-leaders are turned away at the queue.

```mermaid
sequenceDiagram
    participant E1 as Executor-1 (leader)
    participant E2 as Executor-2
    participant Q as OrderQueue

    loop every 1s
        E1->>Q: RenewLeadership(id=E1)
        Q-->>E1: ok, expiry=now+5s
        E1->>Q: Dequeue(executor_id=E1)
        Q-->>E1: order_id=order-42
        Note over E1: execute_order(order-42)
    end

    E2->>Q: TryBecomeLeader(id=E2)
    Q-->>E2: is_leader=false, leader_id=E1

    E2->>Q: Dequeue(executor_id=E2)
    Q-->>E2: has_order=false (not leader)
```

**Leader failure & re-election.** Executor-1 crashes. After the 5s lease expires, Executor-2 wins the next election and takes over.

```mermaid
sequenceDiagram
    participant E1 as Executor-1 (crashed)
    participant E2 as Executor-2
    participant Q as OrderQueue

    Note over E1: Executor-1 crashes — stops renewing
    Note over Q: Lease expires after 5s (no renewal received)

    E2->>Q: TryBecomeLeader(id=E2)
    Note over Q: _leader_alive() → false, granting new lease
    Q-->>E2: is_leader=true, expiry=now+5s

    loop every 1s
        E2->>Q: Dequeue(executor_id=E2)
        Q-->>E2: order_id=order-43
        Note over E2: execute_order(order-43)
        E2->>Q: RenewLeadership(id=E2)
        Q-->>E2: ok, expiry=now+5s
    end
```

---

## Vector Clocks

3-element vector `[TV, FD, SG]` tracked per-order across all services:

| Index | Service | File |
|-------|---------|------|
| 0 | Transaction Verification | `transaction_verification/src/app.py` |
| 1 | Fraud Detection | `fraud_detection/src/app.py` |
| 2 | Suggestions | `suggestions/src/app.py` |

**Merge rule** (identical in all 3 services):
```python
merged = [max(l, r) for l, r in zip(local, received)]
merged[SERVICE_INDEX] += 1
```

**TransactionVerification** (`transaction_verification/src/app.py`) drives the event DAG from within `ExecuteFlow`:
- **ExecuteFlow** itself does a merge-and-increment (TV++) before starting any events
- **A** (VerifyItems), **B** (CheckUserData) - run concurrently in separate threads; each does an internal TV++
- **C** (CheckCard) - runs after A in the same thread; does an internal TV++
- **D** (CheckUserFraud) - runs after B in the same thread; cross-service gRPC call to `FD.RunEventD`
- **E** (CheckCardFraud) - TV calls `FD.RunEventE` after both threads join, passing TV's post-C VC
- **F** (GenerateSuggestions) - FD calls `SG.GenerateSuggestions` from within `RunEventE`

The orchestrator makes a single `TV.ExecuteFlow()` call. It does not track or merge VCs itself. The full result (success, reason, VC, books) is sent directly to the orchestrator via HTTP POST `/order_result` by whichever service terminates the flow — nothing travels back through the gRPC return chain. On cleanup, each service validates the final VC has no rollback via `ClearOrder`.

### Event Dependency DAG

**Diagram 1**: which events are concurrent and which are causally ordered.

```mermaid
graph LR
    A["A: VerifyItems\n[TV]"]
    B["B: CheckUserData\n[TV]"]
    C["C: CheckCard\n[TV]"]
    D["D: CheckUserFraud\n[FD]"]
    E["E: CheckCardFraud\n[FD]"]
    F["F: GenerateSuggestions\n[SG]"]

    A --> C
    B --> D
    C --> E
    D --> E
    E --> F
```

A and B are concurrent (no edge between them). All others have explicit causal dependencies enforced by TV's `ExecuteFlow` (threads + join) and the cross-service call chain (TV → FD → SG).

### VC Execution Trace

**Diagram 2**: one valid execution, showing the vector clock value at each service after every event. VC format: `[TV, FD, SG]`.

The orchestrator makes a single `TV.ExecuteFlow([0,0,0])` call. TV immediately does a merge-and-increment, then launches two concurrent threads. A and B race for TV's lock: A wins, then B, then C. Thread t2 sends TV's post-B VC to `FD.RunEventD`, then FD processes D concurrently with C running in TV. After both threads join, TV calls `FD.RunEventE` with the post-C VC. FD merges its post-D VC with the received post-C VC, then calls `SG.GenerateSuggestions`. SG sends the full result (success, reason, VC, books) **directly to the orchestrator** via HTTP POST `/order_result` and returns a plain ACK to FD. FD and TV also return plain ACKs up the chain — no result data travels back. The final VC `[4,2,1]` reflects 4 TV increments (ExecuteFlow, A, B, C), 2 FD increments (D, E), and 1 SG increment (F).

```mermaid
sequenceDiagram
    participant O  as Orchestrator
    participant TV as TV (index 0)
    participant FD as FD (index 1)
    participant SG as SG (index 2)

    Note over O,SG: Init — all services store initial_vc=[0,0,0]

    O->>TV: ExecuteFlow | send VC=[0,0,0]
    Note over TV: merge([0,0,0],[0,0,0])+TV++ → [1,0,0]

    par Thread t1: A then C
        Note over TV: Event A (VerifyItems)<br/>TV++ → [2,0,0]
        Note over TV: Event C (CheckCard)<br/>TV++ → [4,0,0]
    and Thread t2: B then D
        Note over TV: Event B (CheckUserData)<br/>TV++ → [3,0,0]
        Note over TV: get VC=[3,0,0] to send for D
        TV->>FD: RunEventD | send VC=[3,0,0]
        Note over FD: merge([0,0,0],[3,0,0])+FD++ → [3,1,0]
        Note over TV,FD: C (TV) and D (FD) execute concurrently<br/>— different services, no lock contention
        FD-->>TV: VC=[3,1,0]
    end

    Note over TV: t1.join() ✓  t2.join() ✓<br/>post-C VC=[4,0,0]

    TV->>FD: RunEventE | send VC=[4,0,0]
    Note over FD: FD local=[3,1,0]<br/>merge([3,1,0],[4,0,0])+FD++ → [4,2,0]
    FD->>SG: GenerateSuggestions | send VC=[4,2,0]
    Note over SG: merge([0,0,0],[4,2,0])+SG++ → [4,2,1]
    SG->>O: HTTP POST /order_result | success, reason, VC=[4,2,1], books
    Note over O: result received, event set
    Note over O: final VC=[4,2,1] ✓
```

---

## Logging

No dedicated logging facility, however we use pure stdout `print()` to docker logs with consistent service prefixes:

| Prefix | Service |
|--------|---------|
| `[TV]` | Transaction Verification |
| `[FD]` | Fraud Detection |
| `[SG]` | Suggestions |
| `[Orch]` | Orchestrator |
| `[OrderQueue]` | Order Queue |
| `[Executor {id}]` | Order Executor |

Most log lines include the order ID and current vector clock, e.g.:
```
[TV] Event A (VerifyItems) order-123 | VC=[1, 0, 0]
[Orch] ExecuteFlow complete | final_VC=[4, 2, 1]
```

`PYTHONUNBUFFERED=TRUE` is set in `docker-compose.yaml` for all services so logs appear immediately in container stdout. No log files or aggregation.
