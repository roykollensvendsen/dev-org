"""Gateway module: the only path for external side effects."""

from dev_org.gateway.a2a import A2A_PROTOCOL, A2AAdapter, AgentCard
from dev_org.gateway.github import GitHubAdapter
from dev_org.gateway.migration import BoardMigration, MigrationReport
from dev_org.gateway.protocol import BoardAdapter, Gateway, GitPrAdapter
from dev_org.gateway.redmine import WORK_V1, InMemoryRedmine, RedmineAdapter
from dev_org.gateway.service import ExternalOperation, GatewayService, OperationJournal

__all__ = [
    "A2A_PROTOCOL",
    "WORK_V1",
    "A2AAdapter",
    "AgentCard",
    "BoardAdapter",
    "BoardMigration",
    "ExternalOperation",
    "Gateway",
    "GatewayService",
    "GitHubAdapter",
    "GitPrAdapter",
    "InMemoryRedmine",
    "MigrationReport",
    "OperationJournal",
    "RedmineAdapter",
]
