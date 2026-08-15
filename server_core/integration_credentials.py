"""Protected optional credentials for external KotiBot integrations."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Mapping

from server_core.credentials import read_json_credential


INTEGRATION_CREDENTIAL_NAME = "integration-credentials.json"
INTEGRATION_CREDENTIAL_SCHEMA_VERSION = 1

CLOUDFLARE_API_TOKEN_ENVIRONMENT = "KOTIBOT_CLOUDFLARE_API_TOKEN"
CAMERA_TALK_TURN_USERNAME_ENVIRONMENT = (
    "KOTIBOT_CAMERA_TALK_TURN_USERNAME"
)
CAMERA_TALK_TURN_CREDENTIAL_ENVIRONMENT = (
    "KOTIBOT_CAMERA_TALK_TURN_CREDENTIAL"
)
CAMERA_TALK_ICE_SERVERS_ENVIRONMENT = (
    "KOTIBOT_CAMERA_TALK_ICE_SERVERS"
)

LEGACY_INTEGRATION_CREDENTIAL_ENVIRONMENTS = (
    CLOUDFLARE_API_TOKEN_ENVIRONMENT,
    CAMERA_TALK_TURN_USERNAME_ENVIRONMENT,
    CAMERA_TALK_TURN_CREDENTIAL_ENVIRONMENT,
    CAMERA_TALK_ICE_SERVERS_ENVIRONMENT,
)

_DOCUMENT_TEXT_FIELDS = {
    "cloudflare_api_token": CLOUDFLARE_API_TOKEN_ENVIRONMENT,
    "camera_talk_turn_username": (
        CAMERA_TALK_TURN_USERNAME_ENVIRONMENT
    ),
    "camera_talk_turn_credential": (
        CAMERA_TALK_TURN_CREDENTIAL_ENVIRONMENT
    ),
}
_DOCUMENT_FIELDS = frozenset({
    "version",
    *_DOCUMENT_TEXT_FIELDS,
    "camera_talk_ice_servers",
})
_MAX_TEXT_BYTES = 65536
_MAX_ICE_SERVERS_BYTES = 1024 * 1024


def _clean_text(value, source_name: str) -> str:
    if value in (None, ""):
        return ""

    if not isinstance(value, str):
        raise RuntimeError(
            f"Integration credential has an invalid type: {source_name}"
        )

    text = value.strip()

    if not text:
        return ""

    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError:
        raise RuntimeError(
            f"Integration credential is not valid UTF-8: {source_name}"
        ) from None

    if (
        "\x00" in text
        or "\r" in text
        or "\n" in text
        or len(encoded) > _MAX_TEXT_BYTES
    ):
        raise RuntimeError(
            f"Integration credential is invalid: {source_name}"
        )

    return text


def _clean_ice_servers(value, source_name: str) -> list[dict]:
    if value in (None, ""):
        return []

    parsed = value

    if isinstance(value, str):
        raw = value.strip()

        if not raw:
            return []

        try:
            encoded_raw = raw.encode("utf-8")
        except UnicodeEncodeError:
            raise RuntimeError(
                f"Integration credential is not valid UTF-8: "
                f"{source_name}"
            ) from None

        if "\x00" in raw or len(encoded_raw) > _MAX_ICE_SERVERS_BYTES:
            raise RuntimeError(
                f"Integration credential is invalid: {source_name}"
            )

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            raise RuntimeError(
                f"Integration credential is not valid JSON: {source_name}"
            ) from None

    if isinstance(parsed, dict):
        parsed = [parsed]

    if (
        not isinstance(parsed, list)
        or any(not isinstance(item, dict) for item in parsed)
    ):
        raise RuntimeError(
            f"Integration credential must contain ICE server objects: "
            f"{source_name}"
        )

    try:
        encoded = json.dumps(
            parsed,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise RuntimeError(
            f"Integration credential contains invalid JSON: {source_name}"
        ) from None

    if len(encoded) > _MAX_ICE_SERVERS_BYTES:
        raise RuntimeError(
            f"Integration credential is too large: {source_name}"
        )

    return deepcopy(parsed)


def integration_credential_document_from_environment(
    environment: Mapping[str, str],
) -> dict:
    """Build the closed protected document from named legacy inputs."""
    document = {"version": INTEGRATION_CREDENTIAL_SCHEMA_VERSION}

    for field_name, environment_name in _DOCUMENT_TEXT_FIELDS.items():
        value = _clean_text(
            environment.get(environment_name),
            environment_name,
        )

        if value:
            document[field_name] = value

    ice_servers = _clean_ice_servers(
        environment.get(CAMERA_TALK_ICE_SERVERS_ENVIRONMENT),
        CAMERA_TALK_ICE_SERVERS_ENVIRONMENT,
    )

    if ice_servers:
        document["camera_talk_ice_servers"] = ice_servers

    return document


def validate_integration_credential_document(document: dict) -> dict:
    """Validate and normalize the closed protected credential schema."""
    if not isinstance(document, dict):
        raise RuntimeError(
            "Integration credential document must contain an object"
        )

    if document.get("version") != INTEGRATION_CREDENTIAL_SCHEMA_VERSION:
        raise RuntimeError(
            "Integration credential schema is unsupported"
        )

    unknown_fields = set(document) - _DOCUMENT_FIELDS

    if unknown_fields:
        raise RuntimeError(
            "Integration credential document contains unknown fields"
        )

    normalized = {"version": INTEGRATION_CREDENTIAL_SCHEMA_VERSION}

    for field_name in _DOCUMENT_TEXT_FIELDS:
        value = _clean_text(document.get(field_name), field_name)

        if value:
            normalized[field_name] = value

    ice_servers = _clean_ice_servers(
        document.get("camera_talk_ice_servers"),
        "camera_talk_ice_servers",
    )

    if ice_servers:
        normalized["camera_talk_ice_servers"] = ice_servers

    return normalized


@dataclass(frozen=True)
class IntegrationCredentials:
    cloudflare_api_token: str = ""
    camera_talk_turn_username: str = ""
    camera_talk_turn_credential: str = ""
    _camera_talk_ice_servers: tuple[dict, ...] = ()

    @classmethod
    def from_document(cls, document: dict) -> "IntegrationCredentials":
        normalized = validate_integration_credential_document(document)
        return cls(
            cloudflare_api_token=normalized.get(
                "cloudflare_api_token",
                "",
            ),
            camera_talk_turn_username=normalized.get(
                "camera_talk_turn_username",
                "",
            ),
            camera_talk_turn_credential=normalized.get(
                "camera_talk_turn_credential",
                "",
            ),
            _camera_talk_ice_servers=tuple(
                deepcopy(
                    normalized.get("camera_talk_ice_servers", [])
                )
            ),
        )

    def camera_talk_ice_servers(self) -> list[dict]:
        return deepcopy(list(self._camera_talk_ice_servers))


def load_integration_credentials() -> IntegrationCredentials:
    """Load integrations only from the protected credential document."""
    document = read_json_credential(
        INTEGRATION_CREDENTIAL_NAME,
        required=True,
    )
    return IntegrationCredentials.from_document(document)
