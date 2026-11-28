"""Providers: external execution and decentralized work (issue #63, A66-A69).

Provider-neutral contracts (ExecutionProfile, ExecutionBackend,
WorkerPoolProvider, DecentralizedWorkProvider) plus in-memory simulators
make section 7.2's acceptance tests deterministic. Concrete providers sit
behind these contracts only when a need is documented.
"""

from dev_org.providers.contracts import (
    DEFAULT_CAPABILITIES,
    CapabilityReport,
    DecentralizedWorkProvider,
    ExecutionBackend,
    ExecutionProfile,
    WorkerPoolProvider,
    WorkerPoolSpec,
)
from dev_org.providers.decentralized import (
    HippiusDecentralizedWorkProvider,
    TargonDecentralizedWorkProvider,
    WorkDispatcher,
    verify_result,
)
from dev_org.providers.execution import (
    DirectExecutionBackend,
    IacExecutionBackend,
    KubernetesExecutionBackend,
)
from dev_org.providers.worker_pool import (
    CloudWorkerPoolProvider,
    Organization,
    OrganizationFactory,
    Vm,
)

__all__ = [
    "DEFAULT_CAPABILITIES",
    "CapabilityReport",
    "CloudWorkerPoolProvider",
    "DecentralizedWorkProvider",
    "DirectExecutionBackend",
    "ExecutionBackend",
    "ExecutionProfile",
    "HippiusDecentralizedWorkProvider",
    "IacExecutionBackend",
    "KubernetesExecutionBackend",
    "Organization",
    "OrganizationFactory",
    "TargonDecentralizedWorkProvider",
    "Vm",
    "WorkDispatcher",
    "WorkerPoolProvider",
    "WorkerPoolSpec",
    "verify_result",
]
