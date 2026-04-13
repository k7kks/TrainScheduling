#!/usr/bin/env python3
"""Prototype timetable-master + circulation-subproblem decomposition.

This is an experimental bridge toward a cleaner formulation than the current
column master:

1. Timetable master picks one option per slot and enforces timetable-side
   constraints (coverage, headway, first-car).
2. Circulation subproblem takes the selected options and solves a minimum-cost
   path cover / min-cost flow on the turnback DAG with explicit depot
   source/sink arcs.

The script intentionally keeps the two stages separated. It does not yet add
    Benders cuts back from circulation to the timetable master.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pulp


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_manifest(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value
    return data


def to_int(row: Dict[str, str], key: str, default: int = 0) -> int:
    value = row.get(key, "")
    if value is None or value == "":
        return default
    return int(float(value))


def solve_with_cbc(problem: pulp.LpProblem, time_limit: int | None, msg: bool) -> None:
    solver = pulp.PULP_CBC_CMD(msg=msg, timeLimit=time_limit)
    status = problem.solve(solver)
    if status not in (pulp.LpStatusOptimal, pulp.LpStatusNotSolved, pulp.LpStatusInfeasible):
        raise RuntimeError(f"Unexpected CBC status code: {status}")


@dataclass(frozen=True)
class Slot:
    slot_id: int
    direction: int
    order_in_direction: int
    nominal_departure: int
    headway_nominal_departure: int


@dataclass(frozen=True)
class Option:
    option_id: int
    slot_id: int
    direction: int
    xroad: int
    route_id: int
    departure: int
    arrival: int
    shift_seconds: int
    headway_departure: int
    first_real_departure: int


@dataclass(frozen=True)
class Headway:
    headway_id: int
    lhs_slot_id: int
    rhs_slot_id: int
    min_headway: int
    max_headway: int
    target_gap: int


@dataclass(frozen=True)
class TurnbackArc:
    arc_id: int
    from_option_id: int
    to_option_id: int
    event_id: int
    arc_cost: float
    wait_time: int
    turnback_platform: str


@dataclass(frozen=True)
class DepotInfo:
    out_time: int
    in_time: int
    out_route_id: int
    in_route_id: int


class TimetableCirculationPrototype:
    def __init__(self, instance_dir: Path) -> None:
        self.instance_dir = instance_dir
        self.manifest = read_manifest(instance_dir / "manifest.txt")

        self.slots: Dict[int, Slot] = {}
        self.options: Dict[int, Option] = {}
        self.options_by_slot: Dict[int, List[int]] = defaultdict(list)
        self.headways: List[Headway] = []
        self.turnback_arcs: List[TurnbackArc] = []
        self.out_arcs_by_option: Dict[int, List[int]] = defaultdict(list)
        self.in_arcs_by_option: Dict[int, List[int]] = defaultdict(list)
        self.first_car_targets: List[Dict[str, int]] = []
        self.depot_by_key: Dict[Tuple[int, int], DepotInfo] = {}
        self.vehicle_cost = int(self.manifest.get("vehicle_cost", "1000"))
        self.cover_penalty = int(self.manifest.get("cover_penalty", "100000"))
        self.cover_extra_penalty = int(self.manifest.get("cover_extra_penalty", str(self.cover_penalty * 4)))
        self.headway_target_penalty = int(self.manifest.get("headway_target_penalty", "100"))
        self.first_car_penalty = self.cover_penalty
        self._load()

    def _load(self) -> None:
        for row in read_csv(self.instance_dir / "slots.csv"):
            slot = Slot(
                slot_id=to_int(row, "slot_id"),
                direction=to_int(row, "direction"),
                order_in_direction=to_int(row, "order_in_direction"),
                nominal_departure=to_int(row, "nominal_departure"),
                headway_nominal_departure=to_int(row, "headway_nominal_departure", to_int(row, "nominal_departure")),
            )
            self.slots[slot.slot_id] = slot

        for row in read_csv(self.instance_dir / "options.csv"):
            option = Option(
                option_id=to_int(row, "option_id"),
                slot_id=to_int(row, "slot_id"),
                direction=to_int(row, "direction"),
                xroad=to_int(row, "xroad"),
                route_id=to_int(row, "route_id"),
                departure=to_int(row, "departure"),
                arrival=to_int(row, "arrival"),
                shift_seconds=to_int(row, "shift_seconds"),
                headway_departure=to_int(row, "headway_departure", to_int(row, "departure")),
                first_real_departure=to_int(row, "first_real_departure", to_int(row, "departure")),
            )
            self.options[option.option_id] = option
            self.options_by_slot[option.slot_id].append(option.option_id)

        for option_ids in self.options_by_slot.values():
            option_ids.sort(key=lambda option_id: self.options[option_id].departure)

        for row in read_csv(self.instance_dir / "headways.csv"):
            self.headways.append(
                Headway(
                    headway_id=to_int(row, "headway_id"),
                    lhs_slot_id=to_int(row, "lhs_slot_id"),
                    rhs_slot_id=to_int(row, "rhs_slot_id"),
                    min_headway=to_int(row, "min_headway"),
                    max_headway=to_int(row, "max_headway"),
                    target_gap=to_int(row, "target_gap"),
                )
            )

        for row in read_csv(self.instance_dir / "arcs.csv"):
            arc = TurnbackArc(
                arc_id=to_int(row, "arc_id"),
                from_option_id=to_int(row, "from_option_id"),
                to_option_id=to_int(row, "to_option_id"),
                event_id=to_int(row, "event_id", -1),
                arc_cost=float(row.get("arc_cost", "0") or 0.0),
                wait_time=to_int(row, "wait_time"),
                turnback_platform=row.get("turnback_platform", "") or "",
            )
            self.turnback_arcs.append(arc)
            self.out_arcs_by_option[arc.from_option_id].append(arc.arc_id)
            self.in_arcs_by_option[arc.to_option_id].append(arc.arc_id)

        for row in read_csv(self.instance_dir / "depot_routes.csv"):
            key = (to_int(row, "xroad"), to_int(row, "direction"))
            self.depot_by_key[key] = DepotInfo(
                out_time=to_int(row, "depot_out_time"),
                in_time=to_int(row, "depot_in_time"),
                out_route_id=to_int(row, "depot_out_route_id", -1),
                in_route_id=to_int(row, "depot_in_route_id", -1),
            )

        raw_targets = read_csv(self.instance_dir / "first_car_targets.csv")
        for row in raw_targets:
            slot_id = to_int(row, "slot_id")
            target_departure = to_int(row, "target_departure")
            valid_option_ids = [
                option_id
                for option_id in self.options_by_slot.get(slot_id, [])
                if self.options[option_id].first_real_departure == target_departure
            ]
            self.first_car_targets.append(
                {
                    "target_id": to_int(row, "target_id"),
                    "slot_id": slot_id,
                    "target_departure": target_departure,
                    "valid_option_ids": valid_option_ids,
                }
            )

    def option_base_cost(self, option_id: int) -> float:
        shift_minutes = abs(self.options[option_id].shift_seconds) / 60.0
        return shift_minutes * shift_minutes

    def solve_timetable_master(self, time_limit: int | None = None, msg: bool = True) -> Dict[str, object]:
        problem = pulp.LpProblem("timetable_master", pulp.LpMinimize)
        y = {
            option_id: pulp.LpVariable(f"y_{option_id}", lowBound=0, upBound=1, cat="Binary")
            for option_id in self.options
        }
        cover_miss = {
            slot_id: pulp.LpVariable(f"cover_miss_{slot_id}", lowBound=0)
            for slot_id in self.slots
        }
        cover_extra = {
            slot_id: pulp.LpVariable(f"cover_extra_{slot_id}", lowBound=0)
            for slot_id in self.slots
        }
        headway_pos = {
            headway.headway_id: pulp.LpVariable(f"htp_{headway.headway_id}", lowBound=0)
            for headway in self.headways
        }
        headway_neg = {
            headway.headway_id: pulp.LpVariable(f"htn_{headway.headway_id}", lowBound=0)
            for headway in self.headways
        }
        first_car_slack = {
            target["target_id"]: pulp.LpVariable(f"fc_{target['target_id']}", lowBound=0)
            for target in self.first_car_targets
        }

        problem += (
            pulp.lpSum(self.option_base_cost(option_id) * var for option_id, var in y.items())
            + pulp.lpSum(self.cover_penalty * var for var in cover_miss.values())
            + pulp.lpSum(self.cover_extra_penalty * var for var in cover_extra.values())
            + pulp.lpSum(self.headway_target_penalty * (headway_pos[h.headway_id] + headway_neg[h.headway_id]) for h in self.headways)
            + pulp.lpSum(self.first_car_penalty * var for var in first_car_slack.values())
        )

        for slot_id, option_ids in self.options_by_slot.items():
            problem += (
                pulp.lpSum(y[option_id] for option_id in option_ids)
                + cover_miss[slot_id]
                - cover_extra[slot_id]
                == 1,
                f"cover_{slot_id}",
            )

        for headway in self.headways:
            lhs_expr = pulp.lpSum(
                self.options[option_id].headway_departure * y[option_id]
                for option_id in self.options_by_slot.get(headway.lhs_slot_id, [])
            )
            rhs_expr = pulp.lpSum(
                self.options[option_id].headway_departure * y[option_id]
                for option_id in self.options_by_slot.get(headway.rhs_slot_id, [])
            )
            gap_expr = rhs_expr - lhs_expr
            problem += (gap_expr >= headway.min_headway, f"headway_lb_{headway.headway_id}")
            problem += (gap_expr <= headway.max_headway, f"headway_ub_{headway.headway_id}")
            problem += (
                gap_expr - headway_pos[headway.headway_id] + headway_neg[headway.headway_id]
                == headway.target_gap,
                f"headway_target_{headway.headway_id}",
            )

        for target in self.first_car_targets:
            valid_option_ids = target["valid_option_ids"]
            if not valid_option_ids:
                continue
            problem += (
                pulp.lpSum(y[option_id] for option_id in valid_option_ids)
                + first_car_slack[target["target_id"]]
                >= 1,
                f"first_car_{target['target_id']}",
            )

        solve_with_cbc(problem, time_limit=time_limit, msg=msg)
        selected_option_ids = [
            option_id for option_id, var in y.items() if pulp.value(var) is not None and pulp.value(var) > 0.5
        ]
        selected_option_ids.sort(key=lambda option_id: self.options[option_id].departure)
        return {
            "status": pulp.LpStatus[problem.status],
            "objective": float(pulp.value(problem.objective) or 0.0),
            "selected_option_ids": selected_option_ids,
            "cover_miss_total": float(sum(pulp.value(var) or 0.0 for var in cover_miss.values())),
            "cover_extra_total": float(sum(pulp.value(var) or 0.0 for var in cover_extra.values())),
            "headway_dev_total": float(
                sum((pulp.value(headway_pos[h.headway_id]) or 0.0) + (pulp.value(headway_neg[h.headway_id]) or 0.0) for h in self.headways)
            ),
            "first_car_slack_total": float(sum(pulp.value(var) or 0.0 for var in first_car_slack.values())),
        }

    def solve_circulation_subproblem(
        self,
        selected_option_ids: Iterable[int],
        time_limit: int | None = None,
        msg: bool = True,
    ) -> Dict[str, object]:
        selected_ids = list(selected_option_ids)
        selected_set = set(selected_ids)
        problem = pulp.LpProblem("circulation_subproblem", pulp.LpMinimize)

        internal_arc_ids = [
            arc.arc_id
            for arc in self.turnback_arcs
            if arc.from_option_id in selected_set and arc.to_option_id in selected_set
        ]

        z_arc = {
            arc_id: pulp.LpVariable(f"z_arc_{arc_id}", lowBound=0, upBound=1, cat="Binary")
            for arc_id in internal_arc_ids
        }
        z_source = {
            option_id: pulp.LpVariable(f"z_src_{option_id}", lowBound=0, upBound=1, cat="Binary")
            for option_id in selected_ids
        }
        z_sink = {
            option_id: pulp.LpVariable(f"z_sink_{option_id}", lowBound=0, upBound=1, cat="Binary")
            for option_id in selected_ids
        }

        source_cost = {}
        sink_cost = {}
        for option_id in selected_ids:
            option = self.options[option_id]
            depot = self.depot_by_key.get((option.xroad, option.direction))
            source_cost[option_id] = (depot.out_time / 600.0) if depot else 0.0
            sink_cost[option_id] = (depot.in_time / 600.0) if depot else 0.0

        problem += (
            pulp.lpSum((self.vehicle_cost + source_cost[option_id]) * z_source[option_id] for option_id in selected_ids)
            + pulp.lpSum(sink_cost[option_id] * z_sink[option_id] for option_id in selected_ids)
            + pulp.lpSum(self.turnback_arc_by_id(arc_id).arc_cost * z_arc[arc_id] for arc_id in internal_arc_ids)
        )

        for option_id in selected_ids:
            incoming = [
                arc_id
                for arc_id in self.in_arcs_by_option.get(option_id, [])
                if arc_id in z_arc
            ]
            outgoing = [
                arc_id
                for arc_id in self.out_arcs_by_option.get(option_id, [])
                if arc_id in z_arc
            ]
            problem += (z_source[option_id] + pulp.lpSum(z_arc[arc_id] for arc_id in incoming) == 1, f"in_{option_id}")
            problem += (z_sink[option_id] + pulp.lpSum(z_arc[arc_id] for arc_id in outgoing) == 1, f"out_{option_id}")

        solve_with_cbc(problem, time_limit=time_limit, msg=msg)

        chosen_arc_ids = [arc_id for arc_id, var in z_arc.items() if pulp.value(var) and pulp.value(var) > 0.5]
        source_option_ids = [option_id for option_id, var in z_source.items() if pulp.value(var) and pulp.value(var) > 0.5]
        sink_option_ids = [option_id for option_id, var in z_sink.items() if pulp.value(var) and pulp.value(var) > 0.5]
        return {
            "status": pulp.LpStatus[problem.status],
            "objective": float(pulp.value(problem.objective) or 0.0),
            "vehicle_count": len(source_option_ids),
            "chosen_arc_ids": sorted(chosen_arc_ids),
            "source_option_ids": sorted(source_option_ids),
            "sink_option_ids": sorted(sink_option_ids),
        }

    def turnback_arc_by_id(self, arc_id: int) -> TurnbackArc:
        # The instance is not large enough for this linear fallback to matter in the prototype.
        for arc in self.turnback_arcs:
            if arc.arc_id == arc_id:
                return arc
        raise KeyError(arc_id)


def write_csv(path: Path, rows: List[Dict[str, object]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prototype timetable master + circulation subproblem")
    parser.add_argument("--instance-dir", required=True, help="Path to exported CG instance directory")
    parser.add_argument("--output-dir", required=True, help="Directory for prototype outputs")
    parser.add_argument("--master-time-limit", type=int, default=120)
    parser.add_argument("--subproblem-time-limit", type=int, default=120)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    instance_dir = Path(args.instance_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    proto = TimetableCirculationPrototype(instance_dir)
    master_result = proto.solve_timetable_master(time_limit=args.master_time_limit, msg=not args.quiet)
    circulation_result = proto.solve_circulation_subproblem(
        master_result["selected_option_ids"],
        time_limit=args.subproblem_time_limit,
        msg=not args.quiet,
    )

    selected_rows = []
    for sequence_index, option_id in enumerate(master_result["selected_option_ids"]):
        option = proto.options[option_id]
        slot = proto.slots[option.slot_id]
        depot = proto.depot_by_key.get((option.xroad, option.direction))
        selected_rows.append(
            {
                "sequence_index": sequence_index,
                "slot_id": option.slot_id,
                "option_id": option.option_id,
                "direction": option.direction,
                "xroad": option.xroad,
                "route_id": option.route_id,
                "order_in_direction": slot.order_in_direction,
                "departure": option.departure,
                "arrival": option.arrival,
                "headway_departure": option.headway_departure,
                "shift_seconds": option.shift_seconds,
                "depot_out_route_id": depot.out_route_id if depot else -1,
                "depot_in_route_id": depot.in_route_id if depot else -1,
            }
        )
    write_csv(
        output_dir / "selected_options.csv",
        selected_rows,
        [
            "sequence_index",
            "slot_id",
            "option_id",
            "direction",
            "xroad",
            "route_id",
            "order_in_direction",
            "departure",
            "arrival",
            "headway_departure",
            "shift_seconds",
            "depot_out_route_id",
            "depot_in_route_id",
        ],
    )

    arc_rows = []
    for arc_id in circulation_result["chosen_arc_ids"]:
        arc = proto.turnback_arc_by_id(arc_id)
        arc_rows.append(
            {
                "arc_id": arc.arc_id,
                "from_option_id": arc.from_option_id,
                "to_option_id": arc.to_option_id,
                "wait_time": arc.wait_time,
                "turnback_platform": arc.turnback_platform,
                "arc_cost": arc.arc_cost,
            }
        )
    write_csv(
        output_dir / "circulation_arcs.csv",
        arc_rows,
        ["arc_id", "from_option_id", "to_option_id", "wait_time", "turnback_platform", "arc_cost"],
    )

    summary = {
        "instance_dir": str(instance_dir),
        "master": master_result,
        "circulation": circulation_result,
        "notes": [
            "This is a decoupled prototype: circulation feedback is not yet cut back into the timetable master.",
            "Peak/fleet coupling is not yet enforced in the timetable master of this prototype.",
            "Depot source/sink are explicit in the circulation subproblem objective.",
        ],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
