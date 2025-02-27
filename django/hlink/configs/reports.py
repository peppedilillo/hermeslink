from dataclasses import dataclass
from enum import Enum
from typing import Literal

from django.utils import timezone
from hermes import STANDARD_FILENAMES
from hermes import STANDARD_SUFFIXES

from .models import config_to_sha256
from .models import Configuration
from .validators import crc16
from .validators import TestResult
from .validators import validate_configurations


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
            elif any(map(lambda suffix: literal.endswith(suffix), STANDARD_SUFFIXES)):
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
        return self.text[self.start : self.current]

    def _add_token(self, token: Token):
        self.token_list.append(token)


class Parser:
    def __init__(self, width: int = 68, indent: str = " " * 4, fmt: Literal["html", "txt"] = "html"):
        """
        Parses a token list into an HTML-formatted test report with proper indentation
        and line wrapping.
        """
        self.column = 0
        self.width = width
        self.indent = indent
        self.indent_level = 0
        self.format = fmt
        self.lb = "<br>" if self.format == "html" else "\n"

    def parse(self, token_list: list[Token]) -> str:
        """
        Converts a token list to HTML with proper formatting and status coloring.
        Returns the formatted HTML string.
        """
        s = ""
        for token in token_list:
            if token.ttype == TokenType.HEXSTRING:
                s += self._formatted_hexstring(token.lexeme)
                continue
            elif token.ttype == TokenType.INDENT:
                self.column += len(self.indent)
                self.indent_level += 1
                s += self.indent
                continue
            elif token.ttype == TokenType.NEWLINE:
                self.column = 0
                self.indent_level = 0
                s += self.lb
                continue
            elif token.ttype == TokenType.EOF:
                return s

            token_length = len(token.lexeme)
            if token_length < self.width - len(self.indent) * self.indent_level:
                if self.column + token_length > self.width:
                    s += f"{self.lb}{self.indent * self.indent_level}"
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
                        s += f"{self.lb}{self.indent * self.indent_level}"
                        self.column = len(self.indent) * self.indent_level
                        s += c

    def _formatted_passed(self):
        if self.format == "html":
            return f"""<span class="text-green-500"><b>passed</b></span>"""
        return "PASSED"

    def _formatted_warning(self):
        if self.format == "html":
            return f"""<span class="text-yellow-500"><b>warning</b></span>"""
        return "WARNING"

    def _formatted_error(self):
        if self.format == "html":
            return f"""<span class="text-red-500"><b>error</b></span>"""
        return "ERROR"

    def _formatted_filename(self, filename: str):
        if self.format == "html":
            return f"""<b><i>{filename}</i></b>"""
        return filename

    def _formatted_hexstring(self, hexstring: str):
        if self.format == "html":
            intro = f"""{self.lb}<span class="text-gray-500">"""
            outro = "</span>"
        else:
            intro = f"{self.lb}"
            outro = ""

        s, i = f"""{intro}{self.indent * (self.indent_level + 1)}""", 0
        col = len(self.indent) * (self.indent_level + 1)
        while hexstring:
            i += 1
            s += hexstring[:2] + " "
            col += 3
            if i % 4 == 0:
                s += " "
                col += 1
            if i % 16 == 0:
                s += f"{self.lb}{self.indent * (self.indent_level + 1)}"
                col = len(self.indent) * (self.indent_level + 1)
            hexstring = hexstring[2:]
        break_at_end = col > len(self.indent) * (self.indent_level + 1)
        return s + outro + (self.lb if break_at_end else "")


def _compose(
    test_results: dict[str, list[TestResult]],
    config_data: dict[str, str],
    indent_level=1,
) -> str:
    """
    Writes an input for parser.
    """
    if indent_level < 1:
        raise ValueError("indent_level must be greater than 0")
    indent = "$"
    report = ""
    fileline = ""
    for i, ftype in enumerate(config_data.keys(), 1):
        fileline += f"{indent * (indent_level - 1)}{i}. File {STANDARD_FILENAMES[ftype]}\n\n"
        fileline += f"{indent * indent_level}Content: 0x{config_data[ftype]}\n"
        fileline += f"{indent * indent_level}CRC16: 0x{crc16(bytes.fromhex(config_data[ftype])).hex()}\n"
        fileline += f"{indent * indent_level}Test results:\n"
        for test in test_results.setdefault(ftype, []):
            fileline += f"{indent * (indent_level + 1)}Test {test.status.name} : {test.message}\n"
        # do not add new line if we have no more files
        report += fileline + ("\n" if i < len(config_data) else "")
        fileline = ""
    return report


def write_test_report_html(test_results: dict[str, list[TestResult]], config_data: dict[str, str]) -> str:
    """
    Generates an HTML-formatted report from test results and configuration data.

    Args:
        test_results: Dict mapping file types to lists of test results
        config_data: Dict mapping file types to hex-encoded configuration strings

    Returns:
        HTML-formatted test report string
    """
    try:
        html = Parser(fmt="html").parse(Scanner(_compose(test_results, config_data)).scan_tokens())
    except Exception:
        html = "Could not parse report."
    return html


def write_test_report_txt(test_results: dict[str, list[TestResult]], config_data: dict[str, str]) -> str:
    """
    Generates a plain text report from test results and configuration data.

    Args:
        test_results: Dict mapping file types to lists of test results
        config_data: Dict mapping file types to hex-encoded configuration strings

    Returns:
        plain text test report string
    """
    try:
        txt = Parser(fmt="txt").parse(Scanner(_compose(test_results, config_data)).scan_tokens())
    except Exception:
        txt = "Could not parse report."
    return txt


def write_config_readme_txt(config: Configuration) -> str:
    """
    Generate a README file for a configuration archive.
    Will raise ValueError if `config` has no configuration files.
    """
    non_null_configs = config.non_null_configs_keys()
    sha256sum, order = config_to_sha256(config, ordered_keys=non_null_configs)

    section_intro = [
        f"This report was automatically generated with Hermes Link.",
        f"$$$$$$$$$$$${timezone.now().isoformat()}",
    ]

    section_metadata = [
        f"\n~ CONFIGURATION DATA",
        f"$Configuration ID: {config.id}",
        f"$Payload model: {config.model}",
        f"$Includes configurations: {', '.join(non_null_configs)}",
        f"$Author: {config.author}",
        f"$Created on: {config.date}",
        f"$Submit status: {config.submitted}",
    ]

    if config.submitted:
        section_metadata.append(f"$Submit time: {config.submit_time}")

    section_metadata.append(f"$Uplink status: {config.uplinked}")
    if config.uplinked:
        section_metadata.append(f"$Uplink time: {config.uplink_time}")
    section_metadata.append(f"$SHA256 hash: 0x{sha256sum} ")

    test_report = _compose(
        validate_configurations(config.get_config_data(), config.model),
        config.get_encoded_config_data(),
        indent_level=2,
    )
    section_test = [
        f"\n~ TEST REPORT:",
        f"{test_report}",
    ]

    section_comments = [
        "\n~ COMMENTS:",
        f"$* Hash check with `cat {' '.join([STANDARD_FILENAMES[ftype] for ftype in order])} | sha256sum`",
        f"",
    ]

    text = "\n".join(section_intro + section_metadata + section_test + section_comments)
    return f"{LOGO_ASCII}\n" + Parser(width=120, indent="  ", fmt="txt").parse(Scanner(text).scan_tokens())


LOGO_ASCII = r""" ______  _______ 
 ___  / / /__  / 
 __  /_/ /__  /  
 _  __  / _  /___
 /_/ /_/  /_____/
"""
