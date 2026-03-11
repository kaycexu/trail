from __future__ import annotations

import pytest

from trail.redact import (
    clean_text_for_storage,
    compact_text,
    redact_sensitive_text,
    strip_ansi,
    REDACTED,
)


# ---------------------------------------------------------------------------
# redact_sensitive_text
# ---------------------------------------------------------------------------

class TestRedactSensitiveText:
    """Tests for redact_sensitive_text."""

    # -- OpenAI keys (sk-...) -----------------------------------------------

    def test_openai_key_redacted(self):
        text = "key is sk-abc123def456ghi789jkl012mno"
        result = redact_sensitive_text(text)
        assert "sk-abc123" not in result
        assert REDACTED in result

    def test_openai_proj_key_redacted(self):
        text = "export OPENAI_API_KEY=sk-proj-aBcDeFgHiJkLmNoPqRsT012345"
        result = redact_sensitive_text(text)
        assert "sk-proj-" not in result
        assert REDACTED in result

    # -- Anthropic keys (sk-ant-...) ----------------------------------------

    def test_anthropic_key_redacted(self):
        text = "ANTHROPIC_API_KEY=sk-ant-api03-abcdefghijklmnopqrst"
        result = redact_sensitive_text(text)
        assert "sk-ant-" not in result
        assert REDACTED in result

    # -- AWS access key IDs (AKIA...) ---------------------------------------

    def test_aws_key_redacted(self):
        text = "aws_access_key_id = AKIAIOSFODNN7EXAMPLE"
        result = redact_sensitive_text(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert REDACTED in result

    def test_aws_key_exact_length(self):
        # AKIA followed by exactly 16 uppercase alphanumeric chars
        key = "AKIA" + "A" * 16
        result = redact_sensitive_text(f"id={key}")
        assert key not in result

    # -- GitHub PATs (ghp_...) ----------------------------------------------

    def test_github_pat_redacted(self):
        token = "ghp_" + "a" * 36
        result = redact_sensitive_text(f"token: {token}")
        assert token not in result
        assert REDACTED in result

    # -- GitHub fine-grained tokens (github_pat_...) ------------------------

    def test_github_fine_grained_pat_redacted(self):
        token = "github_pat_" + "a1B2c3D4e5F6g7H8i9J0"
        result = redact_sensitive_text(f"GH_TOKEN={token}")
        assert token not in result
        assert REDACTED in result

    # -- Bearer tokens ------------------------------------------------------

    def test_bearer_token_redacted(self):
        text = "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"
        result = redact_sensitive_text(text)
        assert "eyJhbGci" not in result
        assert "Bearer" in result  # prefix kept
        assert REDACTED in result

    def test_bearer_case_insensitive(self):
        text = "bearer some-long-token-value_here"
        result = redact_sensitive_text(text)
        assert "some-long-token" not in result

    # -- Slack tokens -------------------------------------------------------

    def test_slack_xoxb_redacted(self):
        token = "xoxb-123456789012-1234567890123-abcDEFghiJKL"
        result = redact_sensitive_text(token)
        assert token not in result
        assert REDACTED in result

    def test_slack_xoxp_redacted(self):
        token = "xoxp-123456789012-1234567890123-abcDEFghiJKL"
        result = redact_sensitive_text(token)
        assert token not in result
        assert REDACTED in result

    def test_slack_xapp_redacted(self):
        token = "xapp-1-A12345-67890-abcdef"
        result = redact_sensitive_text(token)
        assert token not in result
        assert REDACTED in result

    # -- --token flag values ------------------------------------------------

    def test_token_flag_redacted(self):
        text = "git clone --token ghp_SomeSecretTokenValueThatIsLongEnough123456 https://example.com"
        result = redact_sensitive_text(text)
        assert "ghp_Some" not in result
        assert REDACTED in result

    def test_password_flag_redacted(self):
        text = "curl --password mysecretvalue https://example.com"
        result = redact_sensitive_text(text)
        assert "mysecretvalue" not in result
        assert REDACTED in result

    # -- key=value patterns -------------------------------------------------

    def test_password_eq_redacted(self):
        text = 'password=hunter2'
        result = redact_sensitive_text(text)
        assert "hunter2" not in result
        assert REDACTED in result

    def test_password_eq_redacted(self):
        text = 'password=abcdef123456'
        result = redact_sensitive_text(text)
        assert "abcdef123456" not in result
        assert REDACTED in result

    def test_token_eq_redacted(self):
        text = "token=eyJhbGciOiJIUzI1NiJ9.payload.signature"
        result = redact_sensitive_text(text)
        assert "eyJhbGci" not in result

    def test_api_key_eq_redacted(self):
        text = "api_key=some_long_value_here"
        result = redact_sensitive_text(text)
        assert "some_long_value_here" not in result

    def test_api_key_with_spaces_around_eq(self):
        text = "api-key = myval123"
        result = redact_sensitive_text(text)
        assert "myval123" not in result

    # -- JWT tokens ---------------------------------------------------------

    def test_jwt_token_redacted(self):
        header = "eyJhbGciOiJIUzI1NiJ9"
        payload = "eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        sig = "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        jwt = f"{header}.{payload}.{sig}"
        result = redact_sensitive_text(f"token: {jwt}")
        assert header not in result
        assert REDACTED in result

    def test_jwt_without_eyj_prefix_not_redacted(self):
        # Must start with eyJ to be recognised as JWT
        text = "abc.def.ghi"
        result = redact_sensitive_text(text)
        assert result == text

    # -- passthrough / edge cases -------------------------------------------

    def test_normal_text_unchanged(self):
        text = "Hello, this is a normal log line with no secrets."
        assert redact_sensitive_text(text) == text

    def test_empty_string(self):
        assert redact_sensitive_text("") == ""

    def test_multibyte_utf8_not_mangled(self):
        text = "日本語テスト こんにちは 🎉 emoji test"
        assert redact_sensitive_text(text) == text

    def test_mixed_secrets_and_utf8(self):
        key = "sk-ant-" + "x" * 30
        text = f"你好 {key} 世界"
        result = redact_sensitive_text(text)
        assert key not in result
        assert "你好" in result
        assert "世界" in result

    def test_multiple_secrets_all_redacted(self):
        sk = "sk-" + "a" * 40
        akia = "AKIA" + "B" * 16
        text = f"keys: {sk} and {akia}"
        result = redact_sensitive_text(text)
        assert sk not in result
        assert akia not in result
        assert result.count(REDACTED) >= 2


# ---------------------------------------------------------------------------
# strip_ansi
# ---------------------------------------------------------------------------

class TestStripAnsi:
    """Tests for strip_ansi."""

    def test_csi_color_codes_stripped(self):
        text = "\x1b[32mgreen text\x1b[0m"
        assert strip_ansi(text) == "green text"

    def test_csi_bold_and_reset(self):
        text = "\x1b[1mbold\x1b[22m normal"
        assert strip_ansi(text) == "bold normal"

    def test_csi_cursor_movement_stripped(self):
        text = "\x1b[2Jhello\x1b[H"
        assert strip_ansi(text) == "hello"

    def test_osc_title_sequence_stripped(self):
        text = "\x1b]0;Window Title\x07rest"
        assert strip_ansi(text) == "rest"

    def test_osc_with_st_terminator(self):
        text = "\x1b]2;title\x1b\\rest"
        assert strip_ansi(text) == "rest"

    def test_plain_text_unchanged(self):
        text = "nothing special here"
        assert strip_ansi(text) == "nothing special here"

    def test_empty_string(self):
        assert strip_ansi("") == ""

    def test_multiple_escapes(self):
        text = "\x1b[31mred\x1b[0m and \x1b[34mblue\x1b[0m"
        assert strip_ansi(text) == "red and blue"


# ---------------------------------------------------------------------------
# clean_text_for_storage
# ---------------------------------------------------------------------------

class TestCleanTextForStorage:
    """Tests for clean_text_for_storage."""

    def test_ansi_embedded_secret_redacted(self):
        """ANSI is stripped first, then redaction sees the bare secret."""
        key = "sk-" + "a" * 40
        text = f"\x1b[33m{key}\x1b[0m"
        result = clean_text_for_storage(text, "stdout")
        assert key not in result
        assert REDACTED in result
        # No leftover ANSI
        assert "\x1b" not in result

    def test_ansi_split_secret_still_redacted(self):
        """Secret interrupted by ANSI codes should be redacted after strip."""
        # e.g., sk-<ansi>rest-of-key -- after stripping ANSI the key is intact
        prefix = "sk-"
        suffix = "a" * 40
        text = f"{prefix}\x1b[1m{suffix}\x1b[0m"
        result = clean_text_for_storage(text, "stdout")
        full_key = prefix + suffix
        assert full_key not in result
        assert REDACTED in result

    def test_cr_lf_normalised(self):
        text = "line1\r\nline2\rline3"
        result = clean_text_for_storage(text, "stdout")
        assert "\r" not in result
        assert result == "line1\nline2\nline3"

    def test_backspace_preserved_for_stdin(self):
        text = "abc\bde"
        result = clean_text_for_storage(text, "stdin")
        assert "\b" in result

    def test_backspace_stripped_for_stdout(self):
        text = "abc\bde"
        result = clean_text_for_storage(text, "stdout")
        assert "\b" not in result

    def test_delete_char_preserved_for_stdin(self):
        text = "abc\x7fde"
        result = clean_text_for_storage(text, "stdin")
        assert "\x7f" in result

    def test_delete_char_stripped_for_stdout(self):
        text = "abc\x7fde"
        result = clean_text_for_storage(text, "stdout")
        assert "\x7f" not in result

    def test_unprintable_characters_filtered(self):
        # BEL (\x07) and other control chars should be dropped
        text = "hello\x07world\x01!"
        result = clean_text_for_storage(text, "stdout")
        assert result == "helloworld!"

    def test_tabs_and_newlines_preserved(self):
        text = "col1\tcol2\nrow2"
        result = clean_text_for_storage(text, "stdout")
        assert result == "col1\tcol2\nrow2"

    def test_empty_string(self):
        assert clean_text_for_storage("", "stdout") == ""

    def test_plain_text_passthrough(self):
        text = "normal log output"
        assert clean_text_for_storage(text, "stdout") == "normal log output"


# ---------------------------------------------------------------------------
# compact_text
# ---------------------------------------------------------------------------

class TestCompactText:
    """Tests for compact_text."""

    def test_short_text_unchanged(self):
        text = "hello world"
        assert compact_text(text, limit=200) == "hello world"

    def test_whitespace_collapsed(self):
        text = "hello   world\n\tnewline"
        assert compact_text(text) == "hello world newline"

    def test_text_exceeding_limit_truncated(self):
        text = "a" * 300
        result = compact_text(text, limit=50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_exactly_at_limit(self):
        text = "a" * 100
        result = compact_text(text, limit=100)
        assert result == text
        assert len(result) == 100

    def test_one_over_limit(self):
        text = "a" * 101
        result = compact_text(text, limit=100)
        assert len(result) == 100
        assert result.endswith("...")
        assert result == "a" * 97 + "..."

    def test_default_limit_is_200(self):
        short = "x" * 200
        assert compact_text(short) == short
        long = "x" * 201
        result = compact_text(long)
        assert len(result) == 200
        assert result.endswith("...")

    def test_empty_string(self):
        assert compact_text("") == ""

    def test_only_whitespace(self):
        assert compact_text("   \t\n  ") == ""
