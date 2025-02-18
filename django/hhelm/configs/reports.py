from dataclasses import dataclass
from enum import Enum

from .validators import TestResult


class TokenType(Enum):
    """Token types for the test report lexer."""
    INDENT = 0
    NEWLINE = 1
    LITERAL = 2
    PASSED = 3
    WARNING = 4
    ERROR = 5
    FILENAME = 6
    HEXSTRING = 7
    EOF = 8


@dataclass
class Token:
    """A lexical token with type and content."""
    ttype: TokenType
    lexeme: str


class Scanner:
    """
    Tokenizes a test report string. The report should be formatted as:
    1. File NAME.cfg
    $Content: 0xHEXSTRING
    $Test results:
    $$Test STATUS: MESSAGE
    """
    def __init__(self, text: str):
        self.text = text
        self.token_list = []
        self.start = 0
        self.current = 0
        self.column = 0

    def scan_tokens(self) -> list[Token]:
        """Scans the input text and returns a list of tokens."""
        while not self._at_end():
            self.start = self.current
            self._scan_token()
        self._add_token(Token(TokenType.EOF, ""))
        return self.token_list

    def _scan_token(self):
        c = self._advance()
        if c == "\n":
            self._add_token(Token(TokenType.NEWLINE, "\n"))
        elif c == "$":
            if self._previous() not in ["\n", "$"]:
                raise ValueError("Indent can only start a line.")
            self._add_token(Token(TokenType.INDENT, ""))
        elif c.isspace():
            pass
        else:
            literal = self._catch_literal()
            if literal == "WARNING":
                self._add_token(Token(TokenType.WARNING, "WARNING"))
            elif literal == "PASSED":
                self._add_token(Token(TokenType.PASSED, "PASSED"))
            elif literal == "ERROR":
                self._add_token(Token(TokenType.ERROR, "ERROR"))
            elif literal.endswith(".cfg"):
                self._add_token(Token(TokenType.FILENAME, literal))
            elif literal.startswith("0x"):
                self._add_token(Token(TokenType.HEXSTRING, literal[2:]))
            else:
                self._add_token(Token(TokenType.LITERAL, literal))
        return

    def _at_end(self):
        return self.current >= len(self.text)

    def _advance(self):
        c = self.text[self.current]
        self.current += 1
        return c

    def _peek(self) -> str:
        if self.current >= len(self.text):
            return ""
        return self.text[self.current]

    def _previous(self) -> str:
        return self.text[self.current - 1]

    def _catch_literal(self):
        while (next_char := self._peek()) and (not next_char.isspace()) and next_char != "$":
            self._advance()
        return self.text[self.start: self.current]

    def _add_token(self, token: Token):
        self.token_list.append(token)


class Parser:
    def __init__(self, width:int = 64, indent:str = " " * 4):
        """
        Parses a token list into an HTML-formatted test report with proper indentation
        and line wrapping.
        """
        self.column = 0
        self.width = width
        self.indent = indent
        self.indent_level = 0

    def parse(self, token_list: list[Token]) -> str:
        """
        Converts a token list to HTML with proper formatting and status coloring.
        Returns the formatted HTML string.
        """
        s = "<pre>"
        for token in token_list:
            if token.ttype == TokenType.HEXSTRING:
                s += self._formatted_hexstring(token.lexeme)
                continue
            elif token.ttype == TokenType.INDENT:
                self.column += len(self.indent)
                self.indent_level += 1
                s += f"{self.indent}"
                continue
            elif token.ttype == TokenType.NEWLINE:
                self.column = 0
                self.indent_level = 0
                s += "\n"
                continue
            elif token.ttype == TokenType.EOF:
                return s + "</pre>"

            token_length = len(token.lexeme)
            if token_length < self.width - len(self.indent) * self.indent_level:
                if self.column + token_length > self.width:
                    s += f"<br>{self.indent * self.indent_level}"
                    self.column = len(self.indent) * self.indent_level
                if token.ttype == TokenType.PASSED:
                    s += self._formatted_passed()
                elif token.ttype == TokenType.WARNING:
                    s += self._formatted_warning()
                elif token.ttype == TokenType.ERROR:
                    s += self._formatted_error()
                elif token.ttype == TokenType.FILENAME:
                    s += self._formatted_filename(token.lexeme)
                elif token.ttype == TokenType.LITERAL:
                    s += token.lexeme
                s += " " if token_length < self.width else ""
                self.column += token_length + 1
            else:
                for c in token.lexeme:
                    s += c
                    self.column += 1
                    if self.column > self.width:
                        s += f"<br>{self.indent * self.indent_level}"
                        self.column = len(self.indent) * self.indent_level
                        s += c

    def _formatted_passed(self):
        return f"""<span class="text-green-500"><b>passed</b></span>"""

    def _formatted_warning(self):
        return f"""<span class="text-yellow-500"><b>warning</b></span>"""

    def _formatted_error(self):
        return f"""<span class="text-red-500"><b>error</b></span>"""

    def _formatted_filename(self, filename: str):
        return f"""<b><i>{filename}</i></b>"""

    def _formatted_hexstring(self, hexstring: str):
        s, i = f"""<br><br><span class="text-gray-500">{self.indent * (self.indent_level + 1)}""", 0
        col = len(self.indent) * (self.indent_level + 1)
        while hexstring:
            i += 1
            s += hexstring[:2] + " "
            col += 3
            if i % 4 == 0:
                s += " "
                col += 1
            if i % 16 == 0:
                s += f"<br>{self.indent * (self.indent_level + 1)}"
                col = len(self.indent) * (self.indent_level + 1)
            hexstring = hexstring[2:]
        break_at_end = col > len(self.indent) * (self.indent_level + 1)
        return s + f"""</span>{"<br>" if break_at_end else "" }"""


def format_report_to_html(
    test_results: dict[str, list[TestResult]],
    config_data: dict[str, str]
) -> str:
    """
    Generates an HTML-formatted test report from test results and configuration data.

    Args:
        test_results: Dict mapping file types to lists of test results
        config_data: Dict mapping file types to hex-encoded configuration strings

    Returns:
        HTML-formatted test report string
    """
    report = ""
    fileline = ""
    for i, ftype in enumerate(config_data.keys(), 1):
        fileline += f"{i}. File {ftype.upper()}.cfg\n"
        fileline += f"$Content: 0x{config_data[ftype]}\n"
        fileline += f"$Test results:\n"
        for test in test_results.setdefault(ftype, []):
            fileline += f"$$Test {test.status.name} : {test.message}\n"
        report += fileline
        fileline = ""

    try:
        html = Parser().parse(Scanner(report).scan_tokens())
    except Exception as e:
        html = "Could not parse report."
    return html