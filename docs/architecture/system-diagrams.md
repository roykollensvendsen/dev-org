# System diagrams

These diagrams show the MVP architecture described in [the system specification](../../dev-org-specification.md). They are architectural views, not a replacement for the module contracts or the operational configuration. Update the diagrams together with the spec when responsibilities or data flows change.

## Components and responsibilities

![UML component overview with ports on the control service boundary](system-overview.svg)

[Editable PlantUML source](system-overview.puml)

The overview shows the ports as small squares on the boundary of the control service. Inbound ports receive REST, MCP, worker, and webhook traffic. Outbound ports connect the core to storage, board, Git/PR, CI, execution environment, and artifacts. The diagram shows responsibilities and runtime data flow; modules in the control service need not be separate processes.

**Important boundaries:**

- The dashboard and voice/chat client are parallel entry points. The voice app connects directly to MCP; it does not go through the dashboard.
- MCP is one protocol entry with a tool registry and profiles. The groups are modules, not separate server processes. Identity and policy govern each call. Access insight is a read-only module over the same identity and policy decisions; the advance assessment does not perform the action.
- The worker fetches tasks via the Worker API. The agent engine runs isolated and does not receive the control service's secrets. External side effects are enforced by the gateway.
- Local board adapter and A2A are optional or later extensions. GitHub and PostgreSQL are the chosen MVP adapters.

## Ports and adapters

The table concretizes the ports already shown on the control service boundary in the main diagram. The ports are module contracts, not extra network hops. Arrows in the UML image show runtime data flow; the adapters depend on the contracts in code, while the core does not import adapter implementations.

| Direction | Port | MVP adapter(s) | Use |
|---|---|---|---|
| Inbound | REST / API | REST adapter | Dashboard and API clients call use cases through identity and policy. |
| Inbound | MCP | MCP adapter with insight, access, work, message, and optional administration groups | Voice and agent clients only see tools that are qualified and permitted for the identity. The access group reads effective rights and assesses actions without performing them. Every call goes through the same authorization. |
| Inbound | Worker API | Worker adapter | Workers fetch tasks, renew the lease, and deliver checkpoints with their own worker identity. |
| Inbound | Webhook | GitHub webhook adapter | Verified issue and CI events are normalized before they affect internal state. |
| Inbound · later | A2A | External agent adapter | External agent identities must be linked to a trust profile before responses can affect work. |
| Outbound | Persistence | PostgreSQL adapter | Internal task, lease, policy, message, and event state is stored transactionally. |
| Outbound | WorkTracking | GitHub Projects/Issues; local file adapter for development and local workflows | Fetches and updates the backlog via one active board adapter per project. |
| Outbound | Git / PR | GitHub Git/PR adapter | Publishes branch and PR idempotently through the gateway. |
| Outbound | CI status | GitHub Actions adapter | Reads check runs and reconciles webhook results. |
| Outbound | ExecutionBackend | Rootless Podman adapter | Creates and ends an isolated workspace and agent process. |
| Outbound | Artefakter | Artifact adapter | Secures checkpoints, logs, and delivery artifacts with integrity references. |

## Sequence: GitHub issue to verified PR

```mermaid
sequenceDiagram
    autonumber
    actor Human as Human
    participant GH as GitHub Projects/Issues
    participant Hook as Webhook/API
    participant Board as Board adapter
    participant API as API v1
    participant Core as Organization core
    participant Policy as Policy
    participant DB as Persistence / PostgreSQL
    participant Worker as Worker
    participant Runtime as Podman runtime
    participant Agent as Agent adapter / engine
    participant MCP as MCP server
    participant Gateway as Integration gateway
    participant Git as Git/PR adapter
    participant CI as GitHub Actions

    Human->>GH: Creates or prioritizes issue
    GH-->>Hook: Webhook with issue change
    Hook->>Board: Verify and normalize event
    Board->>Core: Changed issue with external ID/revision
    Core->>DB: Store internal Task link and event
    Core->>Policy: Assess whether the issue can be planned
    Policy-->>Core: Allow / deny / approval required
    Core->>DB: Queue allowed work atomically

    Worker->>API: Request work
    API->>Core: Authenticated claim request
    Core->>Policy: Check mandate, profile, and availability
    Policy-->>Core: Allow claim
    Core->>DB: Create lease and fencing token
    DB-->>Worker: Task, mandate, checkpoint references
    Worker->>Runtime: Create isolated workspace
    Runtime-->>Worker: Sandbox ready
    Worker->>Agent: Start engine with task and tool profile
    Agent->>MCP: Read task status / send message (optional)
    MCP->>API: Call with worker identity
    API->>Core: Validated tool call
    Core->>DB: Record message / event
    Core-->>API: Structured result
    API-->>MCP: Structured result
    MCP-->>Agent: Structured response
    Agent-->>Worker: Change proposal and run result
    Worker->>DB: Persist checkpoint and run metadata
    Worker->>Gateway: Request branch/PR publishing
    Gateway->>Policy: Check lease, mandate, and valid evidence
    Policy-->>Gateway: Allow / deny / approval required
    Gateway->>Git: Create branch and PR idempotently
    Git->>GH: Publish branch and PR
    GH-->>Gateway: PR reference
    Gateway->>Board: Record PR link/status
    Board->>GH: Update only owned issue fields
    GH->>CI: Start mandatory checks
    CI-->>Hook: CI status webhook
    Hook->>Core: Verified CI result
    Core->>DB: Record result and correlated events
    Core->>Policy: Assess whether the delivery meets publishing requirements
    Policy-->>Core: Verified / rejected / missing check
    Core->>Gateway: Request issue status and result
    Gateway->>Policy: Check mandate and active ownership
    Policy-->>Gateway: Allow / deny
    Gateway->>Board: Update owned issue fields
    Board->>GH: Write status via adapter
    Core-->>Human: Status visible in board/timeline
```

## Sequence: a human asks a voice app for insight

```mermaid
sequenceDiagram
    autonumber
    actor Human as Human
    participant Voice as ChatGPT Voice / Claude app
    participant MCP as dev-org MCP server
    participant API as API v1
    participant Auth as Identity and policy
    participant Query as Status and insight queries
    participant DB as Persistence / PostgreSQL

    Human->>Voice: "Why is the work stalled?"
    Voice->>MCP: Call relevant insight tool
    MCP->>API: Tool call with user identity and scoping
    API->>Auth: Check identity, role, and project access
    Auth-->>API: Allow read / deny
    API->>Query: Fetch status, timeline, and metrics
    Query->>DB: Read authorized data for project and time period
    DB-->>Query: Results with event and metric references
    Query-->>API: Structured insight and source references
    API-->>MCP: Result within the user's access
    MCP-->>Voice: Structured response with sources and data period
    Voice-->>Human: Explained response with source links
```

## Task life cycle

The diagram shows the authoritative operational states of a task as defined in part 5 of the specification. A wait condition can for example be a user response, an approval, a resource, or an external result. Resume creates at most one continuation for the same event and state.

```mermaid
stateDiagram-v2
    direction TB
    [*] --> Ready

    Ready --> In_progress: Assign and reserve
    In_progress --> Waiting: Store condition and checkpoint
    Waiting --> Ready_for_reprocessing: Condition met
    Ready_for_reprocessing --> In_progress: Create one continuation

    In_progress --> Completed: Criteria verified
    In_progress --> Ready_for_reprocessing: Abort or retry after reconciliation

    Ready --> Paused_or_ended: Pause or end
    In_progress --> Paused_or_ended: Pause or end
    Waiting --> Paused_or_ended: Pause or end
    Ready_for_reprocessing --> Paused_or_ended: Pause or end
    Paused_or_ended --> Ready: Authorized resume
```

**Interpretation:** `In progress` means that one attempt has one active owner with a time-limited reservation and fencing token. The attempt and the reservation have their own life cycles; an expired lease is not a new task state. Before a new attempt or a continuation is started, uncertain external operations are reconciled and the old owner must be stopped or cut off from writing. The engine's conversation ID does not change the task state.

## Authorization flow

The tool profile determines what the client can discover, but does not by itself grant permission. Every call is assessed with verified identity and the concrete action and resource. An approval applies only to the original, unchanged basis.

```mermaid
flowchart TD
    A[Client call] --> B[Verify actor and context]
    B --> C{Identity valid?}
    C -- No --> X[Deny and log]
    C -- Yes --> D[Filter tool catalog]
    D --> E[Call with action and resource]
    E --> F[Check role, scope, and mandate]
    F --> G{Decision}
    G -- Deny --> X
    G -- Approval required --> H[Store scoped request]
    H --> I[Wait for response]
    I --> J{Approved and still valid?}
    J -- No --> X
    J -- Yes --> K[Re-evaluate with approval]
    K --> G
    G -- Allow --> L{External side effect?}
    L -- No --> M[Perform read or local action]
    L -- Yes --> N[Gateway checks mandate, lease, and evidence]
    N --> O{Check passed?}
    O -- No --> X
    O -- Yes --> P[Execute via adapter and log result]
```

## Access insight

Access insight is a read-only use case over identity and policy. One's own access can be inspected by the actor; insight into others requires special mandate. An advance assessment shows what the policy answers now, but does not grant permission for a later execution.

```mermaid
flowchart TD
    A[User or agent] --> B[REST, dashboard, or MCP]
    B --> C[Verify identity and context]
    C --> D[Read-only access request]
    D --> E{Own identity?}
    E -- Yes --> G[Fetch effective access]
    E -- No --> F{Has insight mandate?}
    F -- No --> X[Deny without revealing target]
    F -- Yes --> G
    G --> H[Evaluate with current policy]
    H --> I[Collect scope, conditions, and explanation]
    I --> J[Log insight and policy version]
    J --> K[Return readable response]
    K -. Advance assessment is not permission .-> L[Actual action is re-assessed]
```

The response can show action classes, resource scope, conditions, rationale, policy version, and evaluation time. It never shows credentials or secrets. Insight into other identities cannot be used to bypass project scoping.

## Lease and handover between nodes

The sequence shows controlled movement between workers. The same fencing check applies when a lease expires or an old node returns after a network failure.

```mermaid
sequenceDiagram
    autonumber
    participant Old as Worker A / old owner
    participant CP as Control plane
    participant Store as Persistence and operations journal
    participant Gateway as Integration gateway
    participant Artifacts as Git / artifact store
    participant New as Worker B / new owner

    Old->>CP: Renew lease
    CP->>Store: Check lease
    Store-->>CP: Lease still valid
    CP-->>Old: Renewed
    Old->>CP: Request stop/checkpoint
    CP-->>Old: Stop safely
    Old->>Artifacts: Store work and checkpoint
    Old->>CP: Confirm stop and send link
    CP->>Store: Reconcile operations
    Store-->>CP: Result or waiting status
    alt Operations are safe to take over
        CP->>Store: Swap lease and token atomically
        Store-->>CP: New owner registered atomically
        CP-->>New: Task, checkpoint, token
        New->>Artifacts: Fetch and verify checkpoint
        New->>CP: Confirm takeover
        CP->>Store: Check owner/token
        Store-->>CP: Takeover valid
        CP-->>New: Continue the work
        New->>Gateway: Request side effect
        Gateway->>Store: Check mandate and token
        Store-->>Gateway: Allow or deny
        Gateway-->>New: Result or denial
    else Unknown outcome requires reconciliation
        CP->>Store: Invalidate token and set on hold
        Store-->>CP: No new owner or repeated submission yet
    end

    Old->>Gateway: Delayed call with old token
    Gateway->>Store: Check old token
    Store-->>Gateway: Rejected, owner has been replaced
    Gateway-->>Old: Denial, diagnostics only
```

## Self-improvement loop

The candidate runs with separate state and low-priority, interruptible capacity. Only an independent promotion service can activate changes within the standing framework; ordinary work continues under the active version.

```mermaid
flowchart TD
    A[Operational evidence] --> B[Change proposal and goal]
    B --> C[Check against external framework]
    C --> D{Within mandate?}
    D -- No or unknown --> E[Own decision queue]
    D -- Yes --> F[Isolated candidate]
    F --> G[Independent tests]
    G --> H{Invariants passed?}
    H -- No --> I[Reject candidate, active version continues]
    H -- Yes --> J[Replay historical and synthetic data]
    J --> K[Shadow mode]
    K --> L[Canary with security and flow measurement]
    L --> M{Criteria passed?}
    M -- No --> I
    M -- Yes --> N[Promotion service]
    N --> O[Blue/green, transfer lease]
    O --> P{Health check passed?}
    P -- No --> Q[Rollback, old version continues]
    P -- Yes --> R[Activate new version and log result]
    R --> A
```

## Diagram scope and remaining contracts

The diagrams show selected normal flows. Retry, expired lease, duplicate webhooks, CI reconciliation, and unresolved external calls follow the normative rules in parts 3.2 and 5–7 of [the specification](../../dev-org-specification.md); they should not be copied in here as parallel rules.

The architecture decision for external mutations is closed: the organization core owns the use case and asks the gateway to perform the change; only the gateway calls mutating adapter operations. The GitHub issue sequence shows this flow.

The following versioned contract artifacts must be finalized before the corresponding adapter is implemented. The spec fixes the semantics; the routes, serialized schemas, and adapter-specific configuration values belong in these contracts.

| Contract artifact | Already fixed | To concretize before |
|---|---|---|
| Worker API | Claim, lease/fencing, checkpoint, result, stop, and handover rules in parts 5 and 7. | Worker adapter: operations, payloads, errors, authentication, idempotency, and retry response. |
| `Task`, `Attempt` and `Reservation` | Task, attempt, and reservation are separate concepts; life cycle and ownership rules are described in part 5. | Persistence and worker adapter: versioned fields, IDs, relations, and migration rules. They must not be merged into one state machine. |
| Checkpoint and artifact reference | Required checkpoint content, integrity check, and move principles in parts 5 and 7. | Artifact/worker adapter: reference schema, upload/download, retention, and error handling. |
| MCP tool catalog | Versioned groups, access rules, and use cases are described in parts 3.2 and 4. | MCP adapter: exact tool names, input/output schema, errors, and pagination where needed. |
| Board status mapping | Common statuses are `Ready`, `In progress`, `Blocked`, `In review`, and `Done`; unknown status automatically stops assignment. | Project setup/board adapter: concrete GitHub field IDs and alternate IDs, validated against the chosen project before activation. |

Availability of custom MCP servers in a particular voice app is a client/vendor limitation, not an open architecture decision. It is discussed in part 4; other compatible MCP clients use the same entry point.