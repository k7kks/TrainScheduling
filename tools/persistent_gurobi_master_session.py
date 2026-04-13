from __future__ import annotations

import argparse
import json
import time
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


class PersistentMasterSession:
    def __init__(self) -> None:
        self.model: gp.Model | None = None
        self.vars_by_name: dict[str, gp.Var] = {}
        self.constrs_by_name: dict[str, gp.Constr] = {}

    def _apply_common_params(self, request: dict) -> None:
        assert self.model is not None
        self.model.Params.OutputFlag = 1 if int(request.get("log_to_console", 0)) else 0
        try:
            self.model.Params.LPWarmStart = 2
        except Exception:
            pass
        time_limit = float(request.get("time_limit", 0.0))
        if time_limit > 0:
            self.model.Params.TimeLimit = time_limit

    def _refresh_handles(self) -> None:
        assert self.model is not None
        self.vars_by_name = {var.VarName: var for var in self.model.getVars()}
        self.constrs_by_name = {constr.ConstrName: constr for constr in self.model.getConstrs()}

    def init_solve(self, request: dict) -> dict:
        if "model" in request:
            self.model = build_model_from_payload(request["model"])
        else:
            lp_path = Path(request["lp_path"])
            self.model = gp.read(str(lp_path))
        self._apply_common_params(request)
        self._refresh_handles()
        self.model.optimize()
        return build_output(self.model, include_duals=True)

    def add_columns_and_solve(self, request: dict) -> dict:
        if self.model is None:
            raise RuntimeError("Persistent master is not initialized")

        self._apply_common_params(request)

        for column in request.get("columns", []):
            coeffs = []
            constrs = []
            for term in column.get("row_coeffs", []):
                row_name = term["row_name"]
                constr = self.constrs_by_name.get(row_name)
                if constr is None:
                    raise KeyError(f"Unknown constraint {row_name} while adding column {column['var_name']}")
                coeffs.append(float(term["coeff"]))
                constrs.append(constr)
            gp_column = gp.Column(coeffs, constrs)
            var = self.model.addVar(
                lb=0.0,
                ub=1.0,
                obj=float(column["cost"]),
                vtype=gp.GRB.CONTINUOUS,
                name=column["var_name"],
                column=gp_column,
            )
            self.vars_by_name[column["var_name"]] = var

        self.model.update()
        self._refresh_handles()

        for bound_update in request.get("bound_updates", []):
            var_name = bound_update["var_name"]
            var = self.vars_by_name.get(var_name)
            if var is None:
                raise KeyError(f"Unknown variable {var_name} while applying bound update")
            var.LB = float(bound_update.get("lb", var.LB))
            var.UB = float(bound_update.get("ub", var.UB))

        for row in request.get("new_rows", []):
            expr = gp.LinExpr()
            for term in row.get("terms", []):
                expr.addTerms(float(term["coeff"]), self.vars_by_name[term["var_name"]])
            sense = row["sense"]
            rhs = float(row["rhs"])
            if sense == "<=":
                constr = self.model.addConstr(expr <= rhs, name=row["row_name"])
            elif sense == ">=":
                constr = self.model.addConstr(expr >= rhs, name=row["row_name"])
            elif sense == "=":
                constr = self.model.addConstr(expr == rhs, name=row["row_name"])
            else:
                raise ValueError(f"Unsupported row sense: {sense}")
            self.constrs_by_name[row["row_name"]] = constr

        self.model.update()
        self._refresh_handles()
        self.model.optimize()
        self._refresh_handles()
        return build_output(self.model, include_duals=True)


def atomic_write_json(path: Path, payload: dict) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Persistent gurobipy master session for CG LP solves.")
    parser.add_argument("--session-dir", required=True)
    parser.add_argument("--poll-seconds", type=float, default=0.05)
    args = parser.parse_args()
    if gp is None:
        raise SystemExit(f"gurobipy is unavailable: {_GUROBI_IMPORT_ERROR}")

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
