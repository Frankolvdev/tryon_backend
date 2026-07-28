from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


class BeamCredentialError(RuntimeError):
    pass


@dataclass(frozen=True)
class BeamCliAuthResult:
    executable: str
    env: dict[str, str]
    output: str


class BeamCredentialsService:
    """Autenticación Beam encapsulada.

    Beam CLI y SDK Python autentican con el Token. La Primary Key/Workspace ID
    se conserva por separado y nunca sustituye al Token del CLI.
    """

    @staticmethod
    def normalize_token(value: str | None) -> str:
        token = str(value or "").strip()
        if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}:
            token = token[1:-1].strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        return token

    @classmethod
    def require_token(cls, config) -> str:
        token = cls.normalize_token(getattr(config, "api_key", ""))
        if not token:
            raise BeamCredentialError("Configura el Token de Beam.")
        return token

    @classmethod
    def build_env(cls, config, base_env: dict[str, str] | None = None) -> dict[str, str]:
        env = dict(base_env or os.environ.copy())
        token = cls.require_token(config)
        env["BEAM_TOKEN"] = token
        primary_key = str(getattr(config, "workspace", "") or "").strip()
        if primary_key:
            env["BEAM_WORKSPACE_ID"] = primary_key
        return env

    @classmethod
    def configure_cli(
        cls,
        *,
        executable: str,
        config,
        env: dict[str, str],
        timeout_seconds: int = 30,
    ) -> BeamCliAuthResult:
        token = cls.require_token(config)
        configured_env = cls.build_env(config, env)
        completed = subprocess.run(
            [executable, "configure", "default", "--token", token],
            env=configured_env,
            capture_output=True,
            text=True,
            timeout=max(10, int(timeout_seconds)),
        )
        output = "\n".join(
            part.strip() for part in (completed.stdout, completed.stderr) if part and part.strip()
        )
        if completed.returncode != 0:
            raise BeamCredentialError(
                "Beam CLI rechazó el Token. Verifica que pegaste el Token completo "
                "de Beam, no la Primary Key. " + output[-3000:]
            )
        return BeamCliAuthResult(executable=executable, env=configured_env, output=output)


beam_credentials_service = BeamCredentialsService()
