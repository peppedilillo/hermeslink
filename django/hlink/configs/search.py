from abc import ABC
from abc import abstractmethod
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from enum import auto
from enum import Enum
import re

from configs.models import Configuration
from django.db.models import Q
from django.utils import timezone


def interpret_search_query(query: str):
    """Interprets a search query string into a django filter query."""
    tokens = Scanner(query).scan_tokens()
    ast = Parser(tokens).parse()
    filter_query = Interpreter().evaluate(ast)
    return filter_query


class TokenType(Enum):
    """Token types for the test report lexer."""

    MODEL_H1 = auto()
    MODEL_H2 = auto()
    MODEL_H3 = auto()
    MODEL_H4 = auto()
    MODEL_H5 = auto()
    MODEL_H6 = auto()
    CONFG_ACQ = auto()
    CONFG_ACQ0 = auto()
    CONFG_ASIC0 = auto()
    CONFG_ASIC1 = auto()
    CONFG_BEE = auto()
    CONFG_LIKTRG = auto()
    CONFG_OBS = auto()

    MODEL = auto()
    UPLINKED = auto()
    SUBMITTED = auto()

    EQUAL = auto()
    BANG_EQUAL = auto()
    GREATER = auto()
    GREATER_EQUAL = auto()
    LESSER = auto()
    LESSER_EQUAL = auto()
    NOT = auto()
    OR = auto()
    AND = auto()
    BY = auto()
    ISNULL = auto()

    LEFT_PAREN = auto()
    RIGHT_PAREN = auto()

    DATETIME = auto()
    LITERAL = auto()
    TRUE = auto()
    FALSE = auto()

    EOF = auto()


RESERVED_WORDS_SPACECRAFT_NAMES = {
    "h1": TokenType.MODEL_H1,
    "h2": TokenType.MODEL_H2,
    "h3": TokenType.MODEL_H3,
    "h4": TokenType.MODEL_H4,
    "h5": TokenType.MODEL_H5,
    "h6": TokenType.MODEL_H6,
}
RESERVED_WORDS_SPACECRAFT_NAMES_INVERSE = {
    TokenType.MODEL_H1: Configuration.MODELS[0][0],
    TokenType.MODEL_H2: Configuration.MODELS[1][0],
    TokenType.MODEL_H4: Configuration.MODELS[3][0],
    TokenType.MODEL_H5: Configuration.MODELS[4][0],
    TokenType.MODEL_H6: Configuration.MODELS[5][0],
    TokenType.MODEL_H3: Configuration.MODELS[2][0],
}

RESERVED_WORDS_CONFIGURATION_NAMES = {
    "acq": TokenType.CONFG_ACQ,
    "acq0": TokenType.CONFG_ACQ0,
    "asic0": TokenType.CONFG_ASIC0,
    "asic1": TokenType.CONFG_ASIC1,
    "bee": TokenType.CONFG_BEE,
    "liktrg": TokenType.CONFG_LIKTRG,
    "obs": TokenType.CONFG_OBS,
}
# these are sort of hard-coded. the values should `Configuration` field names
RESERVED_WORDS_CONFIGURATION_NAMES_INVERSE = {v: k for k, v in RESERVED_WORDS_CONFIGURATION_NAMES.items()}

RESERVED_WORDS = (
    RESERVED_WORDS_SPACECRAFT_NAMES
    | RESERVED_WORDS_CONFIGURATION_NAMES
    | {
        "uplinked": TokenType.UPLINKED,
        "submitted": TokenType.SUBMITTED,
        "by": TokenType.BY,
        "or": TokenType.OR,
        "and": TokenType.AND,
        "not": TokenType.NOT,
    }
)

DATETIME_PATTERNS = OrderedDict(
    sorted(
        [
            (r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", 20),
            (r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$", 19),
            (r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$", 17),
            (r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$", 16),
            (r"^\d{4}-\d{2}-\d{2}$", 10),
        ],
        key=lambda x: x[1],
        reverse=True,
    )
)


@dataclass
class Token:
    """A lexical token with type and content."""

    ttype: TokenType
    lexeme: str


class Scanner:
    """Tokenizes a query string"""

    def __init__(self, text: str):
        self.text = text
        self.token_list = []
        self.start = 0
        self.current = 0
        self.column = 0

    def scan_tokens(self) -> list[Token]:
        """Scans through input and returns a list of tokens"""
        while not self._at_end():
            self.start = self.current
            self._scan_token()
        self._add_token(Token(TokenType.EOF, ""))
        return self.token_list

    def _scan_token(self):
        """Catches a single token."""
        c = self._advance()
        if c == "=":
            self._add_token(Token(TokenType.EQUAL, "="))
        elif c == "(":
            self._add_token(Token(TokenType.LEFT_PAREN, "("))
        elif c == ")":
            self._add_token(Token(TokenType.RIGHT_PAREN, ")"))
        elif c.isspace():
            pass
        elif c == ">":
            self._add_token(Token(TokenType.GREATER_EQUAL, ">=") if self._match("=") else Token(TokenType.GREATER, ">"))
        elif c == "<":
            self._add_token(Token(TokenType.LESSER_EQUAL, "<=") if self._match("=") else Token(TokenType.LESSER, "<"))
        elif c == "!":
            self._add_token(Token(TokenType.BANG_EQUAL, "!=") if self._match("=") else Token(TokenType.NOT, "!"))
        elif c.isdigit():
            if dt := self._catch_datetime():
                self._add_token(Token(TokenType.DATETIME, dt))
        else:
            literal = self._catch_literal()

            if (llow := literal.lower()) in RESERVED_WORDS:
                self.token_list.append(Token(RESERVED_WORDS[llow], literal))
            else:
                self.token_list.append(Token(TokenType.LITERAL, literal))
        return

    def _at_end(self) -> bool:
        """Checks if we are at end of query string"""
        return self.current >= len(self.text)

    def _advance(self) -> str:
        """Returns next character, consuming it."""
        c = self.text[self.current]
        self.current += 1
        return c

    def _match(self, expected: str):
        """Matches the next character with `expected`.
        Argument `expected` must have length 1 or bad things may happen.
        Will consume character when True is returned.
        """
        if self._at_end():
            return False
        if self.text[self.current] != expected:
            return False

        self.current += 1
        return True

    def _peek(self) -> str:
        """Returns next character without consuming it."""
        if self._at_end():
            return ""
        return self.text[self.current]

    def _previous(self) -> str:
        """Returns previous character."""
        return self.text[self.current - 1]

    def _catch_datetime(self):
        """Returns a datetime if it matches an allowd pattern, consuming it.
        Returns the empty string when no match."""
        for pattern, pattern_length in DATETIME_PATTERNS.items():
            s = self.text[self.current - 1 : self.current + pattern_length - 1]
            if re.match(pattern, s):
                self.current += pattern_length - 1
                return s
        return ""

    def _catch_literal(self):
        """Returns the next literal, consuming it."""
        while (next_char := self._peek()) and (next_char.isalnum() or next_char in ["_", "."]):
            self._advance()
        return self.text[self.start : self.current]

    def _add_token(self, token: Token):
        """Adds a token to the token list."""
        self.token_list.append(token)


class Expression(ABC):
    """Expression abstract base class implementing a visitor interface"""

    @abstractmethod
    def accept(self, visitor):
        pass


class Binary(Expression):
    """A binary expression"""

    def __init__(self, left: Expression, operator: Token, right: Expression):
        self.left = left
        self.operator = operator
        self.right = right

    def accept(self, visitor):
        """Visitor pattern interface"""
        return visitor.visit_binary(self)


class Unary(Expression):
    """An unary expression"""

    def __init__(self, operator: Token, right: Expression):
        self.operator = operator
        self.right = right

    def accept(self, visitor):
        """Visitor pattern interface"""
        return visitor.visit_unary(self)


class Grouping(Expression):
    """A grouping expression"""

    def __init__(self, expression: Expression):
        self.expression = expression

    def accept(self, visitor):
        """Visitor pattern interface"""
        return visitor.visit_grouping(self)


class Query(Expression):
    """A query expression"""

    def __init__(self, key: Token, operator: Token, value: Token):
        self.key = key
        self.operator = operator
        self.value = value

    def accept(self, visitor):
        """Visitor pattern interface"""
        return visitor.visit_query(self)


class ParseError(Exception):
    """A class for parser errors."""


class Parser:
    """An abstract syntax tree parser by recursive descent"""

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.current = 0

    def parse(self) -> Expression | None:
        """Parses a token list into an expression AST"""
        try:
            return self._expression()
        except ParseError as e:
            raise

    def _expression(self) -> Expression:
        return self._or()

    def _or(self) -> Expression:
        expr = self._and()

        while self._match({TokenType.OR}):
            operator = self._previous()
            right = self._and()
            expr = Binary(expr, operator, right)

        return expr

    def _and(self) -> Expression:
        expr = self._unary()
        # we both implicit and explicit `and`.
        while (matched := self._match({TokenType.AND})) or (
            not self._at_end() and not self._check({TokenType.OR, TokenType.RIGHT_PAREN})
        ):
            operator = Token(TokenType.AND, matched.lexeme if matched else "_and")
            right = self._unary()
            expr = Binary(expr, operator, right)

        return expr

    def _unary(self) -> Expression:
        if self._match({TokenType.NOT}):
            operator = self._previous()
            right = self._primary()
            return Unary(operator, right)
        return self._primary()

    def _primary(self) -> Expression:
        if self._match({*RESERVED_WORDS_SPACECRAFT_NAMES.values()}):
            return Query(Token(TokenType.MODEL, "_model"), Token(TokenType.EQUAL, "_="), self._previous())
        elif self._match({*RESERVED_WORDS_CONFIGURATION_NAMES.values()}):
            return Query(self._previous(), Token(TokenType.ISNULL, "_isnull"), Token(TokenType.ISNULL, "_isnull"))
        elif noun := self._match({TokenType.SUBMITTED, TokenType.UPLINKED}):
            if predicate := self._match(
                {
                    TokenType.GREATER,
                    TokenType.GREATER_EQUAL,
                    TokenType.LESSER,
                    TokenType.LESSER_EQUAL,
                    TokenType.EQUAL,
                    TokenType.BANG_EQUAL,
                }
            ):
                if objective := self._match({TokenType.DATETIME}):
                    return Query(noun, predicate, objective)
                else:
                    raise ParseError(
                        f"A valid datetime is expected after '{noun.lexeme} {predicate.lexeme}' expression."
                    )
            elif predicate := self._match({TokenType.BY}):
                if objective := self._match({TokenType.LITERAL}):
                    return Query(noun, predicate, objective)
                else:
                    raise ParseError(f"An username is expected after '{noun.lexeme} {predicate.lexeme}' expression.")
            else:
                return Query(noun, Token(TokenType.ISNULL, "_isnull"), Token(TokenType.ISNULL, "_isnull"))
        elif self._match({TokenType.LEFT_PAREN}):
            expr = self._expression()
            self._consume(TokenType.RIGHT_PAREN, "Expected ')' after expression")
            return Grouping(expr)

        raise ParseError(f"An expression cannot start with '{self._peek().lexeme}'")

    def _match(self, expected: set[TokenType]) -> Token | None:
        """Matches against a set of token types. Consumes token."""
        if self._at_end():
            return None
        nextt = self._peek()
        if nextt.ttype in expected:
            self._advance()
            return nextt
        return None

    def _consume(self, expected: TokenType, error_message: str):
        """Consumes the next character, if it matches `expected`, or throan error."""
        if self._check({expected}):
            return self._advance()

        raise ParseError(error_message)

    def _check(self, expected: set[TokenType]):
        """Checks if token matches token type. Does not consume. If at end, returns false."""
        if self._at_end():
            return False
        return self._peek().ttype in expected

    def _advance(self):
        """Consumes token."""
        if not self._at_end():
            self.current += 1
        return self._previous()

    def _at_end(self):
        """Check if we reached end of token list."""
        return self._peek().ttype == TokenType.EOF

    def _peek(self):
        """Returns next token without consuming it"""
        return self.tokens[self.current]

    def _previous(self):
        """Returns the previous token."""
        return self.tokens[self.current - 1]


class Printer:
    """An AST printer, for debugging purpose."""

    def print(self, expr: Expression):
        return expr.accept(self)

    def visit_binary(self, expr: Binary):
        return f"Binary({self.print(expr.left)}, {expr.operator.lexeme}, {self.print(expr.right)})"

    def visit_unary(self, expr: Unary):
        return f"Unary({expr.operator.lexeme}, {self.print(expr.right)})"

    def visit_grouping(self, expr: Grouping):
        return f"Grouping({self.print(expr.expression)})"

    @staticmethod
    def visit_query(expr: Query):
        return f"Query({expr.key.lexeme}, {expr.operator.lexeme}, {expr.value.lexeme})"


class InterpreterError(Exception):
    """An interpreter error."""


class Interpreter:
    """Interpret an AST built from query string into a complex query expression."""

    def evaluate(self, expr: Expression):
        try:
            return expr.accept(self)
        except InterpreterError as e:
            raise

    def visit_binary(self, expr: Binary):
        left = self.evaluate(expr.left)
        right = self.evaluate(expr.right)

        if expr.operator.ttype == TokenType.AND:
            return left & right
        if expr.operator.ttype == TokenType.OR:
            return left | right
        raise InterpreterError("Invalid binary expression")

    def visit_unary(self, expr: Unary):
        right = self.evaluate(expr.right)

        if expr.operator.ttype == TokenType.NOT:
            return ~right
        raise InterpreterError("Invalid unary expression")

    def visit_grouping(self, expr: Grouping):
        expr = self.evaluate(expr.expression)
        return expr

    def visit_query(self, expr: Query):
        if expr.key.ttype == TokenType.MODEL:
            if expr.operator.ttype == TokenType.EQUAL:
                return Q(model=RESERVED_WORDS_SPACECRAFT_NAMES_INVERSE[expr.value.ttype])

            raise InterpreterError("Invalid model query")

        if expr.key.ttype in {*RESERVED_WORDS_CONFIGURATION_NAMES_INVERSE}:
            if expr.operator.ttype == TokenType.ISNULL and expr.value.ttype == TokenType.ISNULL:
                return Q(**{f"{RESERVED_WORDS_CONFIGURATION_NAMES_INVERSE[expr.key.ttype]}__isnull": False})

            raise InterpreterError("Invalid configuration query")

        if expr.key.ttype in {TokenType.SUBMITTED, TokenType.UPLINKED}:
            if expr.operator.ttype in {
                TokenType.GREATER,
                TokenType.GREATER_EQUAL,
                TokenType.LESSER,
                TokenType.LESSER_EQUAL,
                TokenType.EQUAL,
                TokenType.BANG_EQUAL,
            }:
                noun = "submit_time" if expr.key.ttype == TokenType.SUBMITTED else "uplink_time"
                dt = datetime.fromisoformat(expr.value.lexeme)
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt)
                if expr.operator.ttype == TokenType.GREATER:
                    return Q(**{f"{noun}__gt": dt})
                elif expr.operator.ttype == TokenType.GREATER_EQUAL:
                    return Q(**{f"{noun}__gte": dt})
                elif expr.operator.ttype == TokenType.LESSER:
                    return Q(**{f"{noun}__lt": dt})
                elif expr.operator.ttype == TokenType.LESSER_EQUAL:
                    return Q(**{f"{noun}__lte": dt})
                elif expr.operator.ttype == TokenType.EQUAL:
                    return Q(**{f"{noun}": dt})
                elif expr.operator.ttype == TokenType.BANG_EQUAL:
                    return ~Q(**{f"{noun}": dt})

                raise InterpreterError("Invalid datetime query")

            elif expr.operator.ttype == TokenType.BY:
                noun = "author" if expr.key.ttype == TokenType.SUBMITTED else "uplinked_by"
                return Q(**{f"{noun}__username": expr.value.lexeme})

            elif expr.operator.ttype == TokenType.ISNULL and expr.value.ttype == TokenType.ISNULL:
                noun = "submitted" if expr.key.ttype == TokenType.SUBMITTED else "uplinked"
                return Q(**{f"{noun}": True})

            raise InterpreterError("Invalid status query")

        raise InterpreterError("Invalid status query")
