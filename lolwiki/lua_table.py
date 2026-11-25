"""Parse the subset of Lua used by League of Legends Wiki data modules.

Wiki data modules (e.g. Module:SpellDataWR/data) are a single
``return { ... }`` table literal made of strings, numbers, booleans and
nested tables. This parser handles exactly that, so we don't need a Lua
runtime to read them.
"""

from typing import Any

LuaValue = Any


class LuaParseError(ValueError):
    """Raised when the module text is not a table literal we understand."""


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'"}


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def error(self, message: str) -> LuaParseError:
        return LuaParseError(f"{message} at offset {self.pos}")

    def skip_space(self) -> None:
        text = self.text
        while self.pos < len(text):
            if text[self.pos].isspace():
                self.pos += 1
            elif text.startswith("--", self.pos):
                end = text.find("\n", self.pos)
                self.pos = len(text) if end == -1 else end + 1
            else:
                break

    def peek(self) -> str:
        self.skip_space()
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def expect(self, char: str) -> None:
        if self.peek() != char:
            raise self.error(f"expected {char!r}")
        self.pos += 1

    def parse_module(self) -> LuaValue:
        self.skip_space()
        if self.text.startswith("return", self.pos):
            self.pos += len("return")
        value = self.parse_value()
        if self.peek():
            raise self.error("unexpected trailing text")
        return value

    def parse_value(self) -> LuaValue:
        char = self.peek()
        if char == "{":
            return self.parse_table()
        if char in "\"'":
            return self.parse_string()
        if char == "-" or char.isdigit():
            return self.parse_number()
        word = self.parse_name()
        if word == "true":
            return True
        if word == "false":
            return False
        if word == "nil":
            return None
        raise self.error(f"unexpected token {word!r}")

    def parse_name(self) -> str:
        self.skip_space()
        start = self.pos
        while self.pos < len(self.text) and (
            self.text[self.pos].isalnum() or self.text[self.pos] == "_"
        ):
            self.pos += 1
        if start == self.pos:
            raise self.error("expected a name")
        return self.text[start : self.pos]

    def parse_number(self) -> int | float:
        self.skip_space()
        start = self.pos
        if self.text[self.pos] == "-":
            self.pos += 1
        while self.pos < len(self.text) and (
            self.text[self.pos].isdigit() or self.text[self.pos] in ".eE"
        ):
            self.pos += 1
        literal = self.text[start : self.pos]
        try:
            return int(literal)
        except ValueError:
            try:
                return float(literal)
            except ValueError:
                raise self.error(f"bad number {literal!r}") from None

    def parse_string(self) -> str:
        quote = self.peek()
        self.pos += 1
        chars: list[str] = []
        while self.pos < len(self.text):
            char = self.text[self.pos]
            if char == quote:
                self.pos += 1
                return "".join(chars)
            if char == "\\":
                self.pos += 1
                if self.pos >= len(self.text):
                    break
                escaped = self.text[self.pos]
                chars.append(_ESCAPES.get(escaped, escaped))
            else:
                chars.append(char)
            self.pos += 1
        raise self.error("unterminated string")

    def parse_table(self) -> dict | list:
        self.expect("{")
        result: dict[Any, LuaValue] = {}
        next_index = 1
        while self.peek() != "}":
            if not self.peek():
                raise self.error("unterminated table")
            if self.peek() == "[":
                self.pos += 1
                key = self.parse_value()
                self.expect("]")
                self.expect("=")
                result[key] = self.parse_value()
            elif self._at_bare_key():
                key = self.parse_name()
                self.expect("=")
                result[key] = self.parse_value()
            else:
                result[next_index] = self.parse_value()
                next_index += 1
            if self.peek() in ",;":
                self.pos += 1
            elif self.peek() != "}":
                raise self.error("expected ',' or '}'")
        self.pos += 1
        # A table with only positional entries reads naturally as a list.
        if result and list(result) == list(range(1, next_index)):
            return list(result.values())
        return result

    def _at_bare_key(self) -> bool:
        save = self.pos
        try:
            if not (self.peek().isalpha() or self.peek() == "_"):
                return False
            name = self.parse_name()
            return name not in ("true", "false", "nil") and self.peek() == "="
        except LuaParseError:
            return False
        finally:
            self.pos = save


def parse_lua_table(text: str) -> LuaValue:
    """Parse a ``return { ... }`` Lua module into Python dicts, lists and scalars.

    Args:
        text: The module source, as served by the wiki's ``?action=raw``.

    Returns:
        The returned table, with Lua tables as dicts (or lists when they only
        have positional entries).

    Raises:
        LuaParseError: If the text uses syntax outside the supported subset.
    """
    return _Parser(text).parse_module()
