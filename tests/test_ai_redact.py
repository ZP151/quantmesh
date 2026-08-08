"""Phase D redaction tests (M8, issue #48).

Shape-scan arithmetic pinned per class, known-value replacement
(environment and explicit), the safe-direction over-redaction
negatives (40-hex commits and 16-hex ids survive), deterministic
counts, and the prompt-injection containment property: a secret
embedded in retrieved document text is scrubbed before anything
reaches the gateway, and never appears in the output.
"""

from collections.abc import Mapping

import pytest

from quantmesh.ai.errors import RedactionError
from quantmesh.ai.redact import (
    REDACTED_ENV_SECRET,
    REDACTED_PRIVATE_KEY,
    REDACTED_TOKEN,
    redact_context,
)

PRIVATE_KEY = "0x" + "a1" * 32  # 0x-prefixed 64-hex
BARE_KEY = "b2" * 32  # bare 64-hex
COMMIT = "c3" * 20  # pure 40-hex — must survive
SHORT_ID = "d4" * 8  # 16-hex id — must survive


def _redact(context: Mapping[str, str], **kwargs) -> tuple[dict[str, str], object]:
    return redact_context(context, **kwargs)


class TestShapeScans:
    def test_clean_text_passes_through(self) -> None:
        redacted, report = redact_context({"context": "BTC rallied on volume"})
        assert redacted == {"context": "BTC rallied on volume"}
        assert report.total == 0
        assert report.by_class == {"env_secret": 0, "private_key": 0, "token": 0}

    def test_private_key_0x_prefixed_scrubbed(self) -> None:
        redacted, report = redact_context({"context": f"key: {PRIVATE_KEY}"})
        assert redacted["context"] == f"key: {REDACTED_PRIVATE_KEY}"
        assert report.by_class["private_key"] == 1
        assert report.total == 1

    def test_bare_64_hex_scrubbed_as_key(self) -> None:
        redacted, report = redact_context({"context": BARE_KEY})
        assert redacted["context"] == REDACTED_PRIVATE_KEY
        assert report.by_class["private_key"] == 1

    def test_pure_40_hex_commit_survives(self) -> None:
        redacted, report = redact_context({"context": f"commit {COMMIT} deployed"})
        assert COMMIT in redacted["context"]
        assert report.total == 0

    def test_16_hex_id_survives(self) -> None:
        redacted, report = redact_context({"context": f"run {SHORT_ID}"})
        assert SHORT_ID in redacted["context"]
        assert report.total == 0

    def test_bearer_token_scrubbed(self) -> None:
        token = "Bearer eyJhbGciOi.eyJzdWIiOiJ1c2VyIn0.signature_part"
        redacted, report = redact_context({"context": f"auth: {token}"})
        assert REDACTED_TOKEN in redacted["context"]
        assert token not in redacted["context"]
        assert report.by_class["token"] == 1

    def test_sk_token_scrubbed(self) -> None:
        redacted, report = redact_context({"context": "key sk-abcdefghijklmnopqrstuvwxyz123"})
        assert REDACTED_TOKEN in redacted["context"]
        assert report.by_class["token"] == 1

    def test_long_opaque_non_hex_run_scrubbed_as_token(self) -> None:
        run = "abc123def456ghi789jkl012mno345pqr678stu901z"  # 42 chars, one 'z'
        redacted, report = redact_context({"context": f"opaque {run}"})
        assert REDACTED_TOKEN in redacted["context"]
        assert report.by_class["token"] == 1

    def test_occurrences_counted_not_just_detected(self) -> None:
        redacted, report = redact_context(
            {"context": f"{BARE_KEY} between {BARE_KEY} done"}
        )
        assert redacted["context"] == (
            f"{REDACTED_PRIVATE_KEY} between {REDACTED_PRIVATE_KEY} done"
        )
        assert report.by_class["private_key"] == 2
        assert report.total == 2

    def test_input_never_mutated(self) -> None:
        context = {"context": f"key: {BARE_KEY}"}
        redacted, _ = redact_context(context)
        assert context["context"] == f"key: {BARE_KEY}"
        assert redacted != context


class TestKnownSecrets:
    def test_env_secret_scrubbed(self, monkeypatch) -> None:
        monkeypatch.setenv("QUANTMESH_MODEL_API_KEY", "env-secret-value-1")
        redacted, report = redact_context(
            {"context": "the key is env-secret-value-1, remember"}
        )
        assert redacted["context"] == f"the key is {REDACTED_ENV_SECRET}, remember"
        assert report.by_class["env_secret"] == 1

    def test_unrelated_env_vars_ignored(self, monkeypatch) -> None:
        monkeypatch.setenv("QUANTMESH_MODEL_NAME", "llama-3.1")
        monkeypatch.setenv("PATH", "env-secret-value-1")
        redacted, report = redact_context({"context": "env-secret-value-1"})
        assert redacted["context"] == "env-secret-value-1"
        assert report.total == 0

    def test_explicit_secrets_override_environment(self, monkeypatch) -> None:
        monkeypatch.setenv("QUANTMESH_MODEL_API_KEY", "env-secret-value-1")
        redacted, report = redact_context(
            {"context": "env-secret-value-1 and pinned-secret-9"},
            secrets={"QUANTMESH_MODEL_API_KEY": "pinned-secret-9"},
        )
        assert REDACTED_ENV_SECRET in redacted["context"]
        assert "pinned-secret-9" not in redacted["context"]
        assert "env-secret-value-1" in redacted["context"]  # env ignored, intact
        assert report.by_class["env_secret"] == 1

    def test_nested_secret_replaced_longest_first(self) -> None:
        redacted, report = redact_context(
            {"context": "wrap short inside long-short-x"},
            secrets={"QUANTMESH_A": "short", "QUANTMESH_B": "long-short-x"},
        )
        assert redacted["context"] == f"wrap {REDACTED_ENV_SECRET} inside {REDACTED_ENV_SECRET}"
        assert report.by_class["env_secret"] == 2


class TestRefusals:
    def test_non_string_context_content_refused(self) -> None:
        with pytest.raises(RedactionError, match="content must be a string"):
            redact_context({"context": 42})

    def test_non_string_context_name_refused(self) -> None:
        with pytest.raises(RedactionError, match="name must be a string"):
            redact_context({7: "text"})

    def test_non_string_secret_entry_refused(self) -> None:
        with pytest.raises(RedactionError, match="must be strings"):
            redact_context({"context": "x"}, secrets={"QUANTMESH_A": 42})

    def test_secret_in_document_text_scrubbed(self) -> None:
        # Prompt-injection containment: retrieved document text carrying
        # a known key (and a key-shaped blob) must be scrubbed, and the
        # raw secret must never reach the output.
        payload = {
            "context": f"source: injected key {PRIVATE_KEY} and token {BARE_KEY}",
            "retrieved": f"document says: key is env-secret-value-1 here {PRIVATE_KEY}",
        }
        redacted, report = redact_context(
            payload, secrets={"QUANTMESH_MODEL_API_KEY": "env-secret-value-1"}
        )
        joined = " ".join(redacted.values())
        for raw in (PRIVATE_KEY, BARE_KEY, "env-secret-value-1"):
            assert raw not in joined
        assert REDACTED_PRIVATE_KEY in redacted["context"]
        assert REDACTED_PRIVATE_KEY in redacted["retrieved"]
        assert REDACTED_ENV_SECRET in redacted["retrieved"]
        # Context holds both the 0x-prefixed and the bare 64-hex key;
        # the retrieved text holds another 0x-prefixed one.
        assert report.by_class["private_key"] == 3
        assert report.by_class["env_secret"] == 1

    def test_report_counts_are_non_negative(self) -> None:
        redacted, report = _redact({"context": "clean"})
        assert report.total == 0
        assert all(count >= 0 for count in report.by_class.values())
        assert redacted["context"] == "clean"
