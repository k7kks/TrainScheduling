from __future__ import annotations

import argparse
import json
from pathlib import Path

from coinmp_bridge_common import build_output, build_problem_from_payload, coinmp_available, solve_problem


def main() -> None:
    parser = argparse.ArgumentParser(description="Solve exported master LP/MIP with CoinMP in memory.")
    parser.add_argument("--model-json")
    parser.add_argument("--out-json")
    parser.add_argument("--integer", type=int, default=0)
    parser.add_argument("--time-limit", type=float, default=0.0)
    parser.add_argument("--mip-gap", type=float, default=0.0)
    parser.add_argument("--log-to-console", type=int, default=0)
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
    if not args.model_json or not args.out_json:
        raise SystemExit("--model-json and --out-json are required unless --self-check is used")

    model_payload = json.loads(Path(args.model_json).read_text(encoding="utf-8"))
    out_json = Path(args.out_json)

    try:
        problem, _, _ = build_problem_from_payload(model_payload["model"])
        solver = solve_problem(
            problem,
            time_limit=float(args.time_limit) if float(args.time_limit) > 0 else None,
            mip_gap=float(args.mip_gap) if int(args.integer) and float(args.mip_gap) > 0 else None,
            msg=bool(int(args.log_to_console)),
        )
        payload = build_output(problem, solver, include_duals=(not int(args.integer)))
        out_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
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
        out_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
