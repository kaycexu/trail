from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EditableLineBuffer:
    text: str = ""
    cursor: int = 0
    escape_buffer: str = ""

    def feed(self, chunk: str) -> list[str]:
        data = self.escape_buffer + chunk
        self.escape_buffer = ""
        submissions: list[str] = []
        index = 0

        while index < len(data):
            char = data[index]

            if char == "\x1b":
                consumed = self._consume_escape(data, index)
                if consumed is None:
                    self.escape_buffer = data[index:]
                    break
                index = consumed
                continue

            if char in ("\r", "\n"):
                submitted = self.text.rstrip()
                if submitted.strip():
                    submissions.append(submitted)
                self.text = ""
                self.cursor = 0
                index += 1
                continue

            if char in ("\x7f", "\b"):
                self._delete_before_cursor()
                index += 1
                continue

            if char == "\x01":  # Ctrl-A
                self.cursor = 0
                index += 1
                continue

            if char == "\x05":  # Ctrl-E
                self.cursor = len(self.text)
                index += 1
                continue

            if char == "\x15":  # Ctrl-U
                self.text = self.text[self.cursor:]
                self.cursor = 0
                index += 1
                continue

            if char == "\x0b":  # Ctrl-K
                self.text = self.text[:self.cursor]
                index += 1
                continue

            if char == "\x17":  # Ctrl-W
                self._delete_previous_word()
                index += 1
                continue

            if char == "\t" or char.isprintable():
                self._insert_text(char)

            index += 1

        return submissions

    def _consume_escape(self, data: str, index: int) -> int | None:
        remaining = data[index:]

        if remaining.startswith("\x1b["):
            end = 2
            while index + end < len(data):
                final = data[index + end]
                if final.isalpha() or final == "~":
                    sequence = data[index:index + end + 1]
                    self._apply_escape(sequence)
                    return index + end + 1
                end += 1
            return None

        if remaining.startswith("\x1bO"):
            if index + 2 >= len(data):
                return None
            sequence = data[index:index + 3]
            self._apply_escape(sequence)
            return index + 3

        if remaining.startswith("\x1bb"):
            self._move_word_left()
            return index + 2
        if remaining.startswith("\x1bf"):
            self._move_word_right()
            return index + 2
        if remaining.startswith("\x1bd"):
            self._delete_next_word()
            return index + 2
        if remaining.startswith("\x1b\x7f"):
            self._delete_previous_word()
            return index + 2

        if len(remaining) == 1:
            return None
        return index + 1

    def _apply_escape(self, sequence: str) -> None:
        if sequence in {"\x1b[D", "\x1bOD"}:
            self.cursor = max(0, self.cursor - 1)
            return
        if sequence in {"\x1b[C", "\x1bOC"}:
            self.cursor = min(len(self.text), self.cursor + 1)
            return
        if sequence in {"\x1b[H", "\x1bOH", "\x1b[1~", "\x1b[7~"}:
            self.cursor = 0
            return
        if sequence in {"\x1b[F", "\x1bOF", "\x1b[4~", "\x1b[8~"}:
            self.cursor = len(self.text)
            return
        if sequence == "\x1b[3~":
            self._delete_at_cursor()

    def _insert_text(self, text: str) -> None:
        self.text = self.text[:self.cursor] + text + self.text[self.cursor:]
        self.cursor += len(text)

    def _delete_before_cursor(self) -> None:
        if self.cursor == 0:
            return
        self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
        self.cursor -= 1

    def _delete_at_cursor(self) -> None:
        if self.cursor >= len(self.text):
            return
        self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]

    def _delete_previous_word(self) -> None:
        if self.cursor == 0:
            return
        left = self.text[:self.cursor]
        end = len(left.rstrip())
        start = end
        while start > 0 and not left[start - 1].isspace():
            start -= 1
        self.text = self.text[:start] + self.text[self.cursor:]
        self.cursor = start

    def _delete_next_word(self) -> None:
        if self.cursor >= len(self.text):
            return
        right = self.text[self.cursor:]
        end = 0
        while end < len(right) and right[end].isspace():
            end += 1
        while end < len(right) and not right[end].isspace():
            end += 1
        self.text = self.text[:self.cursor] + right[end:]

    def _move_word_left(self) -> None:
        if self.cursor == 0:
            return
        pos = self.cursor
        while pos > 0 and self.text[pos - 1].isspace():
            pos -= 1
        while pos > 0 and not self.text[pos - 1].isspace():
            pos -= 1
        self.cursor = pos

    def _move_word_right(self) -> None:
        pos = self.cursor
        while pos < len(self.text) and self.text[pos].isspace():
            pos += 1
        while pos < len(self.text) and not self.text[pos].isspace():
            pos += 1
        self.cursor = pos
