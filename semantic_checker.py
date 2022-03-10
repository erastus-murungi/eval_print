import sys
import traceback
from dataclasses import dataclass
from typing import Optional

from ast_nodes import Expression, Store, Node, Declaration
from exc_processor import ExceptionProcessor, ProcessingException


@dataclass
class Env(dict[str, Expression]):
    parent: Optional["Env"] = None
    child: Optional["Env"] = None

    def __hash__(self):
        return hash(id(self))

    def copy(self) -> "Env":
        entries = super(Env, self).copy()
        env = Env(self.parent, self.child)
        env.update(entries)
        return env

    def add_child(self) -> "Env":
        env_copy = self.copy()
        self.child = env_copy
        env_copy.parent = self
        return env_copy


class SemanticChecker:
    def __init__(
        self, nodes: list[Store | Expression], exception_processor: ExceptionProcessor
    ):
        self.exception_processor = exception_processor
        self.exceptions: list[ProcessingException] = []
        self.node_to_env = self.populate_env(nodes)
        self.check_scope(nodes)
        self.node_types = self.evaluate_types(nodes)
        self.check_exceptions()

    def check_exceptions(self):
        if len(self.exceptions) != 0:
            for exception in self.exceptions:
                exc, tb = exception
                print(exc, file=sys.stderr)
                print(*tb, file=sys.stderr)

    @staticmethod
    def populate_env(
        nodes: list[Store | Expression],
    ) -> dict[Node, Env]:
        env = Env()
        node_to_env = {}
        seen = set()
        for node in nodes:
            if isinstance(node, Store):
                if node.id.var in seen:
                    raise ValueError("redeclared binding")
                seen.add(node.id.var)
                env[node.id.var] = node.expr
                env = env.add_child()
            elif not isinstance(node, Expression):
                raise ValueError
            node_to_env[node] = env
        return node_to_env

    def check_scope(self, nodes):
        def _check_scope_for_node(node: Node, env: dict[str, Expression]):
            if isinstance(node, Declaration):
                if node.var not in env:
                    raise ValueError(f"binding '{node.var}' not defined")
            if node.children() is not None:
                children: tuple[Node, ...] = node.children()
                for child in children:
                    _check_scope_for_node(child, env)

        for root_node in nodes:
            if isinstance(root_node, Expression):
                _check_scope_for_node(root_node, self.node_to_env[root_node])

    def evaluate_types(self, nodes: list[Node]):
        types = {}
        for root_node in nodes:
            root_node.evaluate_type(
                types,
                self.node_to_env[root_node],
                self.exception_processor,
                self.exceptions,
            )
        return types