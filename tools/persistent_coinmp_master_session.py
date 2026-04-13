from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from coinmp_bridge_common import (
    add_incremental_payload,
    build_output,
    build_problem_from_payload,
    coinmp_available,
    solve_problem,
)


class PersistentMasterSession:
    def __init__(self) -> None:
        self.problem = None
        self.vars_by_name = {}
        self.constraints_by_name = {}

    def init_solve(self, request: dict) -> dict:
        self.problem, self.vars_by_name, self.constraints_by_name = build_problem_from_payload(request["model"])
        solver = solve_problem(
            self.problem,
            time_limit=float(request.get("time_limit", 0.0)) or None,
            mip_gap=None,
            msg=bool(int(request.get("log_to_console", 0))),
        )
        return build_output(self.problem, solver, include_duals=True)

    def add_columns_and_solve(self, request: dict) -> dict:
        if self.problem is None:
            raise RuntimeError("Persistent master is not initialized")
        add_incremental_payload(self.problem, self.vars_by_name, self.constraints_by_name, request)
        solver = solve_problem(
            self.problem,
            time_limit=float(request.get("time_limit", 0.0)) or None,
            mip_gap=None,
            msg=bool(int(request.get("log_to_console", 0))),
        )
        return build_output(self.problem, solver, include_duals=True)


def atomic_write_json(path: Path, payload: dict) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Persistent CoinMP master session for CG solves.")
    parser.add_argument("--session-dir")
    parser.add_argument("--poll-seconds", type=float, default=0.05)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()

    ok, detail = coinmp_available()
    if args.self_check:
        if ok:
            print(detail)
            raise SystemExit(0)
        raise SystemExit(detail)
    if not ok:
        raise SystemExit(f"CoinMP is unavailable: {detail}")
    if not args.session_dir:
        raise SystemExit("--session-dir is required unless --self-check is used")

    session_dir = Path(args.session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    request_path = session_dir / "request.json"
    response_path = session_dir / "response.json"
    processing_path = session_dir / "request.processing.json"

    session = PersistentMasterSession()

    while True:
        if not request_path.exists():
            time.sleep(args.poll_seconds)
            continue

        if processing_path.exists():
            processing_path.unlink()
        request_path.replace(processing_path)
        request = json.loads(processing_path.read_text(encoding="utf-8"))
        processing_path.unlink(missing_ok=True)

        command = request.get("command", "")
        try:
            if command == "init_solve":
                payload = session.init_solve(request)
            elif command == "add_columns_and_solve":
                payload = session.add_columns_and_solve(request)
            elif command == "shutdown":
                atomic_write_json(response_path, {"Status": "shutdown"})
                break
            else:
                raise ValueError(f"Unknown command: {command}")
        except Exception as exc:
            payload = {
                "SolutionInfo": {
                    "Status": -1,
                    "SolCount": 0,
                    "Runtime": 0.0,
                },
                "Vars": [],
                "Constrs": [],
                "Error": str(exc),
            }

        atomic_write_json(response_path, payload)


if __name__ == "__main__":
    main()
