from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import gurobipy as gp
    _GUROBI_IMPORT_ERROR = None
except Exception as exc:
    gp = None  # type: ignore
    _GUROBI_IMPORT_ERROR = exc


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


def build_model_from_payload(model_payload: dict) -> gp.Model:
    if gp is None:
        raise RuntimeError(f"gurobipy is unavailable: {_GUROBI_IMPORT_ERROR}")
    model = gp.Model()
    model.ModelSense = gp.GRB.MINIMIZE

    constrs_by_name: dict[str, gp.Constr] = {}
    for row in model_payload.get("rows", []):
        expr = gp.LinExpr()
        sense = row["sense"]
        rhs = float(row["rhs"])
        row_name = row["row_name"]
        if sense == "<=":
            constr = model.addConstr(expr <= rhs, name=row_name)
        elif sense == ">=":
            constr = model.addConstr(expr >= rhs, name=row_name)
        elif sense == "=":
            constr = model.addConstr(expr == rhs, name=row_name)
        else:
            raise ValueError(f"Unsupported row sense: {sense}")
        constrs_by_name[row_name] = constr

    model.update()

    for variable in model_payload.get("variables", []):
        coeffs = []
        constrs = []
        for term in variable.get("row_coeffs", []):
            row_name = term["row_name"]
            constr = constrs_by_name.get(row_name)
            if constr is None:
                raise KeyError(f"Unknown constraint {row_name} while adding variable {variable['var_name']}")
            coeffs.append(float(term["coeff"]))
            constrs.append(constr)
        ub_value = variable.get("ub", None)
        if ub_value is None:
            ub = gp.GRB.INFINITY
        else:
            ub = float(ub_value)
        vtype = gp.GRB.BINARY if variable.get("vtype", "C") == "B" else gp.GRB.CONTINUOUS
        gp_column = gp.Column(coeffs, constrs)
        model.addVar(
            lb=float(variable.get("lb", 0.0)),
            ub=ub,
            obj=float(variable.get("obj", 0.0)),
            vtype=vtype,
            name=variable["var_name"],
            column=gp_column,
        )

    model.update()
    return model


def main() -> None:
    parser = argparse.ArgumentParser(description="Solve exported master LP/MIP with gurobipy.")
    parser.add_argument("--lp")
    parser.add_argument("--model-json")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--integer", type=int, default=0)
    parser.add_argument("--time-limit", type=float, default=0.0)
    parser.add_argument("--mip-gap", type=float, default=0.0)
    parser.add_argument("--log-to-console", type=int, default=0)
    args = parser.parse_args()

    out_json = Path(args.out_json)
    if not args.lp and not args.model_json:
        raise SystemExit("One of --lp or --model-json is required")
    if gp is None:
        raise SystemExit(f"gurobipy is unavailable: {_GUROBI_IMPORT_ERROR}")

    try:
        if args.model_json:
            payload = json.loads(Path(args.model_json).read_text(encoding="utf-8"))
            model = build_model_from_payload(payload["model"])
        else:
            model = gp.read(str(Path(args.lp)))
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
