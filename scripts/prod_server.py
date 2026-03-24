"""SSH helper for Observador production operations.

Uses env vars instead of hardcoded credentials:
    PROD_HOST
    PROD_USER
    PROD_PASSWORD
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Iterable


def require_paramiko():
    try:
        import paramiko  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Missing dependency: paramiko. Install with `py -m pip install paramiko`."
        ) from exc
    return paramiko


def get_ssh_config() -> tuple[str, str, str]:
    host = os.getenv("PROD_HOST")
    user = os.getenv("PROD_USER")
    password = os.getenv("PROD_PASSWORD")
    if not host or not user or not password:
        raise SystemExit(
            "Set PROD_HOST, PROD_USER and PROD_PASSWORD before using this script."
        )
    return host, user, password


def run_commands(commands: Iterable[str]) -> int:
    paramiko = require_paramiko()
    host, user, password = get_ssh_config()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=password, timeout=20)
    exit_code = 0
    try:
        for cmd in commands:
            print(f"$ {cmd}")
            stdin, stdout, stderr = client.exec_command(cmd)
            out = stdout.read().decode("utf-8", "replace").strip()
            err = stderr.read().decode("utf-8", "replace").strip()
            code = stdout.channel.recv_exit_status()
            if out:
                print(out)
            if err:
                print(err, file=sys.stderr)
            if code != 0 and exit_code == 0:
                exit_code = code
    finally:
        client.close()
    return exit_code


def cmd_status(_: argparse.Namespace) -> int:
    return run_commands(
        [
            "hostname",
            "docker stack ls",
            "docker service ls",
            "docker service ps observador_backend --no-trunc",
            "docker service ps observador_frontend --no-trunc",
        ]
    )


def cmd_auth_env(_: argparse.Namespace) -> int:
    return run_commands(
        [
            "docker service inspect observador_backend --format '{{json .Spec.TaskTemplate.ContainerSpec.Env}}'"
        ]
    )


def cmd_logs(args: argparse.Namespace) -> int:
    service = args.service
    tail = args.tail
    return run_commands([f"docker service logs {service} --tail {tail}"])


def cmd_restart(args: argparse.Namespace) -> int:
    service = args.service
    return run_commands([f"docker service update --force {service}"])


def cmd_health(_: argparse.Namespace) -> int:
    return run_commands(
        [
            "curl -i https://observadordedominios.com.br",
            "curl -i https://api.observadordedominios.com.br/health",
        ]
    )


def cmd_test_login(args: argparse.Namespace) -> int:
    payload = json.dumps({"email": args.email, "password": args.password})
    safe_payload = payload.replace('"', '\\"')
    command = (
        "curl -i -X POST https://api.observadordedominios.com.br/v1/auth/login "
        f'-H "Content-Type: application/json" -d "{safe_payload}"'
    )
    return run_commands([command])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="Inspect production stack and key services.")
    status.set_defaults(func=cmd_status)

    auth_env = sub.add_parser("auth-env", help="Show backend env list from Docker service spec.")
    auth_env.set_defaults(func=cmd_auth_env)

    logs = sub.add_parser("logs", help="Show service logs.")
    logs.add_argument("--service", default="observador_backend")
    logs.add_argument("--tail", type=int, default=200)
    logs.set_defaults(func=cmd_logs)

    restart = sub.add_parser("restart", help="Force service rolling restart.")
    restart.add_argument("--service", default="observador_backend")
    restart.set_defaults(func=cmd_restart)

    health = sub.add_parser("health", help="Run public URL health checks from the server.")
    health.set_defaults(func=cmd_health)

    login = sub.add_parser("test-login", help="Test production admin login.")
    login.add_argument("--email", required=True)
    login.add_argument("--password", required=True)
    login.set_defaults(func=cmd_test_login)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
