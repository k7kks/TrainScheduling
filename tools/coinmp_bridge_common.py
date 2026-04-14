from __future__ import annotations

import ctypes
import os
import shutil
import time
from pathlib import Path
from typing import Dict, Tuple

import pulp
from pulp import constants
from pulp.apis.core import LpSolver


def _candidate_coinmp_dlls() -> list[Path]:
    candidates: list[Path] = []

    env_vars = ["COINMP_DLL", "COIN_INSTALL_DIR", "COINMP_DIR"]
    for env_var in env_vars:
        raw = os.environ.get(env_var, "").strip()
        if not raw:
            continue
        path = Path(raw)
        if path.is_file():
            candidates.append(path)
        else:
            candidates.append(path / "bin" / "libCoinMP-1.dll")
            candidates.append(path / "libCoinMP-1.dll")

    for base in (
        Path(r"C:\msys64\ucrt64\bin"),
        Path(r"C:\msys64\mingw64\bin"),
        Path(r"C:\msys64\clang64\bin"),
    ):
        candidates.append(base / "libCoinMP-1.dll")

    cbc_path = shutil.which("cbc")
    if cbc_path:
        cbc_bin = Path(cbc_path).resolve().parent
        candidates.append(cbc_bin / "libCoinMP-1.dll")

    seen: set[Path] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
    return ordered


def resolve_coinmp_dll() -> Path:
    for candidate in _candidate_coinmp_dlls():
        if candidate.exists():
            return candidate
    raise FileNotFoundError("CoinMP DLL not found. Expected libCoinMP-1.dll in a configured COIN/MSYS2 bin directory.")


def coinmp_available() -> tuple[bool, str]:
    try:
        dll_path = resolve_coinmp_dll()
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(dll_path.parent))
        ctypes.WinDLL(str(dll_path))
        return True, str(dll_path)
    except Exception as exc:
        return False, str(exc)


def _load_coinmp_library():
    dll_path = resolve_coinmp_dll()
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(dll_path.parent))
    lib = ctypes.WinDLL(str(dll_path))

    void_p = ctypes.c_void_p
    c_char_p = ctypes.c_char_p
    c_int = ctypes.c_int
    c_double = ctypes.c_double

    lib.CoinInitSolver.argtypes = [c_char_p]
    lib.CoinInitSolver.restype = c_int
    lib.CoinCreateProblem.argtypes = [c_char_p]
    lib.CoinCreateProblem.restype = void_p
    lib.CoinSetIntOption.argtypes = [void_p, c_int, c_int]
    lib.CoinSetIntOption.restype = c_int
    lib.CoinSetRealOption.argtypes = [void_p, c_int, c_double]
    lib.CoinSetRealOption.restype = c_int
    lib.CoinGetInfinity.restype = c_double
    lib.CoinGetVersionStr.restype = c_char_p
    lib.CoinLoadProblem.argtypes = [
        void_p,
        c_int,
        c_int,
        c_int,
        c_int,
        c_int,
        c_double,
        ctypes.POINTER(c_double),
        ctypes.POINTER(c_double),
        ctypes.POINTER(c_double),
        ctypes.c_char_p,
        ctypes.POINTER(c_double),
        ctypes.POINTER(c_double),
        ctypes.POINTER(c_int),
        ctypes.POINTER(c_int),
        ctypes.POINTER(c_int),
        ctypes.POINTER(c_double),
        ctypes.POINTER(c_char_p),
        ctypes.POINTER(c_char_p),
        c_char_p,
    ]
    lib.CoinLoadProblem.restype = c_int
    lib.CoinLoadInteger.argtypes = [void_p, ctypes.c_char_p]
    lib.CoinLoadInteger.restype = c_int
    lib.CoinOptimizeProblem.argtypes = [void_p, c_int]
    lib.CoinOptimizeProblem.restype = c_int
    lib.CoinGetSolutionStatus.argtypes = [void_p]
    lib.CoinGetSolutionStatus.restype = c_int
    lib.CoinGetSolutionText.argtypes = [void_p]
    lib.CoinGetSolutionText.restype = c_char_p
    lib.CoinGetObjectValue.argtypes = [void_p]
    lib.CoinGetObjectValue.restype = c_double
    lib.CoinGetMipBestBound.argtypes = [void_p]
    lib.CoinGetMipBestBound.restype = c_double
    lib.CoinGetSolutionValues.argtypes = [void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    lib.CoinGetSolutionValues.restype = c_int
    lib.CoinFreeSolver.argtypes = []
    lib.CoinFreeSolver.restype = None
    if hasattr(lib, "CoinRegisterMsgLogCallback"):
        lib.CoinRegisterMsgLogCallback.argtypes = [void_p, c_char_p, ctypes.c_void_p]
        lib.CoinRegisterMsgLogCallback.restype = c_int
    return lib


class CoinMPSolver(LpSolver):
    COIN_INT_LOGLEVEL = 7
    COIN_REAL_MAXSECONDS = 16
    COIN_REAL_MIPMAXSEC = 19
    COIN_REAL_MIPFRACGAP = 34

    name = "COINMP_BRIDGE"
    _lib = None

    def __init__(self, mip: bool = True, msg: bool = True, time_limit: float | None = None, gap_rel: float | None = None) -> None:
        super().__init__(mip=mip, msg=msg, timeLimit=time_limit)
        self.fracGap = gap_rel
        self.solution_status_code = -1
        self.solution_text = ""
        self.coin_time = 0.0

    @classmethod
    def available(cls) -> bool:
        ok, _ = coinmp_available()
        return ok

    @classmethod
    def _get_lib(cls):
        if cls._lib is None:
            cls._lib = _load_coinmp_library()
        return cls._lib

    def actualSolve(self, lp):
        lib = self._get_lib()
        lib.CoinInitSolver(b"")
        h_prob = lib.CoinCreateProblem(lp.name.encode("utf-8"))
        lib.CoinSetIntOption(h_prob, self.COIN_INT_LOGLEVEL, int(bool(self.msg)))
        if self.timeLimit:
            if self.mip:
                lib.CoinSetRealOption(h_prob, self.COIN_REAL_MIPMAXSEC, ctypes.c_double(float(self.timeLimit)))
            else:
                lib.CoinSetRealOption(h_prob, self.COIN_REAL_MAXSECONDS, ctypes.c_double(float(self.timeLimit)))
        if self.fracGap is not None:
            lib.CoinSetRealOption(h_prob, self.COIN_REAL_MIPFRACGAP, ctypes.c_double(float(self.fracGap)))

        (
            num_vars,
            num_rows,
            numels,
            range_count,
            object_sense,
            object_coeffs,
            object_const,
            rhs_values,
            range_values,
            row_type,
            starts_base,
            len_base,
            ind_base,
            elem_base,
            lower_bounds,
            upper_bounds,
            init_values,
            col_names,
            row_names,
            column_type,
            n2v,
            n2c,
        ) = self.getCplexStyleArrays(lp)

        lib.CoinLoadProblem(
            h_prob,
            num_vars,
            num_rows,
            numels,
            range_count,
            object_sense,
            object_const,
            object_coeffs,
            lower_bounds,
            upper_bounds,
            row_type,
            rhs_values,
            range_values,
            starts_base,
            len_base,
            ind_base,
            elem_base,
            col_names,
            row_names,
            b"Objective",
        )
        if lp.isMIP() and self.mip:
            lib.CoinLoadInteger(h_prob, column_type)

        if not self.msg and hasattr(lib, "CoinRegisterMsgLogCallback"):
            try:
                lib.CoinRegisterMsgLogCallback(h_prob, b"", ctypes.c_void_p())
            except Exception:
                pass

        start = time.perf_counter()
        lib.CoinOptimizeProblem(h_prob, 0)
        self.coin_time = time.perf_counter() - start

        self.solution_status_code = lib.CoinGetSolutionStatus(h_prob)
        raw_text = lib.CoinGetSolutionText(h_prob)
        self.solution_text = raw_text.decode("utf-8", errors="replace") if raw_text else ""

        num_var_double_array = ctypes.c_double * num_vars
        num_row_double_array = ctypes.c_double * num_rows
        c_activity = num_var_double_array()
        c_reduced_cost = num_var_double_array()
        c_slack_values = num_row_double_array()
        c_shadow_prices = num_row_double_array()
        lib.CoinGetSolutionValues(
            h_prob,
            ctypes.byref(c_activity),
            ctypes.byref(c_reduced_cost),
            ctypes.byref(c_slack_values),
            ctypes.byref(c_shadow_prices),
        )

        lp.assignVarsVals({n2v[i].name: c_activity[i] for i in range(num_vars)})
        lp.assignVarsDj({n2v[i].name: c_reduced_cost[i] for i in range(num_vars)})
        lp.assignConsPi({n2c[i]: c_shadow_prices[i] for i in range(num_rows)})
        lp.assignConsSlack({n2c[i]: c_slack_values[i] for i in range(num_rows)})
        if lp.isMIP() and self.mip:
            lp.bestBound = lib.CoinGetMipBestBound(h_prob)

        status_map = {
            0: constants.LpStatusOptimal,
            1: constants.LpStatusInfeasible,
            2: constants.LpStatusInfeasible,
            3: constants.LpStatusNotSolved,
            4: constants.LpStatusNotSolved,
            5: constants.LpStatusNotSolved,
            -1: constants.LpStatusUndefined,
        }
        lib.CoinFreeSolver()
        status = status_map.get(self.solution_status_code, constants.LpStatusUndefined)
        lp.assignStatus(status)
        return status


def _constraint_sense(sense: str) -> int:
    mapping = {
        "<=": pulp.LpConstraintLE,
        ">=": pulp.LpConstraintGE,
        "=": pulp.LpConstraintEQ,
    }
    if sense not in mapping:
        raise ValueError(f"Unsupported row sense: {sense}")
    return mapping[sense]


def build_problem_from_payload(model_payload: dict) -> Tuple[pulp.LpProblem, Dict[str, pulp.LpVariable], Dict[str, pulp.LpConstraint]]:
    problem_sense = pulp.LpMinimize if model_payload.get("sense", "min") == "min" else pulp.LpMaximize
    problem = pulp.LpProblem("master", problem_sense)
    vars_by_name: Dict[str, pulp.LpVariable] = {}
    constraints_by_name: Dict[str, pulp.LpConstraint] = {}

    for row in model_payload.get("rows", []):
        constraint = pulp.LpConstraint(
            e=pulp.LpAffineExpression(),
            sense=_constraint_sense(row["sense"]),
            rhs=float(row["rhs"]),
            name=row["row_name"],
        )
        problem += constraint
        constraints_by_name[row["row_name"]] = problem.constraints[row["row_name"]]

    objective = pulp.LpAffineExpression()
    for variable in model_payload.get("variables", []):
        upper_bound = variable.get("ub")
        category = pulp.LpBinary if variable.get("vtype", "C") == "B" else pulp.LpContinuous
        var = pulp.LpVariable(
            variable["var_name"],
            lowBound=float(variable.get("lb", 0.0)),
            upBound=None if upper_bound is None else float(upper_bound),
            cat=category,
        )
        vars_by_name[variable["var_name"]] = var
        objective += float(variable.get("obj", 0.0)) * var
        for row_coeff in variable.get("row_coeffs", []):
            constraints_by_name[row_coeff["row_name"]].addInPlace(var * float(row_coeff["coeff"]))

    problem.setObjective(objective)
    return problem, vars_by_name, constraints_by_name


def add_incremental_payload(
    problem: pulp.LpProblem,
    vars_by_name: Dict[str, pulp.LpVariable],
    constraints_by_name: Dict[str, pulp.LpConstraint],
    request: dict,
) -> None:
    objective = problem.objective or pulp.LpAffineExpression()

    for column in request.get("columns", []):
        upper_bound = column.get("ub", 1.0)
        category = pulp.LpBinary if column.get("vtype", "C") == "B" else pulp.LpContinuous
        var = pulp.LpVariable(
            column["var_name"],
            lowBound=float(column.get("lb", 0.0)),
            upBound=None if upper_bound is None else float(upper_bound),
            cat=category,
        )
        vars_by_name[column["var_name"]] = var
        objective += float(column.get("cost", column.get("obj", 0.0))) * var
        for term in column.get("row_coeffs", []):
            constraints_by_name[term["row_name"]].addInPlace(var * float(term["coeff"]))

    for bound_update in request.get("bound_updates", []):
        var = vars_by_name[bound_update["var_name"]]
        if "lb" in bound_update:
            var.lowBound = float(bound_update["lb"])
        if "ub" in bound_update:
            ub = bound_update["ub"]
            var.upBound = None if ub is None else float(ub)

    for row in request.get("new_rows", []):
        constraint = pulp.LpConstraint(
            e=pulp.LpAffineExpression(),
            sense=_constraint_sense(row["sense"]),
            rhs=float(row["rhs"]),
            name=row["row_name"],
        )
        problem += constraint
        constraints_by_name[row["row_name"]] = problem.constraints[row["row_name"]]
        for term in row.get("terms", []):
            constraints_by_name[row["row_name"]].addInPlace(vars_by_name[term["var_name"]] * float(term["coeff"]))

    for variable in request.get("new_variables", []):
        upper_bound = variable.get("ub")
        category = pulp.LpBinary if variable.get("vtype", "C") == "B" else pulp.LpContinuous
        var = pulp.LpVariable(
            variable["var_name"],
            lowBound=float(variable.get("lb", 0.0)),
            upBound=None if upper_bound is None else float(upper_bound),
            cat=category,
        )
        vars_by_name[variable["var_name"]] = var
        objective += float(variable.get("obj", 0.0)) * var
        for row_coeff in variable.get("row_coeffs", []):
            constraints_by_name[row_coeff["row_name"]].addInPlace(var * float(row_coeff["coeff"]))

    problem.setObjective(objective)


def solve_problem(problem: pulp.LpProblem, time_limit: float | None, mip_gap: float | None, msg: bool) -> CoinMPSolver:
    solver = CoinMPSolver(mip=problem.isMIP(), msg=msg, time_limit=time_limit, gap_rel=mip_gap)
    status = problem.solve(solver)
    if status not in (pulp.LpStatusOptimal, pulp.LpStatusNotSolved, pulp.LpStatusInfeasible, pulp.LpStatusUndefined):
        raise RuntimeError(f"Unexpected CoinMP/PuLP status code: {status}")
    return solver


def build_output(problem: pulp.LpProblem, solver: CoinMPSolver, include_duals: bool) -> dict:
    solution_vars = []
    solution_count = 0
    for var in problem.variables():
        value = var.value()
        if value is None:
            continue
        solution_count = 1
        value_f = float(value)
        if abs(value_f) > 1e-12:
            solution_vars.append({"VarName": var.name, "X": value_f})

    constr_payload = []
    if include_duals:
        for name, constraint in problem.constraints.items():
            pi = getattr(constraint, "pi", None)
            if pi is None:
                continue
            pi_f = float(pi)
            if abs(pi_f) > 1e-12:
                constr_payload.append({"ConstrName": name, "Pi": pi_f})

    if problem.status == pulp.LpStatusOptimal:
        status_code = 2
    elif solution_count > 0:
        status_code = 9
    else:
        status_code = 3

    info = {
        "Status": int(status_code),
        "SolCount": int(solution_count),
        "Runtime": float(solver.coin_time),
        "StatusText": solver.solution_text,
        "RawStatus": int(solver.solution_status_code),
    }
    if solution_count > 0:
        info["ObjVal"] = float(pulp.value(problem.objective))

    return {
        "SolutionInfo": info,
        "Vars": solution_vars,
        "Constrs": constr_payload,
    }
