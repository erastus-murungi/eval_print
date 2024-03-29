import cmath
import math
import operator as op
import sys
import traceback
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from enum import IntEnum, auto
from numbers import Number
from typing import Callable, Optional

import termcolor


class Type(IntEnum):
    Integer = 0
    Float = 1
    Complex = 2
    Undefined = 3
    Error = 4

    def __repr__(self):
        return self.name


@dataclass(frozen=True)
class TokenLocation:
    filename: str
    line: int
    col: int
    offset: int

    def __str__(self):
        return f"<{self.filename}:{self.line}:{self.col}>"


@dataclass
class Env(set[str]):
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


class State(IntEnum):
    SOURCE_CODE_READ = auto()
    LEXICAL_ANALYSIS_COMPLETE = auto()
    SYNTACTIC_ANALYSIS_COMPLETE = auto()
    SEMANTIC_ANALYSIS_COMPLETE = auto()
    EVALUATION_COMPLETE = auto()
    ERROR = auto()


# Type aliases
NodeToValueMapping = dict["Node", Optional[Number | list[Number]]]
NodeToTypeMapping = dict["Node", Type | list[Type]]
NodeToEnvMapping = dict["Node", Env]


# A container class which should answer most questions
class EPContext:
    def __init__(self):
        self._state_to_exceptions = defaultdict(list)
        self._source_code: str = ""
        self._state: State = State.SOURCE_CODE_READ
        self._exception_processor: Optional[ExceptionProcessor] = None
        self._node_to_value_mapping: Optional[NodeToValueMapping] = None
        self._node_to_env_mapping: Optional[NodeToEnvMapping] = None
        self._node_to_type_mapping: Optional[NodeToTypeMapping] = None
        self._global_env: dict[str, Callable] = self.populate_global_env()

    @staticmethod
    def populate_global_env():
        global_env = {
            name: func for name, func in vars(math).items() if not name.startswith("_")
        }
        global_env.update(
            {
                f"c_{name}": func
                for name, func in vars(cmath).items()
                if not name.startswith("_")
            }
        )
        global_env.update({"max": max})
        global_env.update({"min": min})
        return global_env

    def get_global_env(self):
        return self._global_env

    def set_source_code(self, source_code: str):
        self._source_code = source_code

    def get_source_code(self):
        return self._source_code

    def record_exception(self, exception):
        self._state_to_exceptions[self._state].append(exception)

    def set_exception_processor(self, exception_processor: "ExceptionProcessor"):
        if not isinstance(exception_processor, ExceptionProcessor):
            raise ValueError()
        self._exception_processor = exception_processor

    def get_exception_processor(self):
        if self._exception_processor is None:
            raise AttributeError("exception processor not set")
        return self._exception_processor

    def set_state(self, state: State):
        if not isinstance(state, State):
            raise ValueError()
        if self._state != State.ERROR:
            self._state = state

    def set_node_to_value_mapping(self, node_to_value_mapping: NodeToValueMapping):
        if (
            not isinstance(node_to_value_mapping, dict)
            or not all(isinstance(key, Node) for key in node_to_value_mapping.keys())
            or not all(
                None or isinstance(value, Number)
                for value in node_to_value_mapping.values()
            )
        ):
            raise ValueError()
        self._node_to_value_mapping = node_to_value_mapping

    def get_node_to_value_mapping(self):
        if self._node_to_value_mapping is not None:
            return self._node_to_value_mapping
        raise AttributeError()

    def set_node_to_env_mapping(self, node_to_env_mapping: NodeToEnvMapping):
        if (
            not isinstance(node_to_env_mapping, dict)
            or not all(isinstance(key, Node) for key in node_to_env_mapping.keys())
            or not all(isinstance(value, Env) for value in node_to_env_mapping.values())
        ):
            raise ValueError()
        self._node_to_env_mapping = node_to_env_mapping

    def get_node_to_env_mapping(self):
        if self._node_to_env_mapping is not None:
            return self._node_to_env_mapping
        raise AttributeError()

    def get_node_to_type_mapping(self):
        if self._node_to_type_mapping is not None:
            return self._node_to_type_mapping
        raise AttributeError()

    def set_node_to_type_mapping(self, node_to_type_mapping: NodeToTypeMapping):
        if (
            not isinstance(node_to_type_mapping, dict)
            or not all(isinstance(key, Node) for key in node_to_type_mapping.keys())
            or not all(
                isinstance(value, Type) or isinstance(value, list)
                for value in node_to_type_mapping.values()
            )
        ):
            raise ValueError()
        self._node_to_type_mapping = node_to_type_mapping


@dataclass(frozen=True)
class Node(ABC):
    start_location: TokenLocation = field(repr=False, hash=False)

    def is_terminal(self):
        return len(self.children()) == 0

    @abstractmethod
    def children(self) -> tuple["Node", ...]:
        pass

    @abstractmethod
    def evaluate_type(self, ep_context: EPContext):
        pass

    @abstractmethod
    def evaluate(self, ep_context: EPContext):
        pass

    @abstractmethod
    def source(self):
        pass


@dataclass(frozen=True)
class Expression(Node, ABC):
    pass


@dataclass(frozen=True)
class Parenthesized(Expression):
    body: Expression

    def evaluate(self, ep_context: EPContext):
        self.body.evaluate(ep_context)
        values = ep_context.get_node_to_value_mapping()
        values[self] = values[self.body]

    def children(self):
        return (self.body,)

    def evaluate_type(self, ep_context: EPContext):
        self.body.evaluate_type(ep_context)
        node_to_type_mapping = ep_context.get_node_to_type_mapping()
        node_to_type_mapping[self] = node_to_type_mapping[self.body]

    def source(self):
        return f"({self.body.source()})"


@dataclass(frozen=True, unsafe_hash=True)
class Value(Expression, ABC):
    @abstractmethod
    def literals(self):
        pass


@dataclass(frozen=True, unsafe_hash=True, eq=False)
class RValue(Value):
    _literal: str

    def evaluate_type(self, ep_context: EPContext):
        pass

    def evaluate(self, ep_context: EPContext):
        pass

    def children(self):
        return ()

    def __eq__(self, other):
        return self.literals() == other.literals()

    def literals(self):
        return (self._literal,)

    def source(self):
        if isinstance(self._literal, str):
            return f"{self._literal}"
        else:
            return f'{{{", ".join(self._literal)}}}'


@dataclass(frozen=True)
class LValue(Value, ABC):
    pass


@dataclass(frozen=True)
class RealNumber(Value, ABC):
    raw_value: float

    @staticmethod
    @abstractmethod
    def get_type() -> Type:
        pass

    @abstractmethod
    def get_raw_value(self):
        pass


@dataclass(frozen=True)
class FloatLiteral(RealNumber):
    _literal: str

    def source(self):
        return str(self.raw_value)

    def literals(self):
        return (self._literal,)

    def update_values(self, ep_context: EPContext):
        pass

    def get_raw_value(self):
        return self.raw_value

    @staticmethod
    def get_type() -> Type:
        return Type.Float

    def evaluate(self, ep_context: EPContext):
        values = ep_context.get_node_to_value_mapping()
        values[self] = self.raw_value

    def evaluate_type(self, ep_context: EPContext):
        types = ep_context.get_node_to_type_mapping()
        types[self] = FloatLiteral.get_type()

    def children(self):
        return ()


@dataclass(frozen=True)
class IntLiteral(RealNumber, ABC):
    _literal: str

    def literals(self):
        return (self._literal,)

    def source(self):
        return self._literal

    def update_values(self, ep_context: EPContext):
        pass

    def children(self):
        return ()

    def evaluate_type(self, ep_context: EPContext):
        types = ep_context.get_node_to_type_mapping()
        types[self] = IntLiteral.get_type()

    def evaluate(self, ep_context: EPContext):
        values = ep_context.get_node_to_value_mapping()
        values[self] = self.raw_value

    @staticmethod
    def get_type() -> Type:
        return Type.Integer

    def get_raw_value(self):
        return self.raw_value


class DecimalLiteral(IntLiteral):
    pass


class HexLiteral(IntLiteral):
    pass


class BinLiteral(IntLiteral):
    pass


class OctLiteral(IntLiteral):
    pass


@dataclass(frozen=True)
class ComplexLiteral(LValue):
    literal: str
    real: RealNumber
    imag: RealNumber

    def source(self):
        return f"complex({self.real}, {self.imag})"

    def literals(self):
        return str(complex(self.real.source(), self.imag.source()))

    def children(self) -> tuple[Node, ...]:
        pass

    def evaluate_type(self, ep_context: EPContext):
        types = ep_context.get_node_to_type_mapping()
        types[self] = Type.Complex

    def evaluate(self, ep_context: EPContext):
        val = complex(real=self.real.get_raw_value(), imag=self.imag.get_raw_value())
        values = ep_context.get_node_to_value_mapping()
        values[self] = val


@dataclass(frozen=True)
class ExprVector(Expression):
    expressions: tuple[Expression, ...]

    def children(self) -> tuple["Node", ...]:
        return tuple(self.expressions)

    def evaluate_type(self, ep_context: EPContext):
        node_to_type_mapping = ep_context.get_node_to_type_mapping()
        for expr in self.expressions:
            expr.evaluate_type(ep_context)
        node_to_type_mapping[self] = [
            node_to_type_mapping[expr] for expr in self.expressions
        ]

    def evaluate(self, ep_context: EPContext):
        node_to_value = ep_context.get_node_to_value_mapping()
        node_to_value[self] = [expr.evaluate(ep_context) for expr in self.expressions]

    def source(self):
        return f"{{{', '.join(expr.source() for expr in self.expressions)}}}"

    def __len__(self):
        return len(self.expressions)


@dataclass(frozen=True)
class RValueVector(Value):
    stores: tuple[RValue, ...]

    def children(self) -> tuple["Node", ...]:
        return self.stores

    def evaluate_type(self, ep_context: EPContext):
        pass

    def evaluate(self, ep_context: EPContext):
        pass

    def literals(self):
        return [store._literal for store in self.stores]

    def source(self):
        return f"{{{', '.join(store.source() for store in self.stores)}}}"

    def __len__(self):
        return len(self.stores)


@dataclass(frozen=True)
class Store(Node):
    id: RValue | RValueVector
    expr: Expression

    def source(self):
        return f"const {self.id.source()} := {self.expr.source()}"

    def evaluate_type(self, ep_context: EPContext):
        self.id.evaluate_type(ep_context)
        self.expr.evaluate_type(ep_context)
        types = ep_context.get_node_to_type_mapping()
        types[self] = Type.Undefined
        if isinstance(self.id, RValueVector):
            type_expr = types[self.expr]
            assert isinstance(type_expr, list)
            for binding, binding_type in zip(self.id.stores, type_expr):
                types[binding] = binding_type
        else:
            types[self.id] = types[self.expr]

    def evaluate(self, ep_context: EPContext):
        self.expr.evaluate(ep_context)
        values = ep_context.get_node_to_value_mapping()
        if isinstance(self.id, RValueVector):
            value_expr = values[self.expr]
            assert isinstance(value_expr, list)
            for binding, binding_type in zip(self.id.stores, value_expr):
                values[binding] = binding_type
        else:
            values[self.id] = values[self.expr]
        values[self] = None

    def children(self):
        return self.id, self.expr


@dataclass(frozen=True)
class Load(Expression):
    id: Value

    def update_values(self, ep_context: EPContext):
        node_to_value_mapping = ep_context.get_node_to_value_mapping()
        # node_to_env_mapping = ep_context.get_node_to_env_mapping()
        # env = node_to_env_mapping[self]
        # for literal in self.id.literals():
        #     if literal not in env:
        #         exception_processor = ep_context.get_exception_processor()
        #         exception_processor.raise_scope_error(
        #             ep_context, self.start_location, literal
        #         )
        node_to_value_mapping[self] = node_to_value_mapping[self.id]
        return node_to_value_mapping[self]

    def source(self):
        return self.id.source()

    def evaluate(self, ep_context: EPContext):
        return self.update_values(ep_context)

    def evaluate_type(self, ep_context: EPContext):
        node_to_type_mapping = ep_context.get_node_to_type_mapping()
        self.id.evaluate_type(ep_context)
        node_to_type_mapping[self] = node_to_type_mapping[self.id]

    def children(self) -> tuple[Node, ...]:
        return ()


class Operator(Node, ABC):
    def update_values(self, ep_context: EPContext):
        pass

    def children(self) -> tuple[Node, ...]:
        return ()

    def evaluate(self, ep_context: EPContext):
        pass

    def evaluate_type(self, ep_context: EPContext):
        types = ep_context.get_node_to_type_mapping()
        types[self] = Type.Undefined


@dataclass(frozen=True)
class UnaryOperator(Operator):
    lexeme: str
    str_to_op = {"+": lambda x: x, "-": op.neg}

    def source(self):
        return self.lexeme

    def evaluate_with_operand(self, operand):
        return self.str_to_op[self.lexeme](operand)

    def __post_init__(self):
        if self.lexeme not in self.str_to_op:
            raise ValueError(f"unrecognized unary op {self.lexeme}")


@dataclass(frozen=True)
class UnaryOp(Expression):
    op: UnaryOperator
    operand: Expression

    def update_values(self, ep_context: EPContext):
        pass

    def source(self):
        return f"{self.op.source()}{self.operand.source()}"

    def evaluate(self, ep_context: EPContext):
        self.operand.evaluate(ep_context)
        values = ep_context.get_node_to_value_mapping()
        value = self.op.evaluate_with_operand(values[self.operand])
        values[self] = value

    def evaluate_type(self, ep_context: EPContext):
        self.op.evaluate_type(ep_context)
        self.operand.evaluate_type(ep_context)
        types = ep_context.get_node_to_type_mapping()
        types[self] = types[self.operand]

    def children(self) -> tuple[Node, ...]:
        return self.op, self.operand


@dataclass(frozen=True)
class BinaryOperator(Operator):
    lexeme: str
    str_to_op = {
        "+": op.add,
        "-": op.sub,
        "*": op.mul,
        "/": op.truediv,
        "//": op.floordiv,
        "^": op.pow,
    }

    def eval_with_operands(self, lhs: Number, rhs: Number) -> Number:
        func = self.str_to_op[self.lexeme]
        return func(lhs, rhs)

    def __post_init__(self):
        if self.lexeme not in self.str_to_op:
            raise ValueError(f"unrecognized binary op {self.lexeme}")

    def source(self):
        return self.lexeme


@dataclass(frozen=True)
class BinaryOp(Expression):
    op: BinaryOperator
    left: Expression
    right: Expression

    def update_values(self, ep_context: EPContext):
        pass

    def source(self):
        return f"{self.left.source()} {self.op.source()} {self.right.source()}"

    def evaluate(self, ep_context: EPContext):
        values = ep_context.get_node_to_value_mapping()
        self.left.evaluate(ep_context)
        self.right.evaluate(ep_context)
        self.op.evaluate(ep_context)
        value = self.op.eval_with_operands(values[self.left], values[self.right])
        values[self] = value

    def evaluate_type(self, ep_context: EPContext):
        self.left.evaluate_type(ep_context)
        self.right.evaluate_type(ep_context)
        self.op.evaluate_type(ep_context)
        node_to_type_mapping = ep_context.get_node_to_type_mapping()
        if node_to_type_mapping[self.left] != node_to_type_mapping[self.right]:
            exception_processor = ep_context.get_exception_processor()
            ep_context.record_exception(
                exception_processor.raise_exception(
                    ep_context,
                    self,
                    self.start_location,
                    f"{node_to_type_mapping[self.left]} and {node_to_type_mapping[self.right]}",
                )
            )
            node_to_type_mapping[self] = Type.Error
        else:
            node_to_type_mapping[self] = node_to_type_mapping[self.left]

    def children(self) -> tuple[Node, ...]:
        return self.left, self.op, self.right


@dataclass(frozen=True)
class FunctionDef(Node):
    name: str
    parameters: tuple[RValue, ...]
    body: Expression

    def source(self):
        return f"def {self.name}({', '.join([arg.source() for arg in self.parameters])}) := {self.body.source()}"

    def evaluate_type(self, ep_context: EPContext):
        types = ep_context.get_node_to_type_mapping()
        types[self] = Type.Undefined

    def evaluate(self, ep_context: EPContext):
        values = ep_context.get_node_to_value_mapping()
        values[self] = None

    def children(self) -> tuple[Node, ...]:
        return self.body.children()


@dataclass(frozen=True)
class PyFunctionCall(Expression):
    func_name: str
    py_function: Callable
    arguments: tuple[Expression, ...]

    def children(self) -> tuple[Node, ...]:
        return ()

    def evaluate_type(self, ep_context: EPContext):
        node_to_type_mapping = ep_context.get_node_to_type_mapping()
        node_to_type_mapping[self] = (
            Type.Complex if self.func_name.startswith("c_") else Type.Float
        )
        _type = Type.Undefined

        for argument in self.arguments:
            argument.evaluate_type(ep_context)

        if self.arguments:
            if not FunctionCall.all_same_type(self.arguments, ep_context):
                exception_processor = ep_context.get_exception_processor()
                exception_processor.raise_a_type_mismatch_exception(
                    self.arguments, node_to_type_mapping, self.start_location
                )

    def evaluate(self, ep_context: EPContext):
        node_to_value = ep_context.get_node_to_value_mapping()
        for arg in self.arguments:
            arg.evaluate(ep_context)
        args = tuple(node_to_value[arg] for arg in self.arguments)
        try:
            res = self.py_function(*args)
            node_to_value[self] = res
            return res
        except TypeError as e:
            ep_context.get_exception_processor().raise_evaluation_error(
                self.start_location, str(e)
            )

    def source(self):
        return f"{self.py_function.__name__}({', '.join([arg.source() for arg in self.arguments])})"


@dataclass(frozen=True)
class FunctionCall(Expression):
    function_def: FunctionDef
    arguments: tuple[Expression, ...]

    def source(self):
        return f"{self.function_def.name}({', '.join([arg.source() for arg in self.arguments])})"

    def children(self) -> tuple["Node", ...]:
        return self.function_def.body.children()

    def evaluate(self, ep_context: EPContext):
        node_to_value = ep_context.get_node_to_value_mapping()
        for param, arg in zip(self.function_def.parameters, self.arguments):
            arg.evaluate(ep_context)
            node_to_value[param] = node_to_value[arg]
        self.function_def.body.evaluate(ep_context)
        node_to_value[self] = node_to_value[self.function_def.body]

    @staticmethod
    def get_all_l_values(root: Node):
        def recurse_on_children(node):
            children = node.children()
            return children + tuple(map(recurse_on_children, children))

        return tuple(
            filter(
                lambda n: isinstance(n, LValue),
                recurse_on_children(root),
            )
        )

    @staticmethod
    def all_same_type(elements, ep_context: EPContext):
        types = ep_context.get_node_to_type_mapping()
        first_type = types[elements[0]]
        return all(types[sub] == first_type for sub in elements[1:])

    def evaluate_type(self, ep_context: EPContext):
        node_to_type_mapping = ep_context.get_node_to_type_mapping()

        _type = Type.Undefined
        all_constants = self.get_all_l_values(self.function_def.body)
        for constant in all_constants:
            constant.evaluate_type(node_to_type_mapping, ep_context)
        for argument in self.arguments:
            argument.evaluate_type(ep_context)
        for param, arg in zip(self.function_def.parameters, self.arguments):
            node_to_type_mapping[param] = node_to_type_mapping[arg]
        self.function_def.body.evaluate_type(ep_context)
        ret_type = node_to_type_mapping[self.function_def.body]
        if all_constants:
            if not self.all_same_type(all_constants, ep_context):
                raise ValueError()
            else:
                _type = all_constants[0].get_type()
        if self.arguments:
            if not self.all_same_type(self.arguments, ep_context):
                exception_processor = ep_context.get_exception_processor()
                exception_processor.raise_a_type_mismatch_exception(
                    self.arguments, node_to_type_mapping, self.start_location
                )
            else:
                type_args = node_to_type_mapping[self.arguments[0]]
                if _type != Type.Undefined and type_args != _type:
                    raise ValueError
                _type = type_args
        node_to_type_mapping[self] = ret_type
        return ret_type


@dataclass(frozen=True)
class LetIn(Expression):
    bindings: tuple[tuple[RValue, Expression], ...]
    ret: Expression

    def children(self) -> tuple["Node", ...]:
        return tuple(node for nodes in self.bindings for node in nodes) + (self.ret,)

    def evaluate_type(self, ep_context: EPContext):
        types = ep_context.get_node_to_type_mapping()
        for binding_name, expr in self.bindings:
            binding_name.evaluate_type(ep_context)
            expr.evaluate_type(ep_context)
            types[binding_name] = types[expr]
        self.ret.evaluate_type(ep_context)
        types[self] = types[self.ret]

    def evaluate(self, ep_context: EPContext):
        values = ep_context.get_node_to_value_mapping()
        for binding_name, expr in self.bindings:
            binding_name.evaluate(ep_context)
            expr.evaluate(ep_context)
            values[binding_name] = values[expr]
        self.ret.evaluate(ep_context)
        values[self] = values[self.ret]

    def source(self):
        return (
            " ".join(
                f"\n            let {var.source()} := {expr.source()} in"
                for var, expr in self.bindings
            )
            + f"\n             return {self.ret.source()}"
        )


class ProcessingException(Exception):
    pass


class ExceptionProcessor:
    def __init__(self, string: str, filename: str):
        self.string = string
        self.lines: list[str] = self.string.split("\n")
        self.filename = filename

    def raise_exception(
        self, ep_context: EPContext, ob: object, loc: TokenLocation, message: str
    ):
        line = self.lines[loc.line]
        try:
            raise ProcessingException(
                f"{line}\n from {ob.__class__.__qualname__} : {message}"
            )
        except ProcessingException as e:
            ep_context.set_state(State.ERROR)
            return e, traceback.format_stack()

    def get_problematic_line_str(self, line_number) -> str:
        return f"    {line_number} | {self.lines[line_number]}\n"

    def raise_a_type_mismatch_exception(
        self, args: tuple[Expression, ...], types, loc: TokenLocation
    ):
        line = self.lines[loc.line]
        s = termcolor.colored("error:", "red")
        print(
            f"{termcolor.colored('[✗ TypeMismatch]', 'red')}\n"
            f"{loc}: {s} arguments must all be of the same type \n"
            f"     {loc.line} | {line}\n\n"
            f"The statically evaluated types of your arguments are:\n"
            + "\n".join(
                [
                    f"  {arg.source()} => {termcolor.colored(str(types[arg].name), 'magenta')}"
                    for arg in args
                ]
            )
        )
        sys.exit(1)

    def raise_evaluation_error(self, loc: TokenLocation, message: str):
        problematic_line = self.get_problematic_line_str(loc.line)
        s = termcolor.colored("error:", "red")
        print(
            f"[✗ EvaluationRuntimeError]\n"
            f"{loc}: {s} evaluation error \n"
            f"      {message}\n"
            f"      {problematic_line}\n"
        )
        sys.exit(1)

    def raise_parsing_error(
        self, ep_context: EPContext, token, message: str, expected_type
    ):
        loc = token.loc
        problematic_line = self.get_problematic_line_str(loc.line)
        s = termcolor.colored("error:", "red")
        print(
            f"{termcolor.colored('[✗ ParsingError]', 'red')} {message}\n"
            f"                 {loc}: {s} expected {expected_type} got {token.token_type}\n"
            + problematic_line
            + f"{''.join(' ' * problematic_line.index(token.lexeme))}{termcolor.colored('^' * len(token.lexeme), 'magenta')}"
        )
        ep_context.set_state(State.ERROR)
        sys.exit(1)

    def raise_scope_error(self, ep_context: EPContext, loc, identifier: str):
        generic_message = f'use of undeclared identifier "{identifier}"'
        problematic_line = self.get_problematic_line_str(loc.line)
        s = termcolor.colored("error:", "red")
        print(
            f"[✗ ScopeError]"
            f"{loc}: {s} {generic_message} \n"
            + problematic_line
            + f"{''.join(' ' * problematic_line.index(identifier))}{termcolor.colored('^' * len(identifier), 'magenta')}"
        )
        ep_context.set_state(State.ERROR)
        sys.exit(1)
