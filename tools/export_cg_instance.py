import argparse
import csv
import math
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from Engineering import Engineering  # type: ignore
import pulp  # type: ignore


def _time_to_str(value: int) -> str:
    value = int(value)
    hours = value // 3600
    minutes = (value % 3600) // 60
    seconds = value % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


OPTION_SHIFT_STEP_SEC = 60
OPTION_SHIFT_LIMIT_SEC = 180
HEADWAY_SHIFT_CAP_SEC = 600
SOFT_TURNBACK_EXTENSION_SEC = 360


def _option_step(target_gap: int, explicit_step: Optional[int]) -> int:
    if explicit_step is not None and explicit_step > 0:
        return explicit_step
    return OPTION_SHIFT_STEP_SEC


def _default_shift_candidates() -> List[int]:
    return list(range(-OPTION_SHIFT_LIMIT_SEC, OPTION_SHIFT_LIMIT_SEC + OPTION_SHIFT_STEP_SEC, OPTION_SHIFT_STEP_SEC))


def _soft_turnback_arc_cost(wait_time: int, min_tb: int, def_tb: int, max_tb: int, is_mixed: bool) -> float:
    wait_delta_min = abs(wait_time - def_tb) / 60.0
    mixed_penalty = 0.35 if is_mixed else 0.0
    short_violation_min = max(0.0, min_tb - wait_time) / 60.0
    long_violation_min = max(0.0, wait_time - max_tb) / 60.0
    infeasibility_penalty = 0.0
    if short_violation_min > 0.0:
        infeasibility_penalty += 25.0 * short_violation_min * short_violation_min
    if long_violation_min > 0.0:
        infeasibility_penalty += 10.0 * long_violation_min * long_violation_min
    return round(wait_delta_min + infeasibility_penalty + mixed_penalty, 6)


def _bounded_headway_window(target_gap: int, actual_gaps: List[int]) -> Tuple[int, int]:
    lower_cap = target_gap - HEADWAY_SHIFT_CAP_SEC
    upper_cap = target_gap + HEADWAY_SHIFT_CAP_SEC
    bounded_gaps = [gap for gap in actual_gaps if lower_cap <= gap <= upper_cap and gap >= 0]
    if bounded_gaps:
        return min(bounded_gaps), max(bounded_gaps)

    # Keep the hard headway row feasible even if exact/seed shifts push every
    # exported combination outside the preferred +/-10 minute band.
    nonnegative_gaps = [gap for gap in actual_gaps if gap >= 0]
    if nonnegative_gaps:
        nearest_gap = min(nonnegative_gaps, key=lambda gap: (abs(gap - target_gap), abs(gap)))
        return nearest_gap, nearest_gap

    nearest_gap = min(actual_gaps, key=lambda gap: (abs(gap - target_gap), abs(gap)))
    nearest_gap = max(0, nearest_gap)
    return nearest_gap, nearest_gap


def _headway_window_options(option_rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    bounded_options = [
        row for row in option_rows
        if abs(int(row["shift_seconds"])) <= HEADWAY_SHIFT_CAP_SEC
    ]
    return bounded_options or option_rows


def _get_platform_safe(eng: Engineering, platform_code: Optional[str]):
    if not platform_code:
        return None
    return eng.rl.platformList.get(platform_code)


def _common_turnback_platform(eng: Engineering, rs, rs_oppo) -> Tuple[bool, Optional[str]]:
    rs_tail = [code for code in rs.stopped_platforms[max(0, len(rs.stopped_platforms) - 2):]]
    oppo_head = [code for code in rs_oppo.stopped_platforms[:2]]
    for candidate in rs_tail:
        if candidate in oppo_head and candidate in eng.rl.turnbackList:
            return True, candidate
    for candidate in rs_tail:
        if candidate in oppo_head:
            return True, candidate
    return False, None


def _slot_turnback_platform(eng: Engineering, rs) -> Optional[str]:
    if not rs.stopped_platforms:
        return None
    tail = rs.stopped_platforms[-1]
    if tail in eng.rl.turnbackList:
        return tail
    if len(rs.stopped_platforms) >= 2:
        prev_tail = rs.stopped_platforms[-2]
        if prev_tail in eng.rl.turnbackList:
            return prev_tail
    return tail


def _find_first_real_stop(eng: Engineering, rs) -> Tuple[int, Optional[str], Optional[int]]:
    for idx, platform_code in enumerate(rs.stopped_platforms):
        platform = eng.rl.platformList.get(platform_code)
        if platform is None or platform.is_virtual:
            continue
        if idx >= len(rs.dep_time):
            return -1, None, None
        return idx, platform_code, int(rs.dep_time[idx])
    return -1, None, None


def _find_last_real_stop(eng: Engineering, rs) -> Tuple[int, Optional[str], Optional[int]]:
    for idx in range(len(rs.stopped_platforms) - 1, -1, -1):
        platform_code = rs.stopped_platforms[idx]
        platform = eng.rl.platformList.get(platform_code)
        if platform is None or platform.is_virtual:
            continue
        if idx >= len(rs.arr_time):
            return -1, None, None
        return idx, platform_code, int(rs.arr_time[idx])
    return -1, None, None


def _infer_depot_gate_gap(eng: Engineering, trips_by_dir, xroad: int, direction: int) -> int:
    representative_trip = None
    for rs in trips_by_dir[direction]:
        if int(getattr(rs, "xroad", -1)) == xroad:
            representative_trip = rs
            break

    if representative_trip is None:
        return 180

    gap_candidates: List[int] = []
    _first_idx, first_platform_code, _first_departure = _find_first_real_stop(eng, representative_trip)
    _last_idx, last_platform_code, _last_arrival = _find_last_real_stop(eng, representative_trip)

    for platform_code in (first_platform_code, last_platform_code):
        platform = _get_platform_safe(eng, platform_code)
        if platform is None:
            continue
        min_track_time = int(getattr(platform, "min_track_time", 0) or 0)
        if min_track_time > 0:
            gap_candidates.append(min_track_time)

    return max(gap_candidates) if gap_candidates else 180


def _compute_depot_routes(eng: Engineering, trips_by_dir) -> List[Dict[str, object]]:
    """Extract depot travel times for each xroad/direction combination.

    Returns rows with fields: xroad, direction, depot_in_time, depot_out_time,
    depot_gate_gap.
    - depot_out: time for vehicle to travel from depot to first mainline platform
      (inout=1 in DepotRoutesInfo)
    - depot_in:  time for vehicle to travel from last mainline platform back to depot
      (inout=0 in DepotRoutesInfo)
        - depot_gate_gap: minimum headway between consecutive vehicles using the same
            depot approach track. This is approximated by the boundary mainline
            platform min_track_time from representative phase1 trips, which matches the
            legacy conflict model better than using the full depot travel time.
    """
    rows: List[Dict[str, object]] = []
    dpis = getattr(eng.us, "depot_routes_infos", [])
    for xroad, dpi in enumerate(dpis):
        for direction in range(2):
            # inout=0 -> depot-in segments
            in_segs: List[int] = []
            if len(dpi.routes_time[0]) > direction:
                in_segs = [
                    t for t in dpi.routes_time[0][direction]
                    if isinstance(t, (int, float)) and t > 0
                ]
            # inout=1 -> depot-out segments
            out_segs: List[int] = []
            if len(dpi.routes_time[1]) > direction:
                out_segs = [
                    t for t in dpi.routes_time[1][direction]
                    if isinstance(t, (int, float)) and t > 0
                ]
            gate_gap = _infer_depot_gate_gap(eng, trips_by_dir, xroad, direction)
            rows.append(
                {
                    "xroad": xroad,
                    "direction": direction,
                    "depot_in_time": int(sum(in_segs)),
                    "depot_out_time": int(sum(out_segs)),
                    "depot_gate_gap": gate_gap,
                }
            )
    return rows


def _first_real_platform_of_route(eng: Engineering, route_id: str) -> Optional[str]:
    path = eng.rl.pathList.get(route_id)
    if path is None:
        return None
    for platform_code in path.nodeList:
        if not eng.rl.is_platform_virtual(platform_code):
            return platform_code
    return None


def _select_first_car_target(
    eng: Engineering,
    direction: int,
    trips,
) -> Optional[Dict[str, object]]:
    """Select the fleet-completing train as the first-car target.

    If the first peak requires *train_num* vehicles, the fleet ramps up by
    alternating up/down departures.  The last train in each direction to
    complete the fleet must depart at ``eng.us.first_car``.  For direction 0
    (up) that is train number ``peak.up_train_num``; for direction 1 (down)
    it is ``peak.dn_train_num``.
    """
    if not getattr(eng.us, "peaks", None):
        return None
    if eng.us.first_car <= 0:
        return None

    peak = eng.us.peaks[0]
    if not getattr(peak, "routes", None):
        return None

    # Number of trains in this direction needed to complete the fleet
    target_count = peak.up_train_num if direction == 0 else peak.dn_train_num
    if target_count <= 0:
        return None

    # Sort all trips by physical departure; the fleet-completing trip
    # is at 0-based index ``target_count - 1``.
    sorted_trips = sorted(trips, key=lambda rs: int(rs.dep_time[0]))
    target_pos = min(target_count - 1, len(sorted_trips) - 1)
    if target_pos < 0:
        return None

    target_rs = sorted_trips[target_pos]

    # Determine the first real platform for this trip's own route.
    route_id = str(target_rs.car_info.route_num)
    target_platform = _first_real_platform_of_route(eng, route_id)
    # Fallback: use the big-route first real platform.
    if target_platform is None:
        big_route = peak.routes[0]
        fallback_route = big_route.up_route if direction == 0 else big_route.down_route
        target_platform = _first_real_platform_of_route(eng, fallback_route)
    if target_platform is None:
        return None

    # Find the departure time at that platform.
    target_idx = -1
    for idx, platform_code in enumerate(target_rs.stopped_platforms):
        if platform_code == target_platform:
            target_idx = idx
            break
    if target_idx < 0 or target_idx >= len(target_rs.dep_time):
        # Platform not in route stops; use the first real stop instead.
        fr_idx, fr_platform, _fr_dep = _find_first_real_stop(eng, target_rs)
        if fr_idx < 0:
            return None
        target_platform = fr_platform
        target_idx = fr_idx

    target_dep = int(target_rs.dep_time[target_idx])
    return {
        "direction": direction,
        "route_id": route_id,
        "target_platform": target_platform,
        "round_num": int(target_rs.car_info.round_num),
        "target_departure": int(eng.us.first_car),
        "nominal_target_departure": target_dep,
        "gap": abs(target_dep - int(eng.us.first_car)),
    }


def _mixed_target_platform(eng: Engineering, rs, rs_oppo) -> Optional[str]:
    route_num = str(rs_oppo.car_info.route_num)
    path = eng.rl.pathList.get(route_num)
    if path is None or not path.nodeList:
        return None
    if rs.xroad == 1:
        return path.nodeList[0]
    if len(path.nodeList) > 1:
        return path.nodeList[1]
    return path.nodeList[0]


def _turnback_meta(
    eng: Engineering,
    rs,
    rs_oppo,
    allow_mixed: bool,
) -> Optional[Dict[str, object]]:
    if rs.dir == rs_oppo.dir:
        return None

    same_turnback, same_platform = _common_turnback_platform(eng, rs, rs_oppo)
    is_mixed = rs.xroad != rs_oppo.xroad
    if is_mixed and not allow_mixed:
        return None

    effective_arrival = int(rs.dep_time[-1])
    turnback_platform = _slot_turnback_platform(eng, rs)

    if is_mixed:
        if same_turnback and same_platform is not None:
            turnback_platform = same_platform
        else:
            tar_end = _mixed_target_platform(eng, rs, rs_oppo)
            if tar_end is None:
                return None
            adjusted = eng.rl.computeNewArrival(rs, rs_oppo, tar_end, eng.level)
            if adjusted is None or adjusted < 0:
                return None
            effective_arrival = int(adjusted)
            turnback_platform = tar_end

    if turnback_platform is None:
        return None

    turnback = eng.rl.turnbackList.get(turnback_platform)
    if turnback is None:
        return None

    return {
        "turnback_platform": turnback_platform,
        "effective_arrival": effective_arrival,
        "min_tb": int(turnback.min_tb_time),
        "def_tb": int(turnback.def_tb_time),
        "max_tb": int(turnback.max_tb_time),
        "same_turnback": same_turnback,
        "is_mixed": is_mixed,
    }


def _headway_reference_departure(eng: Engineering, rs) -> int:
    # Reuse the Python engineering-side dispatch alignment so mixed big/small routes
    # are compared on the same headway reference station.
    return int(eng.get_act_send_time_ac_big(rs))


def _write_csv(path: Path, rows: List[Dict[str, object]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _extract_seed_columns(
    rail_path: Path,
    setting_path: Path,
    allow_mixed: int,
    out_dir: Path,
    slots: List[Dict[str, object]],
    seed_phase: int,
) -> Tuple[List[Dict[str, object]], Dict[str, int]]:
    """Map legacy phase-connected chains back to exported phase1 slots."""
    if not slots:
        return [], {"seed_count": 0, "seed_row_count": 0, "seed_matched_route_count": 0}

    slot_groups: Dict[Tuple[int, int], List[Dict[str, object]]] = {}
    for slot in slots:
        key = (int(slot["direction"]), int(slot["route_id"]))
        slot_groups.setdefault(key, []).append(slot)
    for slot_rows in slot_groups.values():
        slot_rows.sort(key=lambda row: (int(row["nominal_departure"]), int(row["slot_id"])))

    log_path = out_dir / f"phase{seed_phase}_seed_generation.log"
    route_lists = []
    try:
        with log_path.open("w", encoding="utf-8") as log_fh:
            with redirect_stdout(log_fh), redirect_stderr(log_fh):
                eng_seed = Engineering(
                    False,
                    str(rail_path),
                    str(setting_path),
                    algorithm_type="LP",
                    solver_type="PULP",
                    obj_type=1,
                    arrange_init=False,
                    n_phase=seed_phase,
                    allow_mixed_operation=allow_mixed,
                )
                eng_seed.allow_mixed_operation = allow_mixed
                eng_seed.run_alg()
                route_lists = list(getattr(eng_seed.rl.sl, "route_lists", []))
    except Exception as exc:
        log_path.write_text(f"phase{seed_phase} seed generation failed: {exc}\n", encoding="utf-8")
        return [], {"seed_count": 0, "seed_row_count": 0, "seed_matched_route_count": 0}

    legacy_groups: Dict[Tuple[int, int], List[object]] = {}
    for rs in route_lists:
        car_info = getattr(rs, "car_info", None)
        dep_time = getattr(rs, "dep_time", None)
        if car_info is None or not dep_time:
            continue
        key = (int(getattr(rs, "dir", -1)), int(getattr(car_info, "route_num", -1)))
        if key not in slot_groups:
            continue
        legacy_groups.setdefault(key, []).append(rs)

    route_to_slot: Dict[int, Dict[str, int]] = {}
    for key, legacy_rows in legacy_groups.items():
        legacy_rows.sort(
            key=lambda rs: (
                int(rs.dep_time[0]),
                int(getattr(getattr(rs, "car_info", None), "round_num", 0)),
            )
        )
        for rs, slot_row in zip(legacy_rows, slot_groups[key]):
            car_info = getattr(rs, "car_info", None)
            route_to_slot[id(rs)] = {
                "slot_id": int(slot_row["slot_id"]),
                "target_departure": int(rs.dep_time[0]),
                "direction": int(getattr(rs, "dir", -1)),
                "route_id": int(getattr(car_info, "route_num", -1)),
                "table_num": int(getattr(car_info, "table_num", -1)),
                "seed_round_num": int(getattr(car_info, "round_num", -1)),
            }

    starts = [rs for rs in route_lists if getattr(rs, "prev_ptr", None) is None]
    seed_rows: List[Dict[str, object]] = []
    seed_keys = set()
    seed_id = 0

    for start in starts:
        matched_chain: List[Dict[str, int]] = []
        used_slots = set()
        current = start
        seen = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            mapped = route_to_slot.get(id(current))
            if mapped is not None and mapped["slot_id"] not in used_slots:
                matched_chain.append(mapped)
                used_slots.add(mapped["slot_id"])
            current = getattr(current, "next_ptr", None)

        if len(matched_chain) <= 1:
            continue
        key = tuple(item["slot_id"] for item in matched_chain)
        if key in seed_keys:
            continue
        seed_keys.add(key)
        for sequence_index, item in enumerate(matched_chain):
            seed_rows.append(
                {
                    "seed_id": seed_id,
                    "sequence_index": sequence_index,
                    "slot_id": item["slot_id"],
                    "target_departure": item["target_departure"],
                    "direction": item["direction"],
                    "route_id": item["route_id"],
                    "table_num": item["table_num"],
                    "seed_round_num": item["seed_round_num"],
                    "source": f"phase{seed_phase}_chain",
                }
            )
        seed_id += 1

    return seed_rows, {
        "seed_count": seed_id,
        "seed_row_count": len(seed_rows),
        "seed_matched_route_count": len(route_to_slot),
    }


def build_instance(
    rail_path: Path,
    setting_path: Path,
    out_dir: Path,
    allow_mixed: int,
    explicit_shift_step: Optional[int],
    seed_phase: int,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    eng = Engineering(
        False,
        str(rail_path),
        str(setting_path),
        algorithm_type="LP",
        solver_type="PULP",
        obj_type=1,
        arrange_init=False,
        n_phase=1,
        allow_mixed_operation=allow_mixed,
    )
    eng.allow_mixed_operation = allow_mixed
    eng.phase0()
    phase1_res = eng.phase1()
    trips_by_dir = eng.phase5_convert(phase1_res)

    # Depot travel times (populated by phase0 -> prepare_phase1 -> update_inout_time)
    depot_routes = _compute_depot_routes(eng, trips_by_dir)
    # Total parking capacity and usable fleet from depot XML
    depot_parking_cap = int(sum(getattr(eng.us, "depot_caps", [])))
    depot_usable_trains = int(sum(getattr(eng.us, "depot_trains", [])))

    slots: List[Dict[str, object]] = []
    options: List[Dict[str, object]] = []
    arcs: List[Dict[str, object]] = []
    arc_conflicts: List[Dict[str, object]] = []
    option_conflicts: List[Dict[str, object]] = []
    slot_missions: List[Dict[str, object]] = []
    options_by_slot: Dict[int, List[Dict[str, object]]] = {}

    slot_id = 0
    option_id = 0

    slot_trip_refs: Dict[int, object] = {}
    slot_row_by_id: Dict[int, Dict[str, object]] = {}
    slot_id_by_dir_round: Dict[Tuple[int, int], int] = {}
    direction_slot_ids: Dict[int, List[int]] = {0: [], 1: []}
    first_car_raw_targets: List[Dict[str, object]] = []

    for direction in range(2):
        first_car_target = _select_first_car_target(eng, direction, trips_by_dir[direction])
        if first_car_target is not None:
            first_car_raw_targets.append(first_car_target)
        headway_dep_times = [_headway_reference_departure(eng, rs) for rs in trips_by_dir[direction]]
        for index, rs in enumerate(trips_by_dir[direction]):
            prev_gap = headway_dep_times[index] - headway_dep_times[index - 1] if index > 0 else None
            next_gap = headway_dep_times[index + 1] - headway_dep_times[index] if index + 1 < len(headway_dep_times) else None
            target_gap_candidates = [gap for gap in [prev_gap, next_gap] if gap is not None and gap > 0]
            target_gap = int(round(sum(target_gap_candidates) / len(target_gap_candidates))) if target_gap_candidates else int(eng.Phases[0].interval)
            shift_step = _option_step(target_gap, explicit_shift_step)
            headway_nominal_departure = _headway_reference_departure(eng, rs)
            first_real_idx, first_real_platform, first_real_departure = _find_first_real_stop(eng, rs)

            first_platform = rs.stopped_platforms[0] if rs.stopped_platforms else ""
            second_platform = rs.stopped_platforms[1] if len(rs.stopped_platforms) > 1 else first_platform
            last_pre_platform = rs.stopped_platforms[-2] if len(rs.stopped_platforms) > 1 else (rs.stopped_platforms[-1] if rs.stopped_platforms else "")
            last_platform = rs.stopped_platforms[-1] if rs.stopped_platforms else ""
            turnback_platform = _slot_turnback_platform(eng, rs) or last_platform
            turnback = eng.rl.turnbackList.get(turnback_platform)
            min_tb = int(turnback.min_tb_time) if turnback else 0
            def_tb = int(turnback.def_tb_time) if turnback else 0
            max_tb = int(turnback.max_tb_time) if turnback else 0
            track_platform = _get_platform_safe(eng, first_platform)
            min_track = int(track_platform.min_track_time) if track_platform else 0
            tail_track_platform = _get_platform_safe(eng, turnback_platform)
            tail_min_track = int(tail_track_platform.min_track_time) if tail_track_platform else 0

            slot_row = {
                "slot_id": slot_id,
                "direction": direction,
                "order_in_direction": index,
                "phase_id": int(rs.phase),
                "xroad": int(rs.xroad),
                "route_id": int(rs.car_info.route_num),
                "round_num": int(rs.car_info.round_num),
                "nominal_departure": int(rs.dep_time[0]),
                "headway_nominal_departure": headway_nominal_departure,
                "nominal_arrival": int(rs.dep_time[-1]),
                "target_gap": target_gap,
                "shift_step": shift_step,
                "first_platform": first_platform,
                "first_real_platform": first_real_platform or first_platform,
                "first_real_idx": int(first_real_idx),
                "first_real_departure": int(first_real_departure if first_real_departure is not None else rs.dep_time[0]),
                "second_platform": second_platform,
                "last_pre_platform": last_pre_platform,
                "last_platform": last_platform,
                "turnback_platform": turnback_platform,
                "slot_min_tb": min_tb,
                "slot_def_tb": def_tb,
                "slot_max_tb": max_tb,
                "slot_min_track": min_track,
                "slot_tail_min_track": tail_min_track,
            }
            slots.append(slot_row)
            slot_trip_refs[slot_id] = rs
            slot_row_by_id[slot_id] = slot_row
            slot_id_by_dir_round[(direction, int(rs.car_info.round_num))] = slot_id
            direction_slot_ids[direction].append(slot_id)
            for stop_index, platform_code in enumerate(rs.stopped_platforms):
                mission_arrival = int(rs.dep_time[0] if stop_index == 0 else rs.arr_time[stop_index])
                mission_departure = int(rs.dep_time[stop_index] if stop_index < len(rs.stopped_platforms) - 1 else rs.arr_time[stop_index])
                slot_missions.append(
                    {
                        "slot_id": slot_row["slot_id"],
                        "stop_index": stop_index,
                        "platform_code": platform_code,
                        "arrival": mission_arrival,
                        "departure": mission_departure,
                        "perf_level": int(rs.performance_levels[stop_index]),
                        "clear_flag": 1 if stop_index == len(rs.stopped_platforms) - 1 else 0,
                    }
                )
            slot_id += 1

    seed_rows: List[Dict[str, object]] = []
    seed_stats = {"seed_count": 0, "seed_row_count": 0, "seed_matched_route_count": 0}
    seed_shift_by_slot: Dict[int, int] = {}
    if int(seed_phase) > 0:
        if int(seed_phase) not in {4, 5, 6}:
            raise ValueError(f"Unsupported seed_phase={seed_phase}; expected one of 0, 4, 5, 6.")
        seed_rows, seed_stats = _extract_seed_columns(
            rail_path=rail_path,
            setting_path=setting_path,
            allow_mixed=allow_mixed,
            out_dir=out_dir,
            slots=slots,
            seed_phase=int(seed_phase),
        )
        for seed_row in seed_rows:
            slot_id = int(seed_row["slot_id"])
            slot_row = slot_row_by_id.get(slot_id)
            if slot_row is None:
                continue
            seed_shift_by_slot[slot_id] = int(seed_row["target_departure"]) - int(slot_row["nominal_departure"])

    first_car_targets: List[Dict[str, object]] = []
    exact_shift_by_slot: Dict[int, int] = {}
    first_car_lower_bound_by_slot: Dict[int, int] = {}
    for raw in first_car_raw_targets:
        slot_key = (int(raw["direction"]), int(raw["round_num"]))
        if slot_key not in slot_id_by_dir_round:
            continue
        slot_id = slot_id_by_dir_round[slot_key]
        slot_row = slot_row_by_id[slot_id]
        exact_shift = int(raw["target_departure"]) - int(slot_row["first_real_departure"])
        first_car_targets.append(
            {
                "target_id": len(first_car_targets),
                "direction": int(raw["direction"]),
                "slot_id": slot_id,
                "route_id": raw["route_id"],
                "target_platform": raw["target_platform"],
                "target_departure": int(raw["target_departure"]),
                "nominal_departure": int(raw["nominal_target_departure"]),
                "required_shift": exact_shift,
            }
        )
        exact_shift_by_slot[slot_id] = exact_shift
        first_car_lower_bound_by_slot[slot_id] = int(raw["target_departure"])

    for slot_row in slots:
        slot_id = int(slot_row["slot_id"])
        rs = slot_trip_refs[slot_id]
        first_platform = str(slot_row["first_platform"])
        first_real_platform = str(slot_row["first_real_platform"])
        second_platform = str(slot_row["second_platform"])
        last_pre_platform = str(slot_row["last_pre_platform"])
        last_platform = str(slot_row["last_platform"])
        base_first_real_departure = int(slot_row["first_real_departure"])
        headway_nominal_departure = int(slot_row["headway_nominal_departure"])
        shifts = set(_default_shift_candidates())
        if slot_id in exact_shift_by_slot:
            shifts.add(int(exact_shift_by_slot[slot_id]))
        if slot_id in seed_shift_by_slot:
            shifts.add(int(seed_shift_by_slot[slot_id]))

        option_rows: List[Dict[str, object]] = []
        for shift in sorted(shifts):
            first_real_departure = int(base_first_real_departure + shift)
            if slot_id in first_car_lower_bound_by_slot and first_real_departure < first_car_lower_bound_by_slot[slot_id]:
                continue
            departure = int(rs.dep_time[0] + shift)
            arrival = int(rs.dep_time[-1] + shift)
            option_row = {
                "option_id": option_id,
                "slot_id": slot_id,
                "direction": int(slot_row["direction"]),
                "xroad": int(rs.xroad),
                "route_id": int(rs.car_info.route_num),
                "shift_seconds": int(shift),
                "departure": departure,
                "headway_departure": int(headway_nominal_departure + shift),
                "arrival": arrival,
                "first_platform": first_platform,
                "first_real_platform": first_real_platform,
                "first_real_departure": first_real_departure,
                "second_platform": second_platform,
                "last_pre_platform": last_pre_platform,
                "last_platform": last_platform,
            }
            options.append(option_row)
            option_rows.append(option_row)
            option_id += 1

        options_by_slot[slot_id] = option_rows

    headways: List[Dict[str, object]] = []
    headway_id = 0
    for direction, slot_ids in direction_slot_ids.items():
        for idx in range(len(slot_ids) - 1):
            lhs_slot = slots[slot_ids[idx]]
            rhs_slot = slots[slot_ids[idx + 1]]
            target_gap = int(rhs_slot["headway_nominal_departure"]) - int(lhs_slot["headway_nominal_departure"])
            lhs_options = options_by_slot.get(int(lhs_slot["slot_id"]), [])
            rhs_options = options_by_slot.get(int(rhs_slot["slot_id"]), [])
            if lhs_options and rhs_options:
                lhs_headway_options = _headway_window_options(lhs_options)
                rhs_headway_options = _headway_window_options(rhs_options)
                actual_gaps = [
                    int(rhs["headway_departure"]) - int(lhs["headway_departure"])
                    for lhs in lhs_headway_options
                    for rhs in rhs_headway_options
                ]
                min_headway, max_headway = _bounded_headway_window(target_gap, actual_gaps)
            else:
                min_headway = target_gap
                max_headway = target_gap
            headways.append(
                {
                    "headway_id": headway_id,
                    "direction": direction,
                    "lhs_slot_id": int(lhs_slot["slot_id"]),
                    "rhs_slot_id": int(rhs_slot["slot_id"]),
                    "target_gap": target_gap,
                    "min_headway": min_headway,
                    "max_headway": max_headway,
                }
            )
            headway_id += 1

    peak_rows: List[Dict[str, object]] = []
    for peak_id, peak in enumerate(getattr(eng.us, "peaks", [])):
        peak_rows.append(
            {
                "peak_id": peak_id,
                "start_time": int(peak.start_time),
                "end_time": int(peak.end_time),
                "train_num": int(peak.train_num),
                "train_num1": int(peak.train_num1),
                "train_num2": int(peak.train_num2),
                "op_rate1": int(peak.op_rate1),
                "op_rate2": int(peak.op_rate2),
            }
        )

    speed_level_count = max(int(len(getattr(eng.rl, "speedLevels_name", {}))), 0)
    travel_time_map: Dict[Tuple[str, str], List[int]] = {}
    for travel_key, travel_time in getattr(eng.rl, "travel_time_map", {}).items():
        splited = str(travel_key).split("_")
        if len(splited) < 3:
            continue
        start_platform = splited[0]
        end_platform = splited[1]
        level_idx = int(splited[2]) - 1
        key = (start_platform, end_platform)
        if key not in travel_time_map:
            travel_time_map[key] = [0] * speed_level_count
        if 0 <= level_idx < speed_level_count:
            travel_time_map[key][level_idx] = int(travel_time)

    travel_time_rows: List[Dict[str, object]] = []
    for start_platform, end_platform in sorted(travel_time_map.keys()):
        row: Dict[str, object] = {
            "start_platform": start_platform,
            "end_platform": end_platform,
        }
        for level_idx, travel_time in enumerate(travel_time_map[(start_platform, end_platform)], start=1):
            row[f"level_{level_idx}"] = travel_time
        travel_time_rows.append(row)

    seen_option_conflicts = set()
    for from_slot_id, from_rs in slot_trip_refs.items():
        from_slot = slot_row_by_id[from_slot_id]
        from_platform = str(from_slot["turnback_platform"])
        min_interval = int(from_slot["slot_tail_min_track"])
        if not from_platform or min_interval <= 0:
            continue
        for to_slot_id, to_rs in slot_trip_refs.items():
            if from_slot_id == to_slot_id:
                continue
            if int(from_rs.dir) == int(to_rs.dir):
                continue
            to_slot = slot_row_by_id[to_slot_id]
            if from_platform != str(to_slot["first_real_platform"]):
                continue
            for from_option in options_by_slot[from_slot_id]:
                for to_option in options_by_slot[to_slot_id]:
                    gap = abs(int(to_option["departure"]) - int(from_option["arrival"]))
                    if gap >= min_interval:
                        continue
                    key = tuple(sorted((int(from_option["option_id"]), int(to_option["option_id"]))))
                    if key in seen_option_conflicts:
                        continue
                    seen_option_conflicts.add(key)
                    option_conflicts.append(
                        {
                            "conflict_id": len(option_conflicts),
                            "option_a": key[0],
                            "option_b": key[1],
                            "platform": from_platform,
                            "min_interval": min_interval,
                            "kind": "arrdep",
                        }
                    )

    arc_id = 0
    event_id = 0
    event_rows: List[Dict[str, object]] = []
    for from_slot_id, from_rs in slot_trip_refs.items():
        for to_slot_id, to_rs in slot_trip_refs.items():
            if from_slot_id == to_slot_id:
                continue
            if from_rs.dir == to_rs.dir:
                continue
            meta = _turnback_meta(eng, from_rs, to_rs, allow_mixed=allow_mixed == 1)
            if meta is None:
                continue

            for from_option in options_by_slot[from_slot_id]:
                effective_arrival = int(meta["effective_arrival"]) + int(from_option["shift_seconds"])
                for to_option in options_by_slot[to_slot_id]:
                    if int(to_option["departure"]) <= int(from_option["arrival"]):
                        continue
                    wait_time = int(to_option["departure"]) - effective_arrival
                    if wait_time < int(meta["min_tb"]) - SOFT_TURNBACK_EXTENSION_SEC:
                        continue
                    if wait_time > int(meta["max_tb"]) + SOFT_TURNBACK_EXTENSION_SEC:
                        continue

                    arc_cost = _soft_turnback_arc_cost(
                        wait_time=wait_time,
                        min_tb=int(meta["min_tb"]),
                        def_tb=int(meta["def_tb"]),
                        max_tb=int(meta["max_tb"]),
                        is_mixed=bool(meta["is_mixed"]),
                    )

                    current_event_id = -1
                    occupy_start = ""
                    occupy_end = ""
                    if bool(meta["same_turnback"]):
                        current_event_id = event_id
                        occupy_start = effective_arrival
                        occupy_end = int(to_option["departure"])
                        event_rows.append(
                            {
                                "event_id": current_event_id,
                                "arc_id": arc_id,
                                "from_slot_id": int(from_slot_id),
                                "to_slot_id": int(to_slot_id),
                                "platform": str(meta["turnback_platform"]),
                                "occupy_start": int(occupy_start),
                                "occupy_end": int(occupy_end),
                            }
                        )
                        event_id += 1

                    arc_row = {
                        "arc_id": arc_id,
                        "from_option_id": int(from_option["option_id"]),
                        "to_option_id": int(to_option["option_id"]),
                        "from_slot_id": int(from_slot_id),
                        "to_slot_id": int(to_slot_id),
                        "effective_arrival": int(effective_arrival),
                        "wait_time": wait_time,
                        "turnback_platform": str(meta["turnback_platform"]),
                        "min_tb": int(meta["min_tb"]),
                        "def_tb": int(meta["def_tb"]),
                        "max_tb": int(meta["max_tb"]),
                        "is_mixed": int(bool(meta["is_mixed"])),
                        "same_turnback": int(bool(meta["same_turnback"])),
                        "event_id": current_event_id,
                        "arc_cost": arc_cost,
                    }
                    arcs.append(arc_row)
                    arc_id += 1

    # Group events by platform for efficient overlap detection.
    _events_by_platform: Dict[str, List[Dict[str, object]]] = {}
    for ev in event_rows:
        _events_by_platform.setdefault(str(ev["platform"]), []).append(ev)

    for _platform, _platform_events in _events_by_platform.items():
        _platform_events.sort(key=lambda e: int(e["occupy_start"]))
        for idx in range(len(_platform_events)):
            lhs = _platform_events[idx]
            for jdx in range(idx + 1, len(_platform_events)):
                rhs = _platform_events[jdx]
                # Events from arcs that share a from/to slot are already
                # mutually exclusive via the cover constraint; skip them.
                if (
                    lhs.get("from_slot_id") == rhs.get("from_slot_id")
                    or lhs.get("to_slot_id") == rhs.get("to_slot_id")
                    or lhs.get("from_slot_id") == rhs.get("to_slot_id")
                    or lhs.get("to_slot_id") == rhs.get("from_slot_id")
                ):
                    continue
                # Sorted by occupy_start, so if rhs starts after lhs ends
                # no further overlaps are possible in this inner loop.
                if int(rhs["occupy_start"]) >= int(lhs["occupy_end"]):
                    break
                arc_conflicts.append(
                    {
                        "conflict_id": len(arc_conflicts),
                        "event_a": int(lhs["event_id"]),
                        "event_b": int(rhs["event_id"]),
                        "platform": _platform,
                    }
                )

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        out_dir / "slots.csv",
        slots,
        [
            "slot_id",
            "direction",
            "order_in_direction",
            "phase_id",
            "xroad",
            "route_id",
            "round_num",
            "nominal_departure",
            "headway_nominal_departure",
            "nominal_arrival",
            "target_gap",
            "shift_step",
            "first_platform",
            "first_real_platform",
            "first_real_idx",
            "first_real_departure",
            "second_platform",
            "last_pre_platform",
            "last_platform",
            "turnback_platform",
            "slot_min_tb",
            "slot_def_tb",
            "slot_max_tb",
            "slot_min_track",
            "slot_tail_min_track",
        ],
    )
    _write_csv(
        out_dir / "options.csv",
        options,
        [
            "option_id",
            "slot_id",
            "direction",
            "xroad",
            "route_id",
            "shift_seconds",
            "departure",
            "headway_departure",
            "arrival",
            "first_platform",
            "first_real_platform",
            "first_real_departure",
            "second_platform",
            "last_pre_platform",
            "last_platform",
        ],
    )
    _write_csv(
        out_dir / "headways.csv",
        headways,
        [
            "headway_id",
            "direction",
            "lhs_slot_id",
            "rhs_slot_id",
            "target_gap",
            "min_headway",
            "max_headway",
        ],
    )
    _write_csv(
        out_dir / "peaks.csv",
        peak_rows,
        [
            "peak_id",
            "start_time",
            "end_time",
            "train_num",
            "train_num1",
            "train_num2",
            "op_rate1",
            "op_rate2",
        ],
    )
    _write_csv(
        out_dir / "first_car_targets.csv",
        first_car_targets,
        [
            "target_id",
            "direction",
            "slot_id",
            "route_id",
            "target_platform",
            "target_departure",
            "nominal_departure",
            "required_shift",
        ],
    )
    _write_csv(
        out_dir / "option_conflicts.csv",
        option_conflicts,
        ["conflict_id", "option_a", "option_b", "platform", "min_interval", "kind"],
    )
    _write_csv(
        out_dir / "arcs.csv",
        arcs,
        [
            "arc_id",
            "from_option_id",
            "to_option_id",
            "from_slot_id",
            "to_slot_id",
            "effective_arrival",
            "wait_time",
            "turnback_platform",
            "min_tb",
            "def_tb",
            "max_tb",
            "is_mixed",
            "same_turnback",
            "event_id",
            "arc_cost",
        ],
    )
    _write_csv(
        out_dir / "arc_events.csv",
        event_rows,
        ["event_id", "arc_id", "from_slot_id", "to_slot_id", "platform", "occupy_start", "occupy_end"],
    )
    _write_csv(
        out_dir / "arc_conflicts.csv",
        arc_conflicts,
        ["conflict_id", "event_a", "event_b", "platform"],
    )
    _write_csv(
        out_dir / "slot_missions.csv",
        slot_missions,
        ["slot_id", "stop_index", "platform_code", "arrival", "departure", "perf_level", "clear_flag"],
    )
    _write_csv(
        out_dir / "travel_times.csv",
        travel_time_rows,
        ["start_platform", "end_platform"] + [f"level_{idx}" for idx in range(1, speed_level_count + 1)],
    )
    if depot_routes:
        _write_csv(
            out_dir / "depot_routes.csv",
            depot_routes,
            ["xroad", "direction", "depot_in_time", "depot_out_time", "depot_gate_gap"],
        )

    if seed_rows:
        _write_csv(
            out_dir / "seed_columns.csv",
            seed_rows,
            [
                "seed_id",
                "sequence_index",
                "slot_id",
                "target_departure",
                "direction",
                "route_id",
                "table_num",
                "seed_round_num",
                "source",
            ],
        )

    manifest_lines = [
        f"rail_path={rail_path}",
        f"setting_path={setting_path}",
        f"allow_mixed={allow_mixed}",
        f"seed_phase={int(seed_phase)}",
        f"seed_enabled={1 if int(seed_phase) > 0 else 0}",
        f"slot_count={len(slots)}",
        f"option_count={len(options)}",
        f"arc_count={len(arcs)}",
        f"headway_count={len(headways)}",
        f"arc_conflict_count={len(arc_conflicts)}",
        f"option_conflict_count={len(option_conflicts)}",
        f"peak_count={len(peak_rows)}",
        f"slot_mission_count={len(slot_missions)}",
        f"travel_time_count={len(travel_time_rows)}",
        f"seed_column_count={seed_stats['seed_count']}",
        f"seed_column_row_count={seed_stats['seed_row_count']}",
        f"seed_matched_route_count={seed_stats['seed_matched_route_count']}",
        f"speed_level_count={speed_level_count}",
        f"vehicle_cost=1000",
        f"max_vehicle_count={max((int(p['train_num']) for p in peak_rows), default=0)}",
        f"depot_usable_trains={depot_usable_trains}",
        f"depot_parking_cap={depot_parking_cap}",
        f"first_car={int(getattr(eng.us, 'first_car', 0))}",
        f"peak_vehicle_penalty=1000000",
        f"vehicle_cap_penalty=1000000",
        f"headway_target_penalty=100",
        f"cover_penalty=100000",
        f"cover_extra_penalty=400000",
        f"headway_penalty=100000",
        f"conflict_penalty=100000",
        f"cbc_path={pulp.PULP_CBC_CMD().path}",
    ]
    (out_dir / "manifest.txt").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    report_lines = [
        "# CG Instance Export",
        "",
        f"- Rail XML: `{rail_path}`",
        f"- Setting XML: `{setting_path}`",
        f"- Mixed operation: `{allow_mixed}`",
        f"- Peak windows: `{len(peak_rows)}`",
        f"- Max vehicle count: `{max((int(p['train_num']) for p in peak_rows), default=0)}`",
        f"- First car target: `{int(getattr(eng.us, 'first_car', 0))}`",
        f"- Slots: `{len(slots)}`",
        f"- Options: `{len(options)}`",
        f"- Arcs: `{len(arcs)}`",
        f"- Seed phase: `{int(seed_phase)}`",
        f"- Legacy seed columns: `{seed_stats['seed_count']}`",
        f"- Legacy seed rows: `{seed_stats['seed_row_count']}`",
        f"- Seed matched trips: `{seed_stats['seed_matched_route_count']}`",
        f"- Slot mission rows: `{len(slot_missions)}`",
        f"- Travel-time rows: `{len(travel_time_rows)}`",
        f"- Arrival/departure option conflicts: `{len(option_conflicts)}`",
        f"- Turnback conflict pairs (same-turnback overlaps): `{len(arc_conflicts)}`",
        f"- Turnback events: `{len(event_rows)}`",
        "",
    ]

    # --- Xroad (big/small route) pattern analysis per direction ----------
    if peak_rows:
        first_peak = peak_rows[0]
        op1 = int(first_peak.get("op_rate1", 1))
        op2 = int(first_peak.get("op_rate2", 0))
        period = op1 + op2
        for _dir in [0, 1]:
            dir_slots = [s for s in slots if int(s["direction"]) == _dir]
            dir_slots.sort(key=lambda s: int(s["nominal_departure"]))
            xroads = [int(s["xroad"]) for s in dir_slots]
            pattern_str = "".join(str(x) for x in xroads)
            report_lines.append(f"### Direction {_dir} xroad pattern")
            report_lines.append("")
            report_lines.append(f"- Total slots: `{len(dir_slots)}`")
            report_lines.append(f"- Big-route (xroad=0): `{xroads.count(0)}`")
            report_lines.append(f"- Small-route (xroad=1): `{xroads.count(1)}`")
            report_lines.append(f"- Pattern (first 40): `{pattern_str[:40]}`")
            if period > 1 and op2 > 0:
                # Ideal cyclic pattern: op1 zeros then op2 ones, repeating.
                ideal_cycle = [0] * op1 + [1] * op2
                matches = sum(
                    1 for i, x in enumerate(xroads) if x == ideal_cycle[i % period]
                )
                rate = matches / len(xroads) if xroads else 0
                report_lines.append(
                    f"- Ideal cycle `{''.join(str(c) for c in ideal_cycle)}` match: `{rate:.1%}`"
                )
                report_lines.append(
                    f"- Note: for ratio {op1}:{op2}, the ideal sequence is "
                    f"{''.join(str(c) for c in ideal_cycle)} repeating (cyclic), "
                    "not all-big then all-small.  Transition regions at peak "
                    "boundaries may deviate."
                )
            report_lines.append("")

    report_lines.extend([
        "## Notes",
        "",
        "- Slots are built from current Python `phase0 + phase1` results.",
        "- Each slot exports minute-level departure options from `-3` to `+3` minutes, plus any exact first-car / legacy-seed shifts.",
        "- First-car target is the fleet-completing train (position = peak train_num per direction).",
        "- The first-car candidate slot exports an exact-shift option and filters out early options, so non-early first-car is hard.",
        "- Headway uses Python-aligned dispatch time, and the hard headway envelope is recomputed from exported options but capped within nominal `+/-10` minutes.",
        "- Peak vehicle limits come directly from XML `PeaksParameter` and are enforced in the master by duty peak-incidence rows.",
        "- `slot_missions.csv` keeps the per-slot mission rows needed for Python-compatible result export.",
        "- `travel_times.csv` keeps section running times needed for the `运行时间` sheet.",
        "- Arrival/departure conflicts are exported as hard option-pair conflicts on the same terminal platform.",
        "- Turnback arcs now allow bounded min/max-turnback violations and push them into arc cost as a convex penalty.",
        "- Mixed-route turnback arcs reuse existing Python `computeNewArrival` and `judgeSameTurnback` semantics.",
        "- Turnback resource conflicts are now exported for ALL same-turnback occupancy overlaps (not only mixed-route).",
        "- Events from arcs sharing a from/to slot are skipped (cover constraint already makes them exclusive).",
        "- `seed_columns.csv` maps legacy connected chains back onto the exported phase1 slots and is used to strengthen the initial restricted master.",
        "- Default seed source is legacy `phase5`, because it aligns with the exported `phase1` slot universe better than `phase6` on cs4.",
        "",
    ])
    (out_dir / "instance_report.md").write_text("\n".join(report_lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a truncated-CG instance from the current Python scheduler.")
    parser.add_argument("--rail", required=True, help="Schedule XML path.")
    parser.add_argument("--setting", required=True, help="User setting XML path.")
    parser.add_argument("--out", required=True, help="Output directory for the exported instance.")
    parser.add_argument("--mixed", type=int, default=1, help="Whether mixed operation arcs are allowed.")
    parser.add_argument("--shift-step", type=int, default=None, help="Explicit departure shift step in seconds.")
    parser.add_argument("--seed-phase", type=int, default=5, help="Legacy phase used for seed columns: 0 disables, supported values are 4, 5, 6.")
    parser.add_argument("--seed-from-phase6", type=int, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    seed_phase = int(args.seed_phase)
    if args.seed_from_phase6 is not None:
        seed_phase = 6 if int(args.seed_from_phase6) == 1 else 0

    build_instance(
        Path(args.rail).resolve(),
        Path(args.setting).resolve(),
        Path(args.out).resolve(),
        allow_mixed=int(args.mixed),
        explicit_shift_step=args.shift_step,
        seed_phase=seed_phase,
    )


if __name__ == "__main__":
    main()
