"""Gateway module: the only path for external side effects."""

from dev_org.gateway.github import GitHubAdapter
from dev_org.gateway.protocol import BoardAdapter, Gateway, GitPrAdapter
from dev_org.gateway.service import ExternalOperation, GatewayService, OperationJournal

__all__ = [
    "BoardAdapter",
    "ExternalOperation",
    "Gateway",
    "GatewayService",
    "GitHubAdapter",
    "GitPrAdapter",
    "OperationJournal",
]
