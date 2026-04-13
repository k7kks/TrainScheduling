import argparse
import json
from pathlib import Path

import gurobipy as gp


def build_output(model: gp.Model, include_duals: bool) -> dict:
    info = {
        "Status": int(model.Status),
        "SolCount": int(model.SolCount),
        "Runtime": float(model.Runtime),
    }
    try:
        info["IterCount"] = float(model.IterCount)
    except Exception:
        pass
    try:
        info["NodeCount"] = float(model.NodeCount)
    except Exception:
        pass
    if model.SolCount:
        info["ObjVal"] = float(model.ObjVal)

    vars_payload = []
    if model.SolCount:
        for var in model.getVars():
            value = float(var.X)
            if abs(value) > 1e-12:
                vars_payload.append({"VarName": var.VarName, "X": value})

    constr_payload = []
    if include_duals:
        for constr in model.getConstrs():
            try:
                pi = float(constr.Pi)
            except Exception:
                pi = 0.0
            if abs(pi) > 1e-12:
                constr_payload.append({"ConstrName": constr.ConstrName, "Pi": pi})

    return {
        "SolutionInfo": info,
        "Vars": vars_payload,
        "Constrs": constr_payload,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Solve exported master LP/MIP with gurobipy.")
    parser.add_argument("--lp", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--integer", type=int, default=0)
    parser.add_argument("--time-limit", type=float, default=0.0)
    parser.add_argument("--mip-gap", type=float, default=0.0)
    parser.add_argument("--log-to-console", type=int, default=0)
    args = parser.parse_args()

    lp_path = Path(args.lp)
    out_json = Path(args.out_json)

    try:
        model = gp.read(str(lp_path))
        model.Params.OutputFlag = 1 if int(args.log_to_console) else 0
        if float(args.time_limit) > 0:
            model.Params.TimeLimit = float(args.time_limit)
        if int(args.integer):
            if float(args.mip_gap) > 0:
                model.Params.MIPGap = float(args.mip_gap)
        model.optimize()

        payload = build_output(model, include_duals=(not int(args.integer)))
        out_json.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
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
        out_json.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        raise SystemExit(2)


if __name__ == "__main__":
    main()
