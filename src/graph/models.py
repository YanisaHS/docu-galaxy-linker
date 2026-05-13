"""
Graph node and edge data models.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Node:
    id: str
    node_type: str  # document | external | anchor | label | asset
    label: str
    path: Optional[str] = None
    url: Optional[str] = None
    project: Optional[str] = None  # originating project name
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'node_type': self.node_type,
            'label': self.label,
            'path': self.path,
            'url': self.url,
            'project': self.project,
            'metadata': self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'Node':
        return cls(
            id=d['id'],
            node_type=d['node_type'],
            label=d['label'],
            path=d.get('path'),
            url=d.get('url'),
            project=d.get('project'),
            metadata=d.get('metadata', {}),
        )


@dataclass
class Edge:
    source: str
    target: str
    edge_type: str  # doc_link | external_link | link | ref_link | include | image | anchor_link
    label: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'source': self.source,
            'target': self.target,
            'edge_type': self.edge_type,
            'label': self.label,
            'metadata': self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'Edge':
        return cls(
            source=d['source'],
            target=d['target'],
            edge_type=d['edge_type'],
            label=d.get('label', ''),
            metadata=d.get('metadata', {}),
        )
