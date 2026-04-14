#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cmath>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <queue>
#ifdef _WIN32
#include <process.h>
#endif
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace fs = std::filesystem;

namespace {

fs::path resolve_tool_script_path(const std::string& script_name);
bool python_has_gurobipy(const std::string& python_exe, bool debug);
bool python_has_coinmp(const std::string& python_exe, bool debug);

constexpr double kEps = 1e-8;

struct Config {
    std::string rail_path;
    std::string setting_path;
    std::string output_dir = "data/output_data/cpp_cg_results";
    std::string instance_dir;
    std::string python_exe = "python";
    std::string cbc_path;
    std::string gurobi_path;
    std::string baseline_xlsx;
    std::string algorithm = "CG_CPP";
    std::string solver = "AUTO";
    int mixed_operation = 1;
    int max_iterations = 200;
    int min_iterations = 40;
    int pricing_batch_size = 64;
    int min_pricing_batch_size = 8;
    int column_prune_trigger = 5000;
    int column_min_age = 12;
    int column_inactive_iterations = 8;
    int column_recent_protection = 6;
    int master_time_limit_sec = 600;
    int final_mip_time_limit_sec = 600;
    int tcg_incumbent_time_limit_sec = 60;
    int tcg_fix_columns = 5;
    double mip_gap = 0.005;
    double tcg_fix_min_value = 0.8;
    double tcg_fix_force_value = 0.9;
    int shift_step = -1;
    int seed_phase = 5;
    int n_phase = 6;
    int obj_type = 1;
    double dual_stabilization_alpha = 0.5;
    double dual_box_abs = 100.0;
    double dual_box_rel = 0.25;
    double basis_activity_epsilon = 1e-6;
    double tabu_option_penalty = 2.0;
    double tabu_arc_penalty = 4.0;
    double tabu_event_penalty = 2.0;
    bool arrange_init = false;
    bool debug = false;
    bool reuse_instance = false;
    bool export_only = false;
    bool enable_orthodox_tcg = true;
    bool enable_persistent_gurobi_master = true;
    bool enable_dual_stabilization = true;
    bool enable_dual_box = false;
    bool enable_adaptive_pricing_batch = true;
    bool enable_column_pool_pruning = true;
    bool enable_tabu_pricing = true;
    bool use_bidirectional_pricing = true;
};

struct Slot {
    int id = -1;
    int direction = 0;
    int order_in_direction = 0;
    int phase_id = 0;
    int xroad = 0;
    int route_id = 0;
    int round_num = 0;
    int nominal_departure = 0;
    int headway_nominal_departure = 0;
    int nominal_arrival = 0;
    int target_gap = 0;
    int shift_step = 0;
    int first_real_idx = -1;
    int first_real_departure = 0;
    int slot_min_track = 0;
    int slot_tail_min_track = 0;
    std::string first_platform;
    std::string first_real_platform;
    std::string turnback_platform;
};

struct Option {
    int id = -1;
    int slot_id = -1;
    int direction = 0;
    int xroad = 0;
    int route_id = 0;
    int shift_seconds = 0;
    int departure = 0;
    int headway_departure = 0;
    int arrival = 0;
    int first_real_departure = 0;
    int peak_id = -1;
    std::uint64_t peak_mask = 0;
};

struct Headway {
    int id = -1;
    int direction = 0;
    int lhs_slot_id = -1;
    int rhs_slot_id = -1;
    int target_gap = 0;
    int min_headway = 0;
    int max_headway = 0;
};

struct PeakWindow {
    int id = -1;
    int start_time = 0;
    int end_time = 0;
    int train_num = 0;
    int train_num1 = 0;
    int train_num2 = 0;
    int op_rate1 = 0;
    int op_rate2 = 0;
    int bit_index = -1;
    std::uint64_t bit_mask = 0;
};

struct FirstCarTarget {
    int id = -1;
    int direction = 0;
    int slot_id = -1;
    int target_departure = 0;
    std::string route_id;
    std::string target_platform;
    std::vector<int> valid_option_ids;
    std::unordered_set<int> valid_option_set;
};

struct Arc {
    int id = -1;
    int from_option_id = -1;
    int to_option_id = -1;
    int from_slot_id = -1;
    int to_slot_id = -1;
    int effective_arrival = 0;
    int wait_time = 0;
    int min_tb = 0;
    int def_tb = 0;
    int max_tb = 0;
    int event_id = -1;
    bool is_mixed = false;
    bool same_turnback = false;
    double arc_cost = 0.0;
    std::string turnback_platform;
};

struct OptionConflict {
    int id = -1;
    int option_a = -1;
    int option_b = -1;
    int min_interval = 0;
    std::string platform;
    std::string kind;
};

struct ArcConflict {
    int id = -1;
    int event_a = -1;
    int event_b = -1;
    std::string platform;
};

// Depot travel time for a given xroad + direction combination.
// depot_out_time: seconds from depot to first mainline platform (before first trip).
// depot_in_time:  seconds from last mainline platform back to depot (after last trip).
// depot_gate_gap: minimum spacing between consecutive vehicles using the same
//                 depot throat (single-track approach/exit segment).
//                 Default 0 means no gate constraint. Typical value: 120-300 s.
struct DepotRoute {
    int xroad = 0;
    int direction = 0;
    int depot_out_time = 0;
    int depot_in_time = 0;
    int depot_gate_gap = 0;   // 0 = disable gate conflicts for this route
    int depot_in_route_id = -1;
    int depot_out_route_id = -1;
    std::string depot_in_route_type;
    std::string depot_out_route_type;
    std::string depot_in_route_ids;
    std::string depot_out_route_ids;
};

struct DepotEndpointArc {
    int id = -1;
    int option_id = -1;
    int xroad = 0;
    int direction = 0;
    int route_id = -1;
    std::string route_type;
    bool is_source = false;
    int travel_time = 0;
    double arc_cost = 0.0;
};

struct SeedColumnStep {
    int slot_id = -1;
    int target_departure = 0;
};

struct Column {
    int id = -1;
    double cost = 0.0;
    std::vector<int> option_ids;
    std::vector<int> arc_ids;
    std::vector<int> event_ids;
    std::unordered_map<int, int> slot_to_option;
    std::unordered_set<int> option_set;
    std::unordered_set<int> event_set;
    std::uint64_t peak_mask = 0;
    std::uint64_t peak_mask_xr0 = 0;
    std::uint64_t peak_mask_xr1 = 0;
    int start_departure = -1;
    int end_arrival = -1;
    int start_direction = -1;
    int end_direction = -1;
    int start_xroad = -1;
    int end_xroad = -1;
    int start_route_id = -1;
    int end_route_id = -1;
    int depot_source_arc_id = -1;
    int depot_sink_arc_id = -1;
    int depot_out_route_id = -1;
    int depot_in_route_id = -1;
    // Depot positioning times included in this column
    int depot_out_time = 0;   // time before first option (depot → first platform)
    int depot_in_time = 0;    // time after last option (last platform → depot)
    // Wall-clock times covering the full vehicle day (including depot legs)
    int day_start = -1;       // first_option.departure - depot_out_time
    int day_end = -1;         // last_option.arrival + depot_in_time
    int birth_iteration = 0;
    int inactive_iterations = 0;
    int last_active_iteration = 0;
    bool is_legacy_seed = false;
    std::unordered_set<long long> direct_arc_pairs;
    std::string key;
};

struct MasterSolveResult {
    bool ok = false;
    std::string status;
    double objective = 0.0;
    std::unordered_map<std::string, double> row_duals;
    std::unordered_map<std::string, double> primal_values;
    std::string requested_solver;
    std::string actual_solver;
    bool fallback_used = false;
    std::string fallback_reason;
};

struct SparseRowCoeff {
    std::string row_name;
    double coeff = 0.0;
};

struct LinearRowTerm {
    std::string var_name;
    double coeff = 0.0;
};

struct DynamicRowPayload {
    std::string row_name;
    std::string sense;
    double rhs = 0.0;
    std::vector<LinearRowTerm> terms;
};

struct StaticRowPayload {
    std::string row_name;
    std::string sense;
    double rhs = 0.0;
};

struct ModelVariablePayload {
    std::string var_name;
    double obj = 0.0;
    double lb = 0.0;
    std::optional<double> ub;
    char vtype = 'C';
    std::vector<SparseRowCoeff> row_coeffs;
};

struct ActiveConflictRows {
    std::vector<int> option_conflict_ids;
    std::vector<int> arc_conflict_ids;
};

struct Instance;
struct DepotGateStats;

std::vector<DynamicRowPayload> build_incremental_depot_gate_rows(
    const Instance& instance,
    const std::vector<Column>& columns,
    std::size_t start_index,
    DepotGateStats* stats = nullptr
);

MasterSolveResult solve_master_with_coinmp(
    const Instance& instance,
    const std::vector<Column>& columns,
    bool integer_master,
    const std::unordered_set<int>& fixed_column_ids,
    const fs::path& work_dir,
    const std::string& python_exe,
    int master_time_limit_sec,
    double mip_gap,
    const std::string& tag,
    bool debug
);

ActiveConflictRows collect_active_conflict_rows(const Instance& instance, const std::vector<Column>& columns);

struct IterationLog {
    int iteration = 0;
    int tcg_round = 0;
    double master_objective = 0.0;
    double best_reduced_cost = 0.0;
    int active_columns = 0;
    int added_columns = 0;
    int fixed_columns_total = 0;
    int fixed_columns_added = 0;
    int pricing_batch_size_used = 0;
    int pruned_columns = 0;
    int depot_gate_rows = 0;
    long long depot_gate_pairwise_conflicts = 0;
    int pricing_option_nodes = 0;
    int pricing_arc_count = 0;
    int pricing_label_states = 0;
    int pricing_label_candidates = 0;
    int pricing_bidirectional_candidates = 0;
    double master_solve_sec = 0.0;
    double pricing_sec = 0.0;
    std::string requested_solver;
    std::string actual_solver;
    bool fallback_used = false;
    bool raw_dual_fallback_used = false;
    bool incumbent_available = false;
    double best_integer_objective = 0.0;
};

struct PricingDiagnostics {
    int option_node_count = 0;
    int arc_count = 0;
    int depot_source_arc_count = 0;
    int depot_sink_arc_count = 0;
    int heuristic_candidate_count = 0;
    int label_state_count = 0;
    int label_candidate_count = 0;
    int bidirectional_candidate_count = 0;
};

struct PricingResult {
    std::vector<Column> columns;
    PricingDiagnostics diagnostics;
};

struct ColumnPruneStats {
    int pruned_columns = 0;
    int kept_active = 0;
    int kept_recent = 0;
    int kept_legacy_seed = 0;
    int pool_size_after = 0;
};

struct DepotGateStats {
    int clique_row_count = 0;
    long long pairwise_conflict_count = 0;
};

struct RunTiming {
    double master_sec = 0.0;
    double pricing_sec = 0.0;
    double other_sec = 0.0;
    double total_sec = 0.0;
    double tcg_incumbent_sec = 0.0;
    double final_lp_sec = 0.0;
    double final_mip_sec = 0.0;
};

struct BasisNeighborhood {
    std::vector<const Column*> active_columns;
    std::unordered_map<int, double> option_activity;
    std::unordered_map<int, double> arc_activity;
    std::unordered_map<int, double> event_activity;
};

struct Instance {
    std::vector<Slot> slots;
    std::vector<Option> options;
    std::vector<PeakWindow> peaks;
    std::vector<FirstCarTarget> first_car_targets;
    std::vector<Headway> headways;
    std::vector<Arc> arcs;
    std::vector<OptionConflict> option_conflicts;
    std::vector<ArcConflict> conflicts;
    std::vector<DepotRoute> depot_routes;
    std::vector<DepotEndpointArc> depot_source_arcs;
    std::vector<DepotEndpointArc> depot_sink_arcs;
    std::vector<std::vector<SeedColumnStep>> seed_column_steps;
    int seed_phase = 0;

    // map (xroad*2 + direction) -> DepotRoute
    std::unordered_map<int, DepotRoute> depot_route_by_key;

    std::unordered_map<int, Slot> slot_by_id;
    std::unordered_map<int, Option> option_by_id;
    std::unordered_map<int, PeakWindow> peak_by_id;
    std::unordered_map<int, FirstCarTarget> first_car_target_by_id;
    std::unordered_map<int, Arc> arc_by_id;
    std::unordered_map<int, Headway> headway_by_id;
    std::unordered_map<int, OptionConflict> option_conflict_by_id;
    std::unordered_map<int, ArcConflict> conflict_by_id;

    std::unordered_map<int, std::vector<int>> options_by_slot;
    std::unordered_map<int, std::vector<int>> outgoing_arcs_by_option;
    std::unordered_map<int, std::vector<int>> headways_by_slot;
    std::unordered_map<int, std::vector<int>> option_conflicts_by_option;
    std::unordered_map<int, std::vector<int>> conflict_rows_by_event;
    std::unordered_map<int, DepotEndpointArc> depot_source_arc_by_option;
    std::unordered_map<int, DepotEndpointArc> depot_sink_arc_by_option;
    std::unordered_map<long long, int> arc_lookup;

    int vehicle_cost = 1000;
    int peak_vehicle_penalty = 1000000;
    int vehicle_cap_penalty = 1000000;
    int max_vehicle_count = 0;
    int depot_usable_trains = 0;   // total usable trains from depot XML (0 = not set)
    int depot_parking_cap = 0;     // total parking capacity at all depots
    int first_car = 0;
    int headway_target_penalty = 100;
    int cover_penalty = 100000;
    int cover_extra_penalty = 400000;
    int headway_penalty = 100000;
    int conflict_penalty = 100000;
    std::string cbc_path;
};

std::string quote(const std::string& value) {
    return "\"" + value + "\"";
}

std::string json_escape(const std::string& value) {
    std::ostringstream oss;
    for (const char ch : value) {
        switch (ch) {
            case '\\':
                oss << "\\\\";
                break;
            case '"':
                oss << "\\\"";
                break;
            case '\n':
                oss << "\\n";
                break;
            case '\r':
                oss << "\\r";
                break;
            case '\t':
                oss << "\\t";
                break;
            default:
                oss << ch;
                break;
        }
    }
    return oss.str();
}

long long pair_key(int lhs, int rhs) {
    return (static_cast<long long>(lhs) << 32) ^ static_cast<unsigned int>(rhs);
}

std::string trim(const std::string& value) {
    std::size_t start = 0;
    while (start < value.size() && std::isspace(static_cast<unsigned char>(value[start])) != 0) {
        ++start;
    }
    std::size_t end = value.size();
    while (end > start && std::isspace(static_cast<unsigned char>(value[end - 1])) != 0) {
        --end;
    }
    return value.substr(start, end - start);
}

bool starts_with(const std::string& value, const std::string& prefix) {
    return value.rfind(prefix, 0) == 0;
}

std::string lower_copy(std::string value) {
    for (char& ch : value) {
        ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
    }
    return value;
}

std::string upper_copy(std::string value) {
    for (char& ch : value) {
        ch = static_cast<char>(std::toupper(static_cast<unsigned char>(ch)));
    }
    return value;
}

std::string format_coeff(double coeff) {
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(6) << coeff;
    return oss.str();
}

std::string format_time(int value) {
    const int safe = std::max(0, value);
    const int hours = safe / 3600;
    const int minutes = (safe % 3600) / 60;
    const int seconds = safe % 60;
    std::ostringstream oss;
    oss << std::setfill('0') << std::setw(2) << hours
        << ":" << std::setw(2) << minutes
        << ":" << std::setw(2) << seconds;
    return oss.str();
}

std::vector<std::string> split_csv_line(const std::string& line) {
    std::vector<std::string> parts;
    std::string current;
    bool in_quotes = false;
    for (char ch : line) {
        if (ch == '"') {
            in_quotes = !in_quotes;
            continue;
        }
        if (ch == ',' && !in_quotes) {
            parts.push_back(current);
            current.clear();
        } else {
            current.push_back(ch);
        }
    }
    parts.push_back(current);
    return parts;
}

std::unordered_map<std::string, std::string> load_manifest(const fs::path& manifest_path) {
    std::unordered_map<std::string, std::string> values;
    std::ifstream in(manifest_path);
    std::string line;
    while (std::getline(in, line)) {
        line = trim(line);
        if (line.empty()) {
            continue;
        }
        const auto pos = line.find('=');
        if (pos == std::string::npos) {
            continue;
        }
        values[line.substr(0, pos)] = line.substr(pos + 1);
    }
    return values;
}

std::vector<std::unordered_map<std::string, std::string>> load_csv(const fs::path& csv_path) {
    std::vector<std::unordered_map<std::string, std::string>> rows;
    std::ifstream in(csv_path);
    std::string header_line;
    if (!std::getline(in, header_line)) {
        return rows;
    }
    const auto headers = split_csv_line(header_line);
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty()) {
            continue;
        }
        const auto cols = split_csv_line(line);
        std::unordered_map<std::string, std::string> row;
        for (std::size_t i = 0; i < headers.size() && i < cols.size(); ++i) {
            row[headers[i]] = cols[i];
        }
        rows.push_back(std::move(row));
    }
    return rows;
}

int get_int(const std::unordered_map<std::string, std::string>& row, const std::string& key, int fallback = 0) {
    const auto it = row.find(key);
    if (it == row.end() || it->second.empty()) {
        return fallback;
    }
    return std::stoi(it->second);
}

double get_double(const std::unordered_map<std::string, std::string>& row, const std::string& key, double fallback = 0.0) {
    const auto it = row.find(key);
    if (it == row.end() || it->second.empty()) {
        return fallback;
    }
    return std::stod(it->second);
}

std::string get_str(const std::unordered_map<std::string, std::string>& row, const std::string& key, const std::string& fallback = "") {
    const auto it = row.find(key);
    if (it == row.end()) {
        return fallback;
    }
    return it->second;
}

void build_depot_endpoint_arcs(Instance& instance) {
    instance.depot_source_arcs.clear();
    instance.depot_sink_arcs.clear();
    instance.depot_source_arc_by_option.clear();
    instance.depot_sink_arc_by_option.clear();

    int next_source_id = 0;
    int next_sink_id = 0;
    for (const auto& option : instance.options) {
        const int key = option.xroad * 2 + option.direction;
        const auto dr_it = instance.depot_route_by_key.find(key);
        if (dr_it == instance.depot_route_by_key.end()) {
            continue;
        }
        const DepotRoute& dr = dr_it->second;

        if (dr.depot_out_time > 0 || dr.depot_out_route_id >= 0) {
            DepotEndpointArc source_arc;
            source_arc.id = next_source_id++;
            source_arc.option_id = option.id;
            source_arc.xroad = option.xroad;
            source_arc.direction = option.direction;
            source_arc.route_id = dr.depot_out_route_id;
            source_arc.route_type = dr.depot_out_route_type;
            source_arc.is_source = true;
            source_arc.travel_time = dr.depot_out_time;
            source_arc.arc_cost = static_cast<double>(dr.depot_out_time) / 600.0;
            instance.depot_source_arcs.push_back(source_arc);
            instance.depot_source_arc_by_option[option.id] = source_arc;
        }

        if (dr.depot_in_time > 0 || dr.depot_in_route_id >= 0) {
            DepotEndpointArc sink_arc;
            sink_arc.id = next_sink_id++;
            sink_arc.option_id = option.id;
            sink_arc.xroad = option.xroad;
            sink_arc.direction = option.direction;
            sink_arc.route_id = dr.depot_in_route_id;
            sink_arc.route_type = dr.depot_in_route_type;
            sink_arc.is_source = false;
            sink_arc.travel_time = dr.depot_in_time;
            sink_arc.arc_cost = static_cast<double>(dr.depot_in_time) / 600.0;
            instance.depot_sink_arcs.push_back(sink_arc);
            instance.depot_sink_arc_by_option[option.id] = sink_arc;
        }
    }
}

bool column_contains_direct_option_arc(const Column& column, int option_a, int option_b) {
    return column.direct_arc_pairs.count(pair_key(option_a, option_b)) != 0 ||
           column.direct_arc_pairs.count(pair_key(option_b, option_a)) != 0;
}

double option_base_cost(const Option& option) {
    const double shift_min = static_cast<double>(std::abs(option.shift_seconds)) / 60.0;
    return shift_min * shift_min;
}

bool departure_in_peak(const PeakWindow& peak, int departure) {
    if (departure < peak.start_time) {
        return false;
    }
    return departure < peak.end_time;
}

std::vector<int> peak_ids_from_mask(const Instance& instance, std::uint64_t peak_mask) {
    std::vector<int> peak_ids;
    for (const auto& peak : instance.peaks) {
        if ((peak_mask & peak.bit_mask) != 0) {
            peak_ids.push_back(peak.id);
        }
    }
    return peak_ids;
}

std::string join_ints(const std::vector<int>& values, const std::string& delim = ";") {
    std::ostringstream oss;
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (i > 0) {
            oss << delim;
        }
        oss << values[i];
    }
    return oss.str();
}

std::string row_name_cover(int slot_id) {
    return "R_cover_" + std::to_string(slot_id);
}

std::string row_name_peak_cap(int peak_id) {
    return "R_peak_cap_" + std::to_string(peak_id);
}

std::string row_name_vehicle_cap() {
    return "R_vehicle_cap";
}

std::string row_name_first_car(int target_id) {
    return "R_first_car_" + std::to_string(target_id);
}

std::string row_name_headway_lb(int headway_id) {
    return "R_headway_lb_" + std::to_string(headway_id);
}

std::string row_name_headway_ub(int headway_id) {
    return "R_headway_ub_" + std::to_string(headway_id);
}

std::string row_name_headway_target(int headway_id) {
    return "R_headway_target_" + std::to_string(headway_id);
}

std::string row_name_conflict(int conflict_id) {
    return "R_conflict_" + std::to_string(conflict_id);
}

std::string row_name_option_conflict(int conflict_id) {
    return "R_opt_conflict_" + std::to_string(conflict_id);
}

// Depot throat gate conflict row names (canonical: min_id < max_id)
std::string row_name_depot_out_gate(int col_a, int col_b) {
    const int lo = std::min(col_a, col_b), hi = std::max(col_a, col_b);
    return "R_dout_" + std::to_string(lo) + "_" + std::to_string(hi);
}
std::string row_name_depot_in_gate(int col_a, int col_b) {
    const int lo = std::min(col_a, col_b), hi = std::max(col_a, col_b);
    return "R_din_" + std::to_string(lo) + "_" + std::to_string(hi);
}
std::string row_name_depot_out_gate_clique(int resource_key, int first_col_id, int last_col_id) {
    return "R_doutc_" + std::to_string(resource_key) + "_" + std::to_string(first_col_id) + "_" + std::to_string(last_col_id);
}
std::string row_name_depot_in_gate_clique(int resource_key, int first_col_id, int last_col_id) {
    return "R_dinc_" + std::to_string(resource_key) + "_" + std::to_string(first_col_id) + "_" + std::to_string(last_col_id);
}

std::string row_name_peak_cap_xr0(int peak_id) {
    return "R_peak_xr0_" + std::to_string(peak_id);
}

std::string row_name_peak_cap_xr1(int peak_id) {
    return "R_peak_xr1_" + std::to_string(peak_id);
}

std::string var_name_column(int column_id) {
    return "X_" + std::to_string(column_id);
}

std::string var_name_slack_lb(int headway_id) {
    return "S_hlb_" + std::to_string(headway_id);
}

std::string var_name_slack_ub(int headway_id) {
    return "S_hub_" + std::to_string(headway_id);
}

std::string var_name_headway_dev_pos(int headway_id) {
    return "S_htp_" + std::to_string(headway_id);
}

std::string var_name_headway_dev_neg(int headway_id) {
    return "S_htn_" + std::to_string(headway_id);
}

std::string var_name_slack_conflict(int conflict_id) {
    return "S_conf_" + std::to_string(conflict_id);
}

std::string var_name_slack_option_conflict(int conflict_id) {
    return "S_opt_conf_" + std::to_string(conflict_id);
}

std::string var_name_slack_cover_miss(int slot_id) {
    return "S_cover_miss_" + std::to_string(slot_id);
}

std::string var_name_slack_cover_extra(int slot_id) {
    return "S_cover_extra_" + std::to_string(slot_id);
}

std::string var_name_slack_peak_cap(int peak_id) {
    return "S_peak_" + std::to_string(peak_id);
}

std::string var_name_slack_vehicle_cap() {
    return "S_vehicle_cap";
}

std::string var_name_slack_peak_xr0(int peak_id) {
    return "S_pxr0_" + std::to_string(peak_id);
}

std::string var_name_slack_peak_xr1(int peak_id) {
    return "S_pxr1_" + std::to_string(peak_id);
}

std::string var_name_slack_first_car(int target_id) {
    return "S_fc_" + std::to_string(target_id);
}

std::string var_name_dummy_zero() {
    return "Z_dummy_zero";
}

double get_value_or_zero(const std::unordered_map<std::string, double>& values, const std::string& key) {
    const auto it = values.find(key);
    if (it == values.end()) {
        return 0.0;
    }
    return it->second;
}

double get_value_or_zero(const std::unordered_map<int, double>& values, int key) {
    const auto it = values.find(key);
    if (it == values.end()) {
        return 0.0;
    }
    return it->second;
}

double get_value_or_zero(const std::unordered_map<std::uint64_t, double>& values, std::uint64_t key) {
    const auto it = values.find(key);
    if (it == values.end()) {
        return 0.0;
    }
    return it->second;
}

void load_instance(const fs::path& instance_dir, Instance& instance) {
    const auto manifest = load_manifest(instance_dir / "manifest.txt");
    if (manifest.count("vehicle_cost")) {
        instance.vehicle_cost = std::stoi(manifest.at("vehicle_cost"));
    }
    if (manifest.count("peak_vehicle_penalty")) {
        instance.peak_vehicle_penalty = std::stoi(manifest.at("peak_vehicle_penalty"));
    }
    if (manifest.count("vehicle_cap_penalty")) {
        instance.vehicle_cap_penalty = std::stoi(manifest.at("vehicle_cap_penalty"));
    }
    if (manifest.count("max_vehicle_count")) {
        instance.max_vehicle_count = std::stoi(manifest.at("max_vehicle_count"));
    }
    if (manifest.count("depot_usable_trains")) {
        instance.depot_usable_trains = std::stoi(manifest.at("depot_usable_trains"));
    }
    if (manifest.count("depot_parking_cap")) {
        instance.depot_parking_cap = std::stoi(manifest.at("depot_parking_cap"));
    }
    // Use depot_usable_trains to tighten max_vehicle_count when available
    if (instance.depot_usable_trains > 0 && instance.max_vehicle_count == 0) {
        instance.max_vehicle_count = instance.depot_usable_trains;
    } else if (instance.depot_usable_trains > 0 && instance.depot_usable_trains < instance.max_vehicle_count) {
        instance.max_vehicle_count = instance.depot_usable_trains;
    }
    if (manifest.count("first_car")) {
        instance.first_car = std::stoi(manifest.at("first_car"));
    }
    if (manifest.count("seed_phase")) {
        instance.seed_phase = std::stoi(manifest.at("seed_phase"));
    }
    if (manifest.count("headway_target_penalty")) {
        instance.headway_target_penalty = std::stoi(manifest.at("headway_target_penalty"));
    }
    if (manifest.count("cover_penalty")) {
        instance.cover_penalty = std::stoi(manifest.at("cover_penalty"));
    }
    if (manifest.count("cover_extra_penalty")) {
        instance.cover_extra_penalty = std::stoi(manifest.at("cover_extra_penalty"));
    } else {
        instance.cover_extra_penalty = instance.cover_penalty * 4;
    }
    if (manifest.count("headway_penalty")) {
        instance.headway_penalty = std::stoi(manifest.at("headway_penalty"));
    }
    if (manifest.count("conflict_penalty")) {
        instance.conflict_penalty = std::stoi(manifest.at("conflict_penalty"));
    }
    if (manifest.count("cbc_path")) {
        instance.cbc_path = fs::path(manifest.at("cbc_path")).lexically_normal().string();
    }

    for (const auto& row : load_csv(instance_dir / "slots.csv")) {
        Slot slot;
        slot.id = get_int(row, "slot_id");
        slot.direction = get_int(row, "direction");
        slot.order_in_direction = get_int(row, "order_in_direction");
        slot.phase_id = get_int(row, "phase_id");
        slot.xroad = get_int(row, "xroad");
        slot.route_id = get_int(row, "route_id");
        slot.round_num = get_int(row, "round_num");
        slot.nominal_departure = get_int(row, "nominal_departure");
        slot.headway_nominal_departure = get_int(row, "headway_nominal_departure", slot.nominal_departure);
        slot.nominal_arrival = get_int(row, "nominal_arrival");
        slot.target_gap = get_int(row, "target_gap");
        slot.shift_step = get_int(row, "shift_step");
        slot.first_real_idx = get_int(row, "first_real_idx", -1);
        slot.first_real_departure = get_int(row, "first_real_departure", slot.nominal_departure);
        slot.slot_min_track = get_int(row, "slot_min_track");
        slot.slot_tail_min_track = get_int(row, "slot_tail_min_track");
        slot.first_platform = get_str(row, "first_platform");
        slot.first_real_platform = get_str(row, "first_real_platform", slot.first_platform);
        slot.turnback_platform = get_str(row, "turnback_platform");
        instance.slot_by_id[slot.id] = slot;
        instance.slots.push_back(slot);
    }

    for (const auto& row : load_csv(instance_dir / "peaks.csv")) {
        PeakWindow peak;
        peak.id = get_int(row, "peak_id");
        peak.start_time = get_int(row, "start_time");
        peak.end_time = get_int(row, "end_time");
        peak.train_num = get_int(row, "train_num");
        peak.train_num1 = get_int(row, "train_num1");
        peak.train_num2 = get_int(row, "train_num2");
        peak.op_rate1 = get_int(row, "op_rate1");
        peak.op_rate2 = get_int(row, "op_rate2");
        peak.bit_index = static_cast<int>(instance.peaks.size());
        if (peak.bit_index >= 63) {
            throw std::runtime_error("Peak count exceeds 63, peak-incidence bitmask is not supported.");
        }
        peak.bit_mask = (static_cast<std::uint64_t>(1) << peak.bit_index);
        instance.peak_by_id[peak.id] = peak;
        instance.peaks.push_back(peak);
    }

    for (const auto& row : load_csv(instance_dir / "options.csv")) {
        Option option;
        option.id = get_int(row, "option_id");
        option.slot_id = get_int(row, "slot_id");
        option.direction = get_int(row, "direction");
        option.xroad = get_int(row, "xroad");
        option.route_id = get_int(row, "route_id");
        option.shift_seconds = get_int(row, "shift_seconds");
        option.departure = get_int(row, "departure");
        option.headway_departure = get_int(row, "headway_departure", option.departure);
        option.arrival = get_int(row, "arrival");
        option.first_real_departure = get_int(row, "first_real_departure", option.departure);
        option.peak_id = -1;
        option.peak_mask = 0;
        for (const auto& peak : instance.peaks) {
            if (!departure_in_peak(peak, option.departure)) {
                continue;
            }
            option.peak_id = peak.id;
            option.peak_mask = peak.bit_mask;
            break;
        }
        instance.option_by_id[option.id] = option;
        instance.options.push_back(option);
        instance.options_by_slot[option.slot_id].push_back(option.id);
    }

    for (const auto& row : load_csv(instance_dir / "first_car_targets.csv")) {
        FirstCarTarget target;
        target.id = get_int(row, "target_id");
        target.direction = get_int(row, "direction");
        target.slot_id = get_int(row, "slot_id");
        target.target_departure = get_int(row, "target_departure");
        target.route_id = get_str(row, "route_id");
        target.target_platform = get_str(row, "target_platform");
        const auto options_it = instance.options_by_slot.find(target.slot_id);
        if (options_it != instance.options_by_slot.end()) {
            for (const int option_id : options_it->second) {
                const auto& option = instance.option_by_id.at(option_id);
                if (option.first_real_departure != target.target_departure) {
                    continue;
                }
                target.valid_option_ids.push_back(option_id);
                target.valid_option_set.insert(option_id);
            }
        }
        if (target.valid_option_ids.empty()) {
            throw std::runtime_error(
                "No exact option found for first-car target slot " + std::to_string(target.slot_id) +
                " at departure " + std::to_string(target.target_departure)
            );
        }
        instance.first_car_target_by_id[target.id] = target;
        instance.first_car_targets.push_back(target);
    }

    for (const auto& row : load_csv(instance_dir / "headways.csv")) {
        Headway headway;
        headway.id = get_int(row, "headway_id");
        headway.direction = get_int(row, "direction");
        headway.lhs_slot_id = get_int(row, "lhs_slot_id");
        headway.rhs_slot_id = get_int(row, "rhs_slot_id");
        headway.target_gap = get_int(row, "target_gap");
        headway.min_headway = get_int(row, "min_headway");
        headway.max_headway = get_int(row, "max_headway");
        instance.headway_by_id[headway.id] = headway;
        instance.headways.push_back(headway);
        instance.headways_by_slot[headway.lhs_slot_id].push_back(headway.id);
        instance.headways_by_slot[headway.rhs_slot_id].push_back(headway.id);
    }

    for (const auto& row : load_csv(instance_dir / "option_conflicts.csv")) {
        OptionConflict conflict;
        conflict.id = get_int(row, "conflict_id");
        conflict.option_a = get_int(row, "option_a");
        conflict.option_b = get_int(row, "option_b");
        conflict.platform = get_str(row, "platform");
        conflict.min_interval = get_int(row, "min_interval");
        conflict.kind = get_str(row, "kind");
        instance.option_conflict_by_id[conflict.id] = conflict;
        instance.option_conflicts.push_back(conflict);
        instance.option_conflicts_by_option[conflict.option_a].push_back(conflict.id);
        instance.option_conflicts_by_option[conflict.option_b].push_back(conflict.id);
    }

    for (const auto& row : load_csv(instance_dir / "arcs.csv")) {
        Arc arc;
        arc.id = get_int(row, "arc_id");
        arc.from_option_id = get_int(row, "from_option_id");
        arc.to_option_id = get_int(row, "to_option_id");
        arc.from_slot_id = get_int(row, "from_slot_id");
        arc.to_slot_id = get_int(row, "to_slot_id");
        arc.effective_arrival = get_int(row, "effective_arrival");
        arc.wait_time = get_int(row, "wait_time");
        arc.turnback_platform = get_str(row, "turnback_platform");
        arc.min_tb = get_int(row, "min_tb");
        arc.def_tb = get_int(row, "def_tb");
        arc.max_tb = get_int(row, "max_tb");
        arc.is_mixed = get_int(row, "is_mixed") == 1;
        arc.same_turnback = get_int(row, "same_turnback") == 1;
        arc.event_id = get_int(row, "event_id", -1);
        arc.arc_cost = get_double(row, "arc_cost");
        instance.arc_by_id[arc.id] = arc;
        instance.arcs.push_back(arc);
        instance.outgoing_arcs_by_option[arc.from_option_id].push_back(arc.id);
        instance.arc_lookup[pair_key(arc.from_option_id, arc.to_option_id)] = arc.id;
    }

    for (const auto& row : load_csv(instance_dir / "arc_conflicts.csv")) {
        ArcConflict conflict;
        conflict.id = get_int(row, "conflict_id");
        conflict.event_a = get_int(row, "event_a");
        conflict.event_b = get_int(row, "event_b");
        conflict.platform = get_str(row, "platform");
        instance.conflict_by_id[conflict.id] = conflict;
        instance.conflicts.push_back(conflict);
        instance.conflict_rows_by_event[conflict.event_a].push_back(conflict.id);
        instance.conflict_rows_by_event[conflict.event_b].push_back(conflict.id);
    }

    // Load depot travel times (optional - present only when depot routes are configured)
    const fs::path depot_routes_path = instance_dir / "depot_routes.csv";
    if (fs::exists(depot_routes_path)) {
        for (const auto& row : load_csv(depot_routes_path)) {
            DepotRoute dr;
            dr.xroad = get_int(row, "xroad");
            dr.direction = get_int(row, "direction");
            dr.depot_out_time = get_int(row, "depot_out_time");
            dr.depot_in_time = get_int(row, "depot_in_time");
            dr.depot_gate_gap = get_int(row, "depot_gate_gap", 0);
            dr.depot_in_route_id = get_int(row, "depot_in_route_id", -1);
            dr.depot_out_route_id = get_int(row, "depot_out_route_id", -1);
            dr.depot_in_route_type = get_str(row, "depot_in_route_type");
            dr.depot_out_route_type = get_str(row, "depot_out_route_type");
            dr.depot_in_route_ids = get_str(row, "depot_in_route_ids");
            dr.depot_out_route_ids = get_str(row, "depot_out_route_ids");
            instance.depot_routes.push_back(dr);
            instance.depot_route_by_key[dr.xroad * 2 + dr.direction] = dr;
        }
        build_depot_endpoint_arcs(instance);
    }

    const fs::path seed_columns_path = instance_dir / "seed_columns.csv";
    if (fs::exists(seed_columns_path)) {
        std::unordered_map<int, std::vector<std::pair<int, SeedColumnStep>>> steps_by_seed;
        for (const auto& row : load_csv(seed_columns_path)) {
            const int seed_id = get_int(row, "seed_id", -1);
            if (seed_id < 0) {
                continue;
            }
            SeedColumnStep step;
            step.slot_id = get_int(row, "slot_id", -1);
            step.target_departure = get_int(row, "target_departure");
            if (step.slot_id < 0) {
                continue;
            }
            const int sequence_index = get_int(row, "sequence_index", 0);
            steps_by_seed[seed_id].push_back({sequence_index, step});
        }
        std::vector<int> seed_ids;
        seed_ids.reserve(steps_by_seed.size());
        for (const auto& entry : steps_by_seed) {
            seed_ids.push_back(entry.first);
        }
        std::sort(seed_ids.begin(), seed_ids.end());
        for (const int seed_id : seed_ids) {
            auto& indexed_steps = steps_by_seed.at(seed_id);
            std::sort(indexed_steps.begin(), indexed_steps.end(), [](const auto& lhs, const auto& rhs) {
                return lhs.first < rhs.first;
            });
            std::vector<SeedColumnStep> steps;
            steps.reserve(indexed_steps.size());
            for (const auto& entry : indexed_steps) {
                steps.push_back(entry.second);
            }
            if (!steps.empty()) {
                instance.seed_column_steps.push_back(std::move(steps));
            }
        }
    }

    std::sort(instance.slots.begin(), instance.slots.end(), [](const Slot& lhs, const Slot& rhs) {
        return lhs.id < rhs.id;
    });
    std::sort(instance.options.begin(), instance.options.end(), [](const Option& lhs, const Option& rhs) {
        if (lhs.departure != rhs.departure) {
            return lhs.departure < rhs.departure;
        }
        return lhs.id < rhs.id;
    });
    for (auto& entry : instance.outgoing_arcs_by_option) {
        auto& arc_ids = entry.second;
        std::sort(arc_ids.begin(), arc_ids.end(), [&](int lhs, int rhs) {
            const auto& arc_lhs = instance.arc_by_id.at(lhs);
            const auto& arc_rhs = instance.arc_by_id.at(rhs);
            const auto& to_lhs = instance.option_by_id.at(arc_lhs.to_option_id);
            const auto& to_rhs = instance.option_by_id.at(arc_rhs.to_option_id);
            if (to_lhs.departure != to_rhs.departure) {
                return to_lhs.departure < to_rhs.departure;
            }
            return lhs < rhs;
        });
    }
}

Column make_column_from_sequence(const Instance& instance, const std::vector<int>& option_ids, int column_id) {
    Column column;
    column.id = column_id;
    column.option_ids = option_ids;
    column.cost = static_cast<double>(instance.vehicle_cost);

    std::ostringstream key_builder;
    for (std::size_t index = 0; index < option_ids.size(); ++index) {
        const int option_id = option_ids[index];
        const auto& option = instance.option_by_id.at(option_id);
        if (index > 0) {
            key_builder << "-";
        }
        key_builder << option_id;
        column.slot_to_option[option.slot_id] = option_id;
        column.option_set.insert(option_id);
        column.cost += option_base_cost(option);
        column.peak_mask |= option.peak_mask;
        if (option.xroad == 0) {
            column.peak_mask_xr0 |= option.peak_mask;
        } else {
            column.peak_mask_xr1 |= option.peak_mask;
        }
        if (index == 0) {
            column.start_departure = option.departure;
            column.start_direction = option.direction;
            column.start_xroad = option.xroad;
            column.start_route_id = option.route_id;
            continue;
        }
        if (index + 1 == option_ids.size()) {
            column.end_arrival = option.arrival;
            column.end_direction = option.direction;
            column.end_xroad = option.xroad;
            column.end_route_id = option.route_id;
        }
        const int prev_option_id = option_ids[index - 1];
        const auto arc_it = instance.arc_lookup.find(pair_key(prev_option_id, option_id));
        if (arc_it == instance.arc_lookup.end()) {
            throw std::runtime_error("Missing arc for option sequence " + std::to_string(prev_option_id) + " -> " + std::to_string(option_id));
        }
        const int arc_id = arc_it->second;
        const auto& arc = instance.arc_by_id.at(arc_id);
        column.arc_ids.push_back(arc_id);
        column.direct_arc_pairs.insert(pair_key(prev_option_id, option_id));
        column.cost += arc.arc_cost;
        if (arc.event_id >= 0 && column.event_set.insert(arc.event_id).second) {
            column.event_ids.push_back(arc.event_id);
        }
    }
    // Handle single-option column: set end fields from start
    if (option_ids.size() == 1) {
        column.end_arrival = instance.option_by_id.at(option_ids[0]).arrival;
        column.end_direction = column.start_direction;
        column.end_xroad = column.start_xroad;
        column.end_route_id = column.start_route_id;
    }
    column.key = key_builder.str();

    // Add explicit depot source/sink arcs and set day_start/day_end.
    if (!column.option_ids.empty()) {
        const int first_option_id = column.option_ids.front();
        const auto source_it = instance.depot_source_arc_by_option.find(first_option_id);
        if (source_it != instance.depot_source_arc_by_option.end()) {
            column.depot_source_arc_id = source_it->second.id;
            column.depot_out_route_id = source_it->second.route_id;
            column.depot_out_time = source_it->second.travel_time;
            column.cost += source_it->second.arc_cost;
        }

        const int last_option_id = column.option_ids.back();
        const auto sink_it = instance.depot_sink_arc_by_option.find(last_option_id);
        if (sink_it != instance.depot_sink_arc_by_option.end()) {
            column.depot_sink_arc_id = sink_it->second.id;
            column.depot_in_route_id = sink_it->second.route_id;
            column.depot_in_time = sink_it->second.travel_time;
            column.cost += sink_it->second.arc_cost;
        }
    }
    column.day_start = (column.start_departure >= 0)
        ? column.start_departure - column.depot_out_time
        : column.start_departure;
    column.day_end = (column.end_arrival >= 0)
        ? column.end_arrival + column.depot_in_time
        : column.end_arrival;

    return column;
}

double headway_coefficient(const Instance& instance, const Column& column, const Headway& headway) {
    double coeff = 0.0;
    const auto lhs_it = column.slot_to_option.find(headway.lhs_slot_id);
    if (lhs_it != column.slot_to_option.end()) {
        coeff -= static_cast<double>(instance.option_by_id.at(lhs_it->second).headway_departure);
    }
    const auto rhs_it = column.slot_to_option.find(headway.rhs_slot_id);
    if (rhs_it != column.slot_to_option.end()) {
        coeff += static_cast<double>(instance.option_by_id.at(rhs_it->second).headway_departure);
    }
    return coeff;
}

int first_car_coefficient(const Column& column, const FirstCarTarget& target) {
    for (const int option_id : target.valid_option_ids) {
        if (column.option_set.count(option_id) != 0) {
            return 1;
        }
    }
    return 0;
}

int option_conflict_coefficient(const Column& column, const OptionConflict& conflict) {
    int coeff = 0;
    if (column.option_set.count(conflict.option_a) != 0) {
        ++coeff;
    }
    if (column.option_set.count(conflict.option_b) != 0) {
        ++coeff;
    }
    if (coeff == 2 && column_contains_direct_option_arc(column, conflict.option_a, conflict.option_b)) {
        --coeff;
    }
    return coeff;
}

int conflict_coefficient(const Column& column, const ArcConflict& conflict) {
    int coeff = 0;
    if (column.event_set.count(conflict.event_a) != 0) {
        ++coeff;
    }
    if (column.event_set.count(conflict.event_b) != 0) {
        ++coeff;
    }
    return coeff;
}

std::vector<int> collect_touched_headway_ids(const Instance& instance, const Column& column) {
    std::vector<int> headway_ids;
    for (const auto& entry : column.slot_to_option) {
        const auto headways_it = instance.headways_by_slot.find(entry.first);
        if (headways_it == instance.headways_by_slot.end()) {
            continue;
        }
        headway_ids.insert(headway_ids.end(), headways_it->second.begin(), headways_it->second.end());
    }
    std::sort(headway_ids.begin(), headway_ids.end());
    headway_ids.erase(std::unique(headway_ids.begin(), headway_ids.end()), headway_ids.end());
    return headway_ids;
}

std::vector<int> collect_touched_option_conflict_ids(const Instance& instance, const Column& column) {
    std::vector<int> conflict_ids;
    for (const int option_id : column.option_ids) {
        const auto conflicts_it = instance.option_conflicts_by_option.find(option_id);
        if (conflicts_it == instance.option_conflicts_by_option.end()) {
            continue;
        }
        conflict_ids.insert(conflict_ids.end(), conflicts_it->second.begin(), conflicts_it->second.end());
    }
    std::sort(conflict_ids.begin(), conflict_ids.end());
    conflict_ids.erase(std::unique(conflict_ids.begin(), conflict_ids.end()), conflict_ids.end());
    return conflict_ids;
}

std::vector<int> collect_touched_arc_conflict_ids(const Instance& instance, const Column& column) {
    std::vector<int> conflict_ids;
    for (const int event_id : column.event_ids) {
        const auto conflicts_it = instance.conflict_rows_by_event.find(event_id);
        if (conflicts_it == instance.conflict_rows_by_event.end()) {
            continue;
        }
        conflict_ids.insert(conflict_ids.end(), conflicts_it->second.begin(), conflicts_it->second.end());
    }
    std::sort(conflict_ids.begin(), conflict_ids.end());
    conflict_ids.erase(std::unique(conflict_ids.begin(), conflict_ids.end()), conflict_ids.end());
    return conflict_ids;
}

std::vector<SparseRowCoeff> build_master_column_row_coeffs(const Instance& instance, const Column& column) {
    const auto touched_headway_ids = collect_touched_headway_ids(instance, column);
    const auto touched_option_conflict_ids = collect_touched_option_conflict_ids(instance, column);
    const auto touched_arc_conflict_ids = collect_touched_arc_conflict_ids(instance, column);

    std::vector<SparseRowCoeff> coeffs;
    coeffs.reserve(
        1 + column.slot_to_option.size() + instance.peaks.size() * 3 +
        touched_headway_ids.size() * 3 + touched_option_conflict_ids.size() +
        touched_arc_conflict_ids.size() + instance.first_car_targets.size()
    );

    if (instance.max_vehicle_count > 0) {
        coeffs.push_back({row_name_vehicle_cap(), 1.0});
    }

    for (const auto& peak : instance.peaks) {
        if ((column.peak_mask & peak.bit_mask) != 0) {
            coeffs.push_back({row_name_peak_cap(peak.id), 1.0});
        }
        if (peak.train_num1 > 0 && (column.peak_mask_xr0 & peak.bit_mask) != 0) {
            coeffs.push_back({row_name_peak_cap_xr0(peak.id), 1.0});
        }
        if (peak.train_num2 > 0 && (column.peak_mask_xr1 & peak.bit_mask) != 0) {
            coeffs.push_back({row_name_peak_cap_xr1(peak.id), 1.0});
        }
    }

    for (const auto& entry : column.slot_to_option) {
        coeffs.push_back({row_name_cover(entry.first), 1.0});
    }

    for (const int headway_id : touched_headway_ids) {
        const auto& headway = instance.headway_by_id.at(headway_id);
        const double coeff = headway_coefficient(instance, column, headway);
        if (std::fabs(coeff) < kEps) {
            continue;
        }
        coeffs.push_back({row_name_headway_lb(headway.id), coeff});
        coeffs.push_back({row_name_headway_ub(headway.id), coeff});
        coeffs.push_back({row_name_headway_target(headway.id), coeff});
    }

    for (const int conflict_id : touched_option_conflict_ids) {
        const auto& conflict = instance.option_conflict_by_id.at(conflict_id);
        const int coeff = option_conflict_coefficient(column, conflict);
        if (coeff == 0) {
            continue;
        }
        coeffs.push_back({row_name_option_conflict(conflict.id), static_cast<double>(coeff)});
    }

    for (const int conflict_id : touched_arc_conflict_ids) {
        const auto& conflict = instance.conflict_by_id.at(conflict_id);
        const int coeff = conflict_coefficient(column, conflict);
        if (coeff == 0) {
            continue;
        }
        coeffs.push_back({row_name_conflict(conflict.id), static_cast<double>(coeff)});
    }

    for (const auto& target : instance.first_car_targets) {
        const int coeff = first_car_coefficient(column, target);
        if (coeff == 0) {
            continue;
        }
        coeffs.push_back({row_name_first_car(target.id), static_cast<double>(coeff)});
    }

    return coeffs;
}

std::unordered_map<std::string, std::vector<SparseRowCoeff>> build_extra_row_coeffs_by_var(
    const std::vector<DynamicRowPayload>& rows
) {
    std::unordered_map<std::string, std::vector<SparseRowCoeff>> coeffs_by_var;
    for (const auto& row : rows) {
        for (const auto& term : row.terms) {
            coeffs_by_var[term.var_name].push_back({row.row_name, term.coeff});
        }
    }
    return coeffs_by_var;
}

std::vector<StaticRowPayload> build_master_row_payloads(
    const Instance& instance,
    const std::vector<Column>& columns,
    const ActiveConflictRows& active_conflict_rows
) {
    const auto depot_gate_rows = build_incremental_depot_gate_rows(instance, columns, 0, nullptr);
    std::size_t row_capacity =
        instance.peaks.size() +
        (instance.max_vehicle_count > 0 ? 1 : 0) +
        instance.slots.size() +
        instance.headways.size() * 3 +
        active_conflict_rows.option_conflict_ids.size() +
        active_conflict_rows.arc_conflict_ids.size() +
        instance.first_car_targets.size() +
        depot_gate_rows.size();
    for (const auto& peak : instance.peaks) {
        if (peak.train_num1 > 0) {
            ++row_capacity;
        }
        if (peak.train_num2 > 0) {
            ++row_capacity;
        }
    }

    std::vector<StaticRowPayload> rows;
    rows.reserve(row_capacity);

    for (const auto& peak : instance.peaks) {
        rows.push_back({row_name_peak_cap(peak.id), "<=", static_cast<double>(peak.train_num)});
    }

    if (instance.max_vehicle_count > 0) {
        rows.push_back({row_name_vehicle_cap(), "<=", static_cast<double>(instance.max_vehicle_count)});
    }

    for (const auto& slot : instance.slots) {
        rows.push_back({row_name_cover(slot.id), "=", 1.0});
    }

    for (const auto& headway : instance.headways) {
        rows.push_back({row_name_headway_lb(headway.id), ">=", static_cast<double>(headway.min_headway)});
        rows.push_back({row_name_headway_ub(headway.id), "<=", static_cast<double>(headway.max_headway)});
        rows.push_back({row_name_headway_target(headway.id), "=", static_cast<double>(headway.target_gap)});
    }

    for (const int conflict_id : active_conflict_rows.option_conflict_ids) {
        rows.push_back({row_name_option_conflict(conflict_id), "<=", 1.0});
    }

    for (const int conflict_id : active_conflict_rows.arc_conflict_ids) {
        rows.push_back({row_name_conflict(conflict_id), "<=", 1.0});
    }

    for (const auto& target : instance.first_car_targets) {
        rows.push_back({row_name_first_car(target.id), ">=", 1.0});
    }

    for (const auto& row : depot_gate_rows) {
        rows.push_back({row.row_name, row.sense, row.rhs});
    }

    for (const auto& peak : instance.peaks) {
        if (peak.train_num1 > 0) {
            rows.push_back({row_name_peak_cap_xr0(peak.id), "<=", static_cast<double>(peak.train_num1)});
        }
    }

    for (const auto& peak : instance.peaks) {
        if (peak.train_num2 > 0) {
            rows.push_back({row_name_peak_cap_xr1(peak.id), "<=", static_cast<double>(peak.train_num2)});
        }
    }

    return rows;
}

std::vector<ModelVariablePayload> build_master_variable_payloads(
    const Instance& instance,
    const std::vector<Column>& columns,
    bool integer_master,
    const std::unordered_set<int>& fixed_column_ids,
    const ActiveConflictRows& active_conflict_rows
) {
    const auto depot_gate_rows = build_incremental_depot_gate_rows(instance, columns, 0, nullptr);
    const auto extra_row_coeffs_by_var = build_extra_row_coeffs_by_var(depot_gate_rows);

    std::size_t var_capacity =
        columns.size() +
        instance.peaks.size() +
        instance.slots.size() * 2 +
        instance.first_car_targets.size() +
        instance.headways.size() * 2 +
        active_conflict_rows.option_conflict_ids.size() +
        active_conflict_rows.arc_conflict_ids.size() +
        (instance.max_vehicle_count > 0 ? 1 : 0);
    for (const auto& peak : instance.peaks) {
        if (peak.train_num1 > 0) {
            ++var_capacity;
        }
        if (peak.train_num2 > 0) {
            ++var_capacity;
        }
    }

    std::vector<ModelVariablePayload> vars;
    vars.reserve(var_capacity);

    for (const auto& column : columns) {
        ModelVariablePayload payload;
        payload.var_name = var_name_column(column.id);
        payload.obj = column.cost;
        payload.lb = fixed_column_ids.count(column.id) != 0 ? 1.0 : 0.0;
        payload.ub = 1.0;
        payload.vtype = integer_master ? 'B' : 'C';
        payload.row_coeffs = build_master_column_row_coeffs(instance, column);
        const auto extra_it = extra_row_coeffs_by_var.find(payload.var_name);
        if (extra_it != extra_row_coeffs_by_var.end()) {
            payload.row_coeffs.insert(
                payload.row_coeffs.end(),
                extra_it->second.begin(),
                extra_it->second.end()
            );
        }
        vars.push_back(std::move(payload));
    }

    for (const auto& peak : instance.peaks) {
        vars.push_back({
            var_name_slack_peak_cap(peak.id),
            static_cast<double>(instance.peak_vehicle_penalty),
            0.0,
            std::nullopt,
            'C',
            {{row_name_peak_cap(peak.id), -1.0}}
        });
        if (peak.train_num1 > 0) {
            vars.push_back({
                var_name_slack_peak_xr0(peak.id),
                static_cast<double>(instance.peak_vehicle_penalty),
                0.0,
                std::nullopt,
                'C',
                {{row_name_peak_cap_xr0(peak.id), -1.0}}
            });
        }
        if (peak.train_num2 > 0) {
            vars.push_back({
                var_name_slack_peak_xr1(peak.id),
                static_cast<double>(instance.peak_vehicle_penalty),
                0.0,
                std::nullopt,
                'C',
                {{row_name_peak_cap_xr1(peak.id), -1.0}}
            });
        }
    }

    if (instance.max_vehicle_count > 0) {
        vars.push_back({
            var_name_slack_vehicle_cap(),
            static_cast<double>(instance.vehicle_cap_penalty),
            0.0,
            std::nullopt,
            'C',
            {{row_name_vehicle_cap(), -1.0}}
        });
    }

    for (const auto& slot : instance.slots) {
        vars.push_back({
            var_name_slack_cover_miss(slot.id),
            static_cast<double>(instance.cover_penalty),
            0.0,
            std::nullopt,
            'C',
            {{row_name_cover(slot.id), 1.0}}
        });
        vars.push_back({
            var_name_slack_cover_extra(slot.id),
            static_cast<double>(instance.cover_extra_penalty),
            0.0,
            std::nullopt,
            'C',
            {{row_name_cover(slot.id), -1.0}}
        });
    }

    for (const auto& target : instance.first_car_targets) {
        vars.push_back({
            var_name_slack_first_car(target.id),
            static_cast<double>(instance.cover_penalty),
            0.0,
            std::nullopt,
            'C',
            {{row_name_first_car(target.id), -1.0}}
        });
    }

    for (const auto& headway : instance.headways) {
        vars.push_back({
            var_name_headway_dev_pos(headway.id),
            static_cast<double>(instance.headway_target_penalty),
            0.0,
            std::nullopt,
            'C',
            {{row_name_headway_target(headway.id), -1.0}}
        });
        vars.push_back({
            var_name_headway_dev_neg(headway.id),
            static_cast<double>(instance.headway_target_penalty),
            0.0,
            std::nullopt,
            'C',
            {{row_name_headway_target(headway.id), 1.0}}
        });
    }

    for (const int conflict_id : active_conflict_rows.option_conflict_ids) {
        vars.push_back({
            var_name_slack_option_conflict(conflict_id),
            static_cast<double>(instance.conflict_penalty),
            0.0,
            std::nullopt,
            'C',
            {{row_name_option_conflict(conflict_id), -1.0}}
        });
    }

    for (const int conflict_id : active_conflict_rows.arc_conflict_ids) {
        vars.push_back({
            var_name_slack_conflict(conflict_id),
            static_cast<double>(instance.conflict_penalty),
            0.0,
            std::nullopt,
            'C',
            {{row_name_conflict(conflict_id), -1.0}}
        });
    }

    return vars;
}

void append_master_row_payloads_json(std::ostringstream& out, const std::vector<StaticRowPayload>& rows) {
    out << "[";
    for (std::size_t index = 0; index < rows.size(); ++index) {
        if (index > 0) {
            out << ",";
        }
        out << "{"
            << "\"row_name\":\"" << json_escape(rows[index].row_name) << "\","
            << "\"sense\":\"" << json_escape(rows[index].sense) << "\","
            << "\"rhs\":" << format_coeff(rows[index].rhs)
            << "}";
    }
    out << "]";
}

void append_dynamic_row_payloads_json(std::ostringstream& out, const std::vector<DynamicRowPayload>& rows) {
    out << "[";
    for (std::size_t row_index = 0; row_index < rows.size(); ++row_index) {
        if (row_index > 0) {
            out << ",";
        }
        out << "{"
            << "\"row_name\":\"" << json_escape(rows[row_index].row_name) << "\","
            << "\"sense\":\"" << json_escape(rows[row_index].sense) << "\","
            << "\"rhs\":" << format_coeff(rows[row_index].rhs) << ","
            << "\"terms\":[";
        for (std::size_t term_index = 0; term_index < rows[row_index].terms.size(); ++term_index) {
            if (term_index > 0) {
                out << ",";
            }
            out << "{"
                << "\"var_name\":\"" << json_escape(rows[row_index].terms[term_index].var_name) << "\","
                << "\"coeff\":" << format_coeff(rows[row_index].terms[term_index].coeff)
                << "}";
        }
        out << "]"
            << "}";
    }
    out << "]";
}

void append_master_variable_payloads_json(std::ostringstream& out, const std::vector<ModelVariablePayload>& vars) {
    out << "[";
    for (std::size_t index = 0; index < vars.size(); ++index) {
        if (index > 0) {
            out << ",";
        }
        out << "{"
            << "\"var_name\":\"" << json_escape(vars[index].var_name) << "\","
            << "\"obj\":" << format_coeff(vars[index].obj) << ","
            << "\"lb\":" << format_coeff(vars[index].lb) << ","
            << "\"ub\":";
        if (vars[index].ub.has_value()) {
            out << format_coeff(*vars[index].ub);
        } else {
            out << "null";
        }
        out << ",\"vtype\":\"" << vars[index].vtype << "\","
            << "\"row_coeffs\":[";
        for (std::size_t coeff_index = 0; coeff_index < vars[index].row_coeffs.size(); ++coeff_index) {
            if (coeff_index > 0) {
                out << ",";
            }
            out << "{"
                << "\"row_name\":\"" << json_escape(vars[index].row_coeffs[coeff_index].row_name) << "\","
                << "\"coeff\":" << format_coeff(vars[index].row_coeffs[coeff_index].coeff)
                << "}";
        }
        out << "]"
            << "}";
    }
    out << "]";
}

void append_master_model_json(
    std::ostringstream& out,
    const Instance& instance,
    const std::vector<Column>& columns,
    bool integer_master,
    const std::unordered_set<int>& fixed_column_ids
) {
    const ActiveConflictRows active_conflict_rows = collect_active_conflict_rows(instance, columns);
    const auto rows = build_master_row_payloads(instance, columns, active_conflict_rows);
    const auto vars = build_master_variable_payloads(instance, columns, integer_master, fixed_column_ids, active_conflict_rows);

    out << "\"model\":{"
        << "\"sense\":\"min\","
        << "\"rows\":";
    append_master_row_payloads_json(out, rows);
    out << ",\"variables\":";
    append_master_variable_payloads_json(out, vars);
    out << "}";
}

void write_master_model_json(
    const Instance& instance,
    const std::vector<Column>& columns,
    bool integer_master,
    const std::unordered_set<int>& fixed_column_ids,
    const fs::path& json_path
) {
    std::ofstream out(json_path);
    if (!out) {
        throw std::runtime_error("Unable to open model JSON for writing: " + json_path.string());
    }
    std::ostringstream payload;
    payload << "{";
    append_master_model_json(payload, instance, columns, integer_master, fixed_column_ids);
    payload << "}";
    out << payload.str();
}

ActiveConflictRows collect_active_conflict_rows(const Instance& instance, const std::vector<Column>& columns) {
    std::unordered_set<int> active_option_conflict_ids;
    std::unordered_set<int> active_arc_conflict_ids;

    for (const auto& column : columns) {
        for (const int option_id : column.option_ids) {
            const auto option_conflicts_it = instance.option_conflicts_by_option.find(option_id);
            if (option_conflicts_it == instance.option_conflicts_by_option.end()) {
                continue;
            }
            for (const int conflict_id : option_conflicts_it->second) {
                active_option_conflict_ids.insert(conflict_id);
            }
        }
        for (const int event_id : column.event_ids) {
            const auto event_conflicts_it = instance.conflict_rows_by_event.find(event_id);
            if (event_conflicts_it == instance.conflict_rows_by_event.end()) {
                continue;
            }
            for (const int conflict_id : event_conflicts_it->second) {
                active_arc_conflict_ids.insert(conflict_id);
            }
        }
    }

    ActiveConflictRows active_rows;
    active_rows.option_conflict_ids.assign(active_option_conflict_ids.begin(), active_option_conflict_ids.end());
    active_rows.arc_conflict_ids.assign(active_arc_conflict_ids.begin(), active_arc_conflict_ids.end());
    std::sort(active_rows.option_conflict_ids.begin(), active_rows.option_conflict_ids.end());
    std::sort(active_rows.arc_conflict_ids.begin(), active_rows.arc_conflict_ids.end());
    return active_rows;
}

ActiveConflictRows diff_active_conflict_rows(
    const ActiveConflictRows& current_rows,
    const ActiveConflictRows& loaded_rows
) {
    ActiveConflictRows diff_rows;
    std::set_difference(
        current_rows.option_conflict_ids.begin(),
        current_rows.option_conflict_ids.end(),
        loaded_rows.option_conflict_ids.begin(),
        loaded_rows.option_conflict_ids.end(),
        std::back_inserter(diff_rows.option_conflict_ids)
    );
    std::set_difference(
        current_rows.arc_conflict_ids.begin(),
        current_rows.arc_conflict_ids.end(),
        loaded_rows.arc_conflict_ids.begin(),
        loaded_rows.arc_conflict_ids.end(),
        std::back_inserter(diff_rows.arc_conflict_ids)
    );
    return diff_rows;
}

std::vector<DynamicRowPayload> build_incremental_conflict_rows(
    const Instance& instance,
    const std::vector<Column>& columns,
    const ActiveConflictRows& added_conflict_rows
) {
    std::vector<DynamicRowPayload> rows;
    rows.reserve(added_conflict_rows.option_conflict_ids.size() + added_conflict_rows.arc_conflict_ids.size());

    for (const int conflict_id : added_conflict_rows.option_conflict_ids) {
        const auto conflict_it = instance.option_conflict_by_id.find(conflict_id);
        if (conflict_it == instance.option_conflict_by_id.end()) {
            continue;
        }
        DynamicRowPayload row;
        row.row_name = row_name_option_conflict(conflict_id);
        row.sense = "<=";
        row.rhs = 1.0;
        for (const auto& column : columns) {
            const int coeff = option_conflict_coefficient(column, conflict_it->second);
            if (coeff == 0) {
                continue;
            }
            row.terms.push_back({var_name_column(column.id), static_cast<double>(coeff)});
        }
        if (!row.terms.empty()) {
            rows.push_back(std::move(row));
        }
    }

    for (const int conflict_id : added_conflict_rows.arc_conflict_ids) {
        const auto conflict_it = instance.conflict_by_id.find(conflict_id);
        if (conflict_it == instance.conflict_by_id.end()) {
            continue;
        }
        DynamicRowPayload row;
        row.row_name = row_name_conflict(conflict_id);
        row.sense = "<=";
        row.rhs = 1.0;
        for (const auto& column : columns) {
            const int coeff = conflict_coefficient(column, conflict_it->second);
            if (coeff == 0) {
                continue;
            }
            row.terms.push_back({var_name_column(column.id), static_cast<double>(coeff)});
        }
        if (!row.terms.empty()) {
            rows.push_back(std::move(row));
        }
    }

    return rows;
}

std::vector<ModelVariablePayload> build_incremental_conflict_slack_variables(
    const Instance& instance,
    const ActiveConflictRows& added_conflict_rows
) {
    std::vector<ModelVariablePayload> vars;
    vars.reserve(added_conflict_rows.option_conflict_ids.size() + added_conflict_rows.arc_conflict_ids.size());

    for (const int conflict_id : added_conflict_rows.option_conflict_ids) {
        vars.push_back({
            var_name_slack_option_conflict(conflict_id),
            static_cast<double>(instance.conflict_penalty),
            0.0,
            std::nullopt,
            'C',
            {{row_name_option_conflict(conflict_id), -1.0}}
        });
    }

    for (const int conflict_id : added_conflict_rows.arc_conflict_ids) {
        vars.push_back({
            var_name_slack_conflict(conflict_id),
            static_cast<double>(instance.conflict_penalty),
            0.0,
            std::nullopt,
            'C',
            {{row_name_conflict(conflict_id), -1.0}}
        });
    }

    return vars;
}

std::unordered_set<std::string> build_conflict_row_name_set(const ActiveConflictRows& conflict_rows) {
    std::unordered_set<std::string> row_names;
    row_names.reserve(conflict_rows.option_conflict_ids.size() + conflict_rows.arc_conflict_ids.size());
    for (const int conflict_id : conflict_rows.option_conflict_ids) {
        row_names.insert(row_name_option_conflict(conflict_id));
    }
    for (const int conflict_id : conflict_rows.arc_conflict_ids) {
        row_names.insert(row_name_conflict(conflict_id));
    }
    return row_names;
}

std::vector<SparseRowCoeff> filter_incremental_column_row_coeffs(
    const std::vector<SparseRowCoeff>& row_coeffs,
    const std::unordered_set<std::string>& excluded_row_names
) {
    if (excluded_row_names.empty()) {
        return row_coeffs;
    }
    std::vector<SparseRowCoeff> filtered;
    filtered.reserve(row_coeffs.size());
    for (const auto& coeff : row_coeffs) {
        if (excluded_row_names.count(coeff.row_name) != 0) {
            continue;
        }
        filtered.push_back(coeff);
    }
    return filtered;
}

std::unordered_set<std::string> collect_dynamic_row_names(const std::vector<DynamicRowPayload>& rows) {
    std::unordered_set<std::string> row_names;
    row_names.reserve(rows.size());
    for (const auto& row : rows) {
        row_names.insert(row.row_name);
    }
    return row_names;
}

bool depot_out_gate_conflict(const Instance& instance, const Column& lhs, const Column& rhs) {
    if (lhs.id == rhs.id || lhs.depot_out_time <= 0 || rhs.depot_out_time <= 0 ||
        lhs.start_departure < 0 || rhs.start_departure < 0) {
        return false;
    }
    const int lhs_key = lhs.start_xroad * 2 + lhs.start_direction;
    const int rhs_key = rhs.start_xroad * 2 + rhs.start_direction;
    if (lhs_key != rhs_key) {
        return false;
    }
    const auto dr_it = instance.depot_route_by_key.find(lhs_key);
    if (dr_it == instance.depot_route_by_key.end() || dr_it->second.depot_gate_gap <= 0) {
        return false;
    }
    return std::abs(lhs.start_departure - rhs.start_departure) < dr_it->second.depot_gate_gap;
}

bool depot_in_gate_conflict(const Instance& instance, const Column& lhs, const Column& rhs) {
    if (lhs.id == rhs.id || lhs.depot_in_time <= 0 || rhs.depot_in_time <= 0 ||
        lhs.end_arrival < 0 || rhs.end_arrival < 0) {
        return false;
    }
    const int lhs_key = lhs.end_xroad * 2 + lhs.end_direction;
    const int rhs_key = rhs.end_xroad * 2 + rhs.end_direction;
    if (lhs_key != rhs_key) {
        return false;
    }
    const auto dr_it = instance.depot_route_by_key.find(lhs_key);
    if (dr_it == instance.depot_route_by_key.end() || dr_it->second.depot_gate_gap <= 0) {
        return false;
    }
    return std::abs(lhs.end_arrival - rhs.end_arrival) < dr_it->second.depot_gate_gap;
}

std::vector<DynamicRowPayload> build_incremental_depot_gate_rows(
    const Instance& instance,
    const std::vector<Column>& columns,
    std::size_t loaded_column_count,
    DepotGateStats* stats
) {
    std::vector<DynamicRowPayload> rows;
    if (instance.depot_route_by_key.empty() || columns.empty()) {
        if (stats != nullptr) {
            *stats = DepotGateStats{};
        }
        return rows;
    }

    struct IndexedGateColumn {
        const Column* column = nullptr;
        std::size_t index = 0;
        int time = 0;
    };

    auto build_rows_for_kind = [&](bool depot_out, std::vector<DynamicRowPayload>& out_rows, DepotGateStats& out_stats) {
        std::unordered_map<int, std::vector<IndexedGateColumn>> by_key;
        by_key.reserve(instance.depot_route_by_key.size());
        for (std::size_t index = 0; index < columns.size(); ++index) {
            const Column& column = columns[index];
            if (depot_out) {
                if (column.depot_out_time <= 0 || column.start_departure < 0) {
                    continue;
                }
                const int key = column.start_xroad * 2 + column.start_direction;
                const auto dr_it = instance.depot_route_by_key.find(key);
                if (dr_it == instance.depot_route_by_key.end() || dr_it->second.depot_gate_gap <= 0) {
                    continue;
                }
                by_key[key].push_back({&column, index, column.start_departure});
            } else {
                if (column.depot_in_time <= 0 || column.end_arrival < 0) {
                    continue;
                }
                const int key = column.end_xroad * 2 + column.end_direction;
                const auto dr_it = instance.depot_route_by_key.find(key);
                if (dr_it == instance.depot_route_by_key.end() || dr_it->second.depot_gate_gap <= 0) {
                    continue;
                }
                by_key[key].push_back({&column, index, column.end_arrival});
            }
        }

        std::unordered_set<std::string> seen_row_names;
        for (auto& [resource_key, group] : by_key) {
            if (group.size() <= 1) {
                continue;
            }
            std::sort(group.begin(), group.end(), [](const IndexedGateColumn& lhs, const IndexedGateColumn& rhs) {
                if (lhs.time != rhs.time) {
                    return lhs.time < rhs.time;
                }
                return lhs.column->id < rhs.column->id;
            });
            const int gate_gap = instance.depot_route_by_key.at(resource_key).depot_gate_gap;

            std::size_t pair_right = 0;
            for (std::size_t left = 0; left < group.size(); ++left) {
                if (pair_right < left + 1) {
                    pair_right = left + 1;
                }
                while (pair_right < group.size() && group[pair_right].time - group[left].time < gate_gap) {
                    ++pair_right;
                }
                out_stats.pairwise_conflict_count += static_cast<long long>(pair_right - left - 1);
            }

            std::size_t left = 0;
            for (std::size_t right = 0; right < group.size(); ++right) {
                while (group[right].time - group[left].time >= gate_gap) {
                    ++left;
                }
                const std::size_t clique_size = right - left + 1;
                if (clique_size <= 1) {
                    continue;
                }
                const bool maximal_to_right =
                    (right + 1 == group.size()) ||
                    (group[right + 1].time - group[left].time >= gate_gap);
                if (!maximal_to_right) {
                    continue;
                }

                bool includes_new_column = (loaded_column_count == 0);
                if (loaded_column_count > 0) {
                    includes_new_column = false;
                    for (std::size_t idx = left; idx <= right; ++idx) {
                        if (group[idx].index >= loaded_column_count) {
                            includes_new_column = true;
                            break;
                        }
                    }
                }
                if (!includes_new_column) {
                    continue;
                }

                const int first_col_id = group[left].column->id;
                const int last_col_id = group[right].column->id;
                const std::string row_name = depot_out
                    ? row_name_depot_out_gate_clique(resource_key, first_col_id, last_col_id)
                    : row_name_depot_in_gate_clique(resource_key, first_col_id, last_col_id);
                if (!seen_row_names.insert(row_name).second) {
                    continue;
                }

                DynamicRowPayload row;
                row.row_name = row_name;
                row.sense = "<=";
                row.rhs = 1.0;
                row.terms.reserve(clique_size);
                for (std::size_t idx = left; idx <= right; ++idx) {
                    row.terms.push_back({var_name_column(group[idx].column->id), 1.0});
                }
                out_rows.push_back(std::move(row));
                ++out_stats.clique_row_count;
            }
        }
    };

    DepotGateStats computed_stats;
    build_rows_for_kind(true, rows, computed_stats);
    build_rows_for_kind(false, rows, computed_stats);
    if (stats != nullptr) {
        *stats = computed_stats;
    }
    return rows;
}

DepotGateStats compute_depot_gate_stats(const Instance& instance, const std::vector<Column>& columns) {
    DepotGateStats stats;
    if (instance.depot_route_by_key.empty() || columns.empty()) {
        return stats;
    }

    struct GateTimePoint {
        int column_id = -1;
        int time = 0;
    };

    auto accumulate_kind = [&](bool depot_out) {
        std::unordered_map<int, std::vector<GateTimePoint>> by_key;
        by_key.reserve(instance.depot_route_by_key.size());
        for (const auto& column : columns) {
            if (depot_out) {
                if (column.depot_out_time <= 0 || column.start_departure < 0) {
                    continue;
                }
                const int key = column.start_xroad * 2 + column.start_direction;
                const auto dr_it = instance.depot_route_by_key.find(key);
                if (dr_it == instance.depot_route_by_key.end() || dr_it->second.depot_gate_gap <= 0) {
                    continue;
                }
                by_key[key].push_back({column.id, column.start_departure});
            } else {
                if (column.depot_in_time <= 0 || column.end_arrival < 0) {
                    continue;
                }
                const int key = column.end_xroad * 2 + column.end_direction;
                const auto dr_it = instance.depot_route_by_key.find(key);
                if (dr_it == instance.depot_route_by_key.end() || dr_it->second.depot_gate_gap <= 0) {
                    continue;
                }
                by_key[key].push_back({column.id, column.end_arrival});
            }
        }

        for (auto& [resource_key, group] : by_key) {
            if (group.size() <= 1) {
                continue;
            }
            std::sort(group.begin(), group.end(), [](const GateTimePoint& lhs, const GateTimePoint& rhs) {
                if (lhs.time != rhs.time) {
                    return lhs.time < rhs.time;
                }
                return lhs.column_id < rhs.column_id;
            });
            const int gate_gap = instance.depot_route_by_key.at(resource_key).depot_gate_gap;
            std::size_t pair_right = 0;
            for (std::size_t left = 0; left < group.size(); ++left) {
                if (pair_right < left + 1) {
                    pair_right = left + 1;
                }
                while (pair_right < group.size() && group[pair_right].time - group[left].time < gate_gap) {
                    ++pair_right;
                }
                stats.pairwise_conflict_count += static_cast<long long>(pair_right - left - 1);
            }

            std::size_t left = 0;
            for (std::size_t right = 0; right < group.size(); ++right) {
                while (group[right].time - group[left].time >= gate_gap) {
                    ++left;
                }
                if (right - left + 1 <= 1) {
                    continue;
                }
                const bool maximal_to_right =
                    (right + 1 == group.size()) ||
                    (group[right + 1].time - group[left].time >= gate_gap);
                if (maximal_to_right) {
                    ++stats.clique_row_count;
                }
            }
        }
    };

    accumulate_kind(true);
    accumulate_kind(false);
    return stats;
}

std::pair<int, int> slot_headway_departure_range(const Instance& instance, int slot_id) {
    const auto it = instance.options_by_slot.find(slot_id);
    if (it == instance.options_by_slot.end() || it->second.empty()) {
        return {std::numeric_limits<int>::max(), std::numeric_limits<int>::min()};
    }
    int min_departure = std::numeric_limits<int>::max();
    int max_departure = std::numeric_limits<int>::min();
    for (const int option_id : it->second) {
        const auto& option = instance.option_by_id.at(option_id);
        min_departure = std::min(min_departure, option.headway_departure);
        max_departure = std::max(max_departure, option.headway_departure);
    }
    return {min_departure, max_departure};
}

bool headway_has_feasible_completion(
    const Instance& instance,
    const std::unordered_map<int, int>& fixed_slot_to_option,
    const Headway& headway
) {
    int lhs_min = 0;
    int lhs_max = 0;
    int rhs_min = 0;
    int rhs_max = 0;

    const auto lhs_fixed = fixed_slot_to_option.find(headway.lhs_slot_id);
    if (lhs_fixed != fixed_slot_to_option.end()) {
        const int departure = instance.option_by_id.at(lhs_fixed->second).headway_departure;
        lhs_min = departure;
        lhs_max = departure;
    } else {
        const auto lhs_range = slot_headway_departure_range(instance, headway.lhs_slot_id);
        lhs_min = lhs_range.first;
        lhs_max = lhs_range.second;
    }

    const auto rhs_fixed = fixed_slot_to_option.find(headway.rhs_slot_id);
    if (rhs_fixed != fixed_slot_to_option.end()) {
        const int departure = instance.option_by_id.at(rhs_fixed->second).headway_departure;
        rhs_min = departure;
        rhs_max = departure;
    } else {
        const auto rhs_range = slot_headway_departure_range(instance, headway.rhs_slot_id);
        rhs_min = rhs_range.first;
        rhs_max = rhs_range.second;
    }

    if (lhs_min > lhs_max || rhs_min > rhs_max) {
        return false;
    }

    const int possible_gap_min = rhs_min - lhs_max;
    const int possible_gap_max = rhs_max - lhs_min;
    return possible_gap_max >= headway.min_headway && possible_gap_min <= headway.max_headway;
}

bool can_fix_column_without_breaking_hard_rows(
    const Instance& instance,
    const std::vector<Column>& columns,
    const std::unordered_set<int>& fixed_column_ids,
    const Column& candidate
) {
    if (fixed_column_ids.count(candidate.id) != 0) {
        return false;
    }
    if (instance.max_vehicle_count > 0 &&
        static_cast<int>(fixed_column_ids.size()) + 1 > instance.max_vehicle_count) {
        return false;
    }

    std::unordered_map<int, int> fixed_slot_to_option;
    std::vector<const Column*> fixed_columns;
    fixed_columns.reserve(fixed_column_ids.size());

    for (const auto& column : columns) {
        if (fixed_column_ids.count(column.id) == 0) {
            continue;
        }
        fixed_columns.push_back(&column);
        for (const auto& entry : column.slot_to_option) {
            const auto existing = fixed_slot_to_option.find(entry.first);
            if (existing != fixed_slot_to_option.end() && existing->second != entry.second) {
                return false;
            }
            fixed_slot_to_option[entry.first] = entry.second;
        }
    }

    for (const auto& entry : candidate.slot_to_option) {
        if (fixed_slot_to_option.count(entry.first) != 0) {
            return false;
        }
        fixed_slot_to_option[entry.first] = entry.second;
    }

    // The master already prices option/arc conflicts with explicit slack variables.
    // Keep the fixing filter aligned with the model by enforcing only truly hard
    // compatibility here; otherwise orthodox TCG reintroduces the old hard cut.
    for (const auto* fixed_column : fixed_columns) {
        if (depot_out_gate_conflict(instance, *fixed_column, candidate) ||
            depot_in_gate_conflict(instance, *fixed_column, candidate)) {
            return false;
        }
    }
    for (const auto& headway : instance.headways) {
        if (!headway_has_feasible_completion(instance, fixed_slot_to_option, headway)) {
            return false;
        }
    }
    return true;
}

std::vector<int> select_tcg_fix_column_ids(
    const Instance& instance,
    const std::vector<Column>& columns,
    const std::unordered_map<std::string, double>& primal_values,
    const std::unordered_set<int>& fixed_column_ids,
    const Config& config
) {
    if (!config.enable_orthodox_tcg || config.tcg_fix_columns <= 0) {
        return {};
    }

    struct FixCandidate {
        const Column* column = nullptr;
        double value = 0.0;
    };

    std::vector<FixCandidate> ranked_candidates;
    std::vector<FixCandidate> positive_candidates;
    std::vector<FixCandidate> forced_candidates;
    ranked_candidates.reserve(columns.size());
    positive_candidates.reserve(columns.size());
    forced_candidates.reserve(columns.size());
    for (const auto& column : columns) {
        if (fixed_column_ids.count(column.id) != 0) {
            continue;
        }
        const double value = get_value_or_zero(primal_values, var_name_column(column.id));
        if (value > kEps) {
            positive_candidates.push_back({&column, value});
        }
        if (value + kEps < config.tcg_fix_min_value) {
            continue;
        }
        ranked_candidates.push_back({&column, value});
        if (value + kEps >= config.tcg_fix_force_value) {
            forced_candidates.push_back({&column, value});
        }
    }

    const auto candidate_desc = [](const FixCandidate& lhs, const FixCandidate& rhs) {
        if (std::fabs(lhs.value - rhs.value) > kEps) {
            return lhs.value > rhs.value;
        }
        if (lhs.column->option_ids.size() != rhs.column->option_ids.size()) {
            return lhs.column->option_ids.size() > rhs.column->option_ids.size();
        }
        return lhs.column->id < rhs.column->id;
    };
    std::sort(ranked_candidates.begin(), ranked_candidates.end(), candidate_desc);
    std::sort(positive_candidates.begin(), positive_candidates.end(), candidate_desc);
    std::sort(forced_candidates.begin(), forced_candidates.end(), candidate_desc);

    std::unordered_set<int> working_fixed = fixed_column_ids;
    std::vector<int> selected_ids;
    selected_ids.reserve(std::max<int>(config.tcg_fix_columns, static_cast<int>(forced_candidates.size())));

    // First, force in every sufficiently strong LP column.
    for (const auto& candidate : forced_candidates) {
        if (!can_fix_column_without_breaking_hard_rows(instance, columns, working_fixed, *candidate.column)) {
            continue;
        }
        working_fixed.insert(candidate.column->id);
        selected_ids.push_back(candidate.column->id);
    }
    if (!selected_ids.empty()) {
        return selected_ids;
    }

    // Then prefer the base-threshold top-N bucket.
    for (const auto& candidate : ranked_candidates) {
        if (!can_fix_column_without_breaking_hard_rows(instance, columns, working_fixed, *candidate.column)) {
            continue;
        }
        working_fixed.insert(candidate.column->id);
        selected_ids.push_back(candidate.column->id);
        if (static_cast<int>(selected_ids.size()) >= config.tcg_fix_columns) {
            break;
        }
    }
    if (!selected_ids.empty()) {
        return selected_ids;
    }

    // As a last resort, avoid an empty fixing round by taking the top-N positive LP columns.
    for (const auto& candidate : positive_candidates) {
        if (!can_fix_column_without_breaking_hard_rows(instance, columns, working_fixed, *candidate.column)) {
            continue;
        }
        working_fixed.insert(candidate.column->id);
        selected_ids.push_back(candidate.column->id);
        if (static_cast<int>(selected_ids.size()) >= config.tcg_fix_columns) {
            break;
        }
    }
    return selected_ids;
}

bool update_best_integer_result(
    const MasterSolveResult& candidate,
    const std::string& source_tag,
    MasterSolveResult& best_result,
    std::string& best_source_tag,
    bool& has_best_result
) {
    if (!candidate.ok) {
        return false;
    }
    if (!has_best_result || candidate.objective + kEps < best_result.objective) {
        best_result = candidate;
        best_source_tag = source_tag;
        has_best_result = true;
        return true;
    }
    return false;
}

double compute_column_reduced_cost(
    const Instance& instance,
    const Column& column,
    const std::unordered_map<std::string, double>& row_duals
) {
    const auto touched_headway_ids = collect_touched_headway_ids(instance, column);
    const auto touched_option_conflict_ids = collect_touched_option_conflict_ids(instance, column);
    const auto touched_arc_conflict_ids = collect_touched_arc_conflict_ids(instance, column);

    double reduced_cost = column.cost;
    if (instance.max_vehicle_count > 0) {
        reduced_cost -= get_value_or_zero(row_duals, row_name_vehicle_cap());
    }
    for (const auto& peak : instance.peaks) {
        if ((column.peak_mask & peak.bit_mask) == 0) {
            continue;
        }
        reduced_cost -= get_value_or_zero(row_duals, row_name_peak_cap(peak.id));
    }
    for (const auto& peak : instance.peaks) {
        if (peak.train_num1 > 0 && (column.peak_mask_xr0 & peak.bit_mask) != 0) {
            reduced_cost -= get_value_or_zero(row_duals, row_name_peak_cap_xr0(peak.id));
        }
        if (peak.train_num2 > 0 && (column.peak_mask_xr1 & peak.bit_mask) != 0) {
            reduced_cost -= get_value_or_zero(row_duals, row_name_peak_cap_xr1(peak.id));
        }
    }
    for (const auto& entry : column.slot_to_option) {
        reduced_cost -= get_value_or_zero(row_duals, row_name_cover(entry.first));
    }
    for (const auto& target : instance.first_car_targets) {
        const int coeff = first_car_coefficient(column, target);
        if (coeff == 0) {
            continue;
        }
        reduced_cost -= get_value_or_zero(row_duals, row_name_first_car(target.id)) * static_cast<double>(coeff);
    }
    for (const int headway_id : touched_headway_ids) {
        const auto& headway = instance.headway_by_id.at(headway_id);
        const double coeff = headway_coefficient(instance, column, headway);
        if (std::fabs(coeff) < kEps) {
            continue;
        }
        reduced_cost -= get_value_or_zero(row_duals, row_name_headway_lb(headway.id)) * coeff;
        reduced_cost -= get_value_or_zero(row_duals, row_name_headway_ub(headway.id)) * coeff;
        reduced_cost -= get_value_or_zero(row_duals, row_name_headway_target(headway.id)) * coeff;
    }
    for (const int conflict_id : touched_option_conflict_ids) {
        const auto& conflict = instance.option_conflict_by_id.at(conflict_id);
        const int coeff = option_conflict_coefficient(column, conflict);
        if (coeff == 0) {
            continue;
        }
        reduced_cost -= get_value_or_zero(row_duals, row_name_option_conflict(conflict.id)) * static_cast<double>(coeff);
    }
    for (const int conflict_id : touched_arc_conflict_ids) {
        const auto& conflict = instance.conflict_by_id.at(conflict_id);
        const int coeff = conflict_coefficient(column, conflict);
        if (coeff == 0) {
            continue;
        }
        reduced_cost -= get_value_or_zero(row_duals, row_name_conflict(conflict.id)) * static_cast<double>(coeff);
    }
    return reduced_cost;
}

std::unordered_map<int, double> compute_option_activity(
    const std::vector<Column>& columns,
    const std::unordered_map<std::string, double>& primal_values,
    double activity_epsilon
) {
    std::unordered_map<int, double> option_activity;
    for (const auto& column : columns) {
        const double value = get_value_or_zero(primal_values, var_name_column(column.id));
        if (value <= activity_epsilon) {
            continue;
        }
        for (const int option_id : column.option_ids) {
            option_activity[option_id] += value;
        }
    }
    return option_activity;
}

std::vector<int> select_representative_options(
    const Instance& instance,
    const std::unordered_map<int, double>* option_activity
) {
    std::vector<int> selected_option_ids;
    selected_option_ids.reserve(instance.slots.size());
    for (const auto& slot : instance.slots) {
        const auto options_it = instance.options_by_slot.find(slot.id);
        if (options_it == instance.options_by_slot.end() || options_it->second.empty()) {
            continue;
        }
        int best_option_id = options_it->second.front();
        double best_score = option_activity == nullptr ? 0.0 : get_value_or_zero(*option_activity, best_option_id);
        for (const int option_id : options_it->second) {
            const double score = option_activity == nullptr ? 0.0 : get_value_or_zero(*option_activity, option_id);
            const auto& best_option = instance.option_by_id.at(best_option_id);
            const auto& option = instance.option_by_id.at(option_id);
            if (score > best_score + kEps) {
                best_option_id = option_id;
                best_score = score;
                continue;
            }
            if (std::fabs(score - best_score) > kEps) {
                continue;
            }
            if (std::abs(option.shift_seconds) < std::abs(best_option.shift_seconds)) {
                best_option_id = option_id;
                continue;
            }
            if (std::abs(option.shift_seconds) == std::abs(best_option.shift_seconds) && option.departure < best_option.departure) {
                best_option_id = option_id;
            }
        }
        selected_option_ids.push_back(best_option_id);
    }
    return selected_option_ids;
}

std::vector<std::vector<int>> build_path_cover_sequences(
    const Instance& instance,
    const std::vector<int>& selected_option_ids
) {
    std::unordered_set<int> selected_set(selected_option_ids.begin(), selected_option_ids.end());
    std::unordered_map<int, std::vector<int>> adjacency;
    for (const int option_id : selected_option_ids) {
        const auto out_it = instance.outgoing_arcs_by_option.find(option_id);
        if (out_it == instance.outgoing_arcs_by_option.end()) {
            continue;
        }
        auto& next_options = adjacency[option_id];
        for (const int arc_id : out_it->second) {
            const auto& arc = instance.arc_by_id.at(arc_id);
            if (selected_set.count(arc.to_option_id) == 0) {
                continue;
            }
            next_options.push_back(arc.to_option_id);
        }
        std::sort(next_options.begin(), next_options.end(), [&](int lhs, int rhs) {
            const auto& option_lhs = instance.option_by_id.at(lhs);
            const auto& option_rhs = instance.option_by_id.at(rhs);
            if (option_lhs.departure != option_rhs.departure) {
                return option_lhs.departure < option_rhs.departure;
            }
            return lhs < rhs;
        });
    }

    constexpr int kInfDistance = std::numeric_limits<int>::max();
    std::unordered_map<int, int> pair_u;
    std::unordered_map<int, int> pair_v;
    std::unordered_map<int, int> distance;
    for (const int option_id : selected_option_ids) {
        pair_u[option_id] = -1;
        pair_v[option_id] = -1;
    }

    auto bfs = [&]() -> bool {
        std::queue<int> queue;
        bool found_augmenting_path = false;
        for (const int option_id : selected_option_ids) {
            if (pair_u[option_id] == -1) {
                distance[option_id] = 0;
                queue.push(option_id);
            } else {
                distance[option_id] = kInfDistance;
            }
        }
        while (!queue.empty()) {
            const int current = queue.front();
            queue.pop();
            const auto adj_it = adjacency.find(current);
            if (adj_it == adjacency.end()) {
                continue;
            }
            for (const int next : adj_it->second) {
                const int matched = pair_v[next];
                if (matched == -1) {
                    found_augmenting_path = true;
                    continue;
                }
                if (distance[matched] != kInfDistance) {
                    continue;
                }
                distance[matched] = distance[current] + 1;
                queue.push(matched);
            }
        }
        return found_augmenting_path;
    };

    std::function<bool(int)> dfs = [&](int current) -> bool {
        const auto adj_it = adjacency.find(current);
        if (adj_it == adjacency.end()) {
            distance[current] = kInfDistance;
            return false;
        }
        for (const int next : adj_it->second) {
            const int matched = pair_v[next];
            if (matched == -1 || (distance[matched] == distance[current] + 1 && dfs(matched))) {
                pair_u[current] = next;
                pair_v[next] = current;
                return true;
            }
        }
        distance[current] = kInfDistance;
        return false;
    };

    while (bfs()) {
        for (const int option_id : selected_option_ids) {
            if (pair_u[option_id] == -1) {
                dfs(option_id);
            }
        }
    }

    std::vector<int> start_options;
    start_options.reserve(selected_option_ids.size());
    for (const int option_id : selected_option_ids) {
        if (pair_v[option_id] == -1) {
            start_options.push_back(option_id);
        }
    }
    std::sort(start_options.begin(), start_options.end(), [&](int lhs, int rhs) {
        const auto& option_lhs = instance.option_by_id.at(lhs);
        const auto& option_rhs = instance.option_by_id.at(rhs);
        if (option_lhs.departure != option_rhs.departure) {
            return option_lhs.departure < option_rhs.departure;
        }
        return lhs < rhs;
    });

    std::unordered_set<int> visited;
    std::vector<std::vector<int>> sequences;
    for (const int start_option_id : start_options) {
        if (visited.count(start_option_id) != 0) {
            continue;
        }
        std::vector<int> sequence;
        int current = start_option_id;
        while (current != -1 && visited.insert(current).second) {
            sequence.push_back(current);
            current = pair_u[current];
        }
        if (!sequence.empty()) {
            sequences.push_back(std::move(sequence));
        }
    }

    for (const int option_id : selected_option_ids) {
        if (visited.count(option_id) != 0) {
            continue;
        }
        sequences.push_back({option_id});
    }
    return sequences;
}

std::vector<Column> build_columns_from_sequences(
    const Instance& instance,
    const std::vector<std::vector<int>>& sequences,
    const std::unordered_set<std::string>& existing_keys,
    int start_column_id
) {
    std::vector<Column> columns;
    std::unordered_set<std::string> seen_keys;
    for (const auto& sequence : sequences) {
        if (sequence.size() <= 1) {
            continue;
        }
        Column column = make_column_from_sequence(instance, sequence, start_column_id + static_cast<int>(columns.size()));
        if (existing_keys.count(column.key) != 0 || seen_keys.count(column.key) != 0) {
            continue;
        }
        seen_keys.insert(column.key);
        columns.push_back(std::move(column));
    }
    std::sort(columns.begin(), columns.end(), [](const Column& lhs, const Column& rhs) {
        if (lhs.option_ids.size() != rhs.option_ids.size()) {
            return lhs.option_ids.size() > rhs.option_ids.size();
        }
        return lhs.key < rhs.key;
    });
    return columns;
}

std::optional<std::vector<int>> materialize_seed_option_sequence(
    const Instance& instance,
    const std::vector<SeedColumnStep>& steps
) {
    if (steps.empty()) {
        return std::nullopt;
    }

    struct SeedDpState {
        double cost = std::numeric_limits<double>::infinity();
        int prev_option_id = -1;
    };

    std::vector<std::unordered_map<int, SeedDpState>> dp(steps.size());
    for (std::size_t index = 0; index < steps.size(); ++index) {
        const auto options_it = instance.options_by_slot.find(steps[index].slot_id);
        if (options_it == instance.options_by_slot.end() || options_it->second.empty()) {
            return std::nullopt;
        }

        for (const int option_id : options_it->second) {
            const auto& option = instance.option_by_id.at(option_id);
            const double hint_cost =
                static_cast<double>(std::abs(option.departure - steps[index].target_departure)) / 60.0
                + static_cast<double>(std::abs(option.shift_seconds)) / 6000.0;
            if (index == 0) {
                dp[index][option_id] = {hint_cost, -1};
                continue;
            }

            double best_cost = std::numeric_limits<double>::infinity();
            int best_prev_option = -1;
            for (const auto& prev_entry : dp[index - 1]) {
                const int prev_option_id = prev_entry.first;
                if (instance.arc_lookup.count(pair_key(prev_option_id, option_id)) == 0) {
                    continue;
                }
                const double total_cost = prev_entry.second.cost + hint_cost;
                if (total_cost + kEps < best_cost) {
                    best_cost = total_cost;
                    best_prev_option = prev_option_id;
                }
            }
            if (best_prev_option >= 0) {
                dp[index][option_id] = {best_cost, best_prev_option};
            }
        }

        if (dp[index].empty()) {
            return std::nullopt;
        }
    }

    double best_cost = std::numeric_limits<double>::infinity();
    int current_option_id = -1;
    for (const auto& entry : dp.back()) {
        if (entry.second.cost + kEps < best_cost) {
            best_cost = entry.second.cost;
            current_option_id = entry.first;
        }
    }
    if (current_option_id < 0) {
        return std::nullopt;
    }

    std::vector<int> option_ids(steps.size(), -1);
    for (int index = static_cast<int>(steps.size()) - 1; index >= 0; --index) {
        option_ids[index] = current_option_id;
        const auto state_it = dp[index].find(current_option_id);
        if (state_it == dp[index].end()) {
            return std::nullopt;
        }
        current_option_id = state_it->second.prev_option_id;
    }
    return option_ids;
}

std::vector<Column> build_columns_from_seed_steps(
    const Instance& instance,
    const std::unordered_set<std::string>& existing_keys,
    int start_column_id
) {
    std::vector<Column> columns;
    std::unordered_set<std::string> seen_keys;
    for (const auto& seed_steps : instance.seed_column_steps) {
        if (seed_steps.size() <= 1) {
            continue;
        }
        const auto option_ids = materialize_seed_option_sequence(instance, seed_steps);
        if (!option_ids.has_value() || option_ids->size() <= 1) {
            continue;
        }
        Column column = make_column_from_sequence(instance, *option_ids, start_column_id + static_cast<int>(columns.size()));
        if (existing_keys.count(column.key) != 0 || seen_keys.count(column.key) != 0) {
            continue;
        }
        seen_keys.insert(column.key);
        columns.push_back(std::move(column));
    }
    std::sort(columns.begin(), columns.end(), [](const Column& lhs, const Column& rhs) {
        if (lhs.option_ids.size() != rhs.option_ids.size()) {
            return lhs.option_ids.size() > rhs.option_ids.size();
        }
        return lhs.key < rhs.key;
    });
    return columns;
}

std::vector<Column> build_initial_columns(const Instance& instance) {
    std::vector<Column> columns;
    columns.reserve(instance.options.size() + instance.slots.size() + instance.seed_column_steps.size());
    std::unordered_set<std::string> existing_keys;
    int column_id = 0;

    auto legacy_seed_columns = build_columns_from_seed_steps(instance, existing_keys, column_id);
    for (auto& column : legacy_seed_columns) {
        column.id = column_id++;
        column.is_legacy_seed = true;
        existing_keys.insert(column.key);
        columns.push_back(std::move(column));
    }

    const auto selected_option_ids = select_representative_options(instance, nullptr);
    const auto sequences = build_path_cover_sequences(instance, selected_option_ids);
    auto seeded_columns = build_columns_from_sequences(instance, sequences, existing_keys, column_id);
    for (auto& column : seeded_columns) {
        column.id = column_id++;
        existing_keys.insert(column.key);
        columns.push_back(std::move(column));
    }

    for (const auto& option : instance.options) {
        columns.push_back(make_column_from_sequence(instance, {option.id}, column_id));
        existing_keys.insert(columns.back().key);
        ++column_id;
    }
    return columns;
}

BasisNeighborhood build_basis_neighborhood(
    const std::vector<Column>& columns,
    const std::unordered_map<std::string, double>& primal_values,
    double activity_epsilon
) {
    BasisNeighborhood neighborhood;
    for (const auto& column : columns) {
        const double value = get_value_or_zero(primal_values, var_name_column(column.id));
        if (value <= activity_epsilon) {
            continue;
        }
        neighborhood.active_columns.push_back(&column);
        for (const int option_id : column.option_ids) {
            neighborhood.option_activity[option_id] += value;
        }
        for (const int arc_id : column.arc_ids) {
            neighborhood.arc_activity[arc_id] += value;
        }
        for (const int event_id : column.event_ids) {
            neighborhood.event_activity[event_id] += value;
        }
    }
    return neighborhood;
}

std::vector<int> reconstruct_prefix(
    int end_option_id,
    const std::unordered_map<int, int>& predecessor_option
) {
    std::vector<int> sequence;
    int current = end_option_id;
    while (current >= 0) {
        sequence.push_back(current);
        const auto pred_it = predecessor_option.find(current);
        if (pred_it == predecessor_option.end()) {
            break;
        }
        current = pred_it->second;
    }
    std::reverse(sequence.begin(), sequence.end());
    return sequence;
}

std::vector<int> reconstruct_suffix(
    int start_option_id,
    const std::unordered_map<int, int>& successor_option
) {
    std::vector<int> sequence;
    int current = start_option_id;
    while (current >= 0) {
        sequence.push_back(current);
        const auto succ_it = successor_option.find(current);
        if (succ_it == successor_option.end()) {
            break;
        }
        current = succ_it->second;
    }
    return sequence;
}

void append_lp_term(std::ostream& out, bool& first_term, int& line_len, double coeff, const std::string& var_name) {
    if (std::fabs(coeff) < kEps) {
        return;
    }
    std::ostringstream term;
    const bool negative = coeff < 0.0;
    if (first_term) {
        term << (negative ? " - " : " ");
    } else {
        term << (negative ? " - " : " + ");
    }
    term << format_coeff(std::fabs(coeff)) << " " << var_name;
    const std::string token = term.str();
    if (line_len + static_cast<int>(token.size()) > 180) {
        out << "\n   ";
        line_len = 3;
    }
    out << token;
    line_len += static_cast<int>(token.size());
    first_term = false;
}

void finish_lp_row(std::ostream& out, bool first_term, const std::string& sense, double rhs) {
    if (first_term) {
        out << " 0";
    }
    out << " " << sense << " " << format_coeff(rhs) << "\n";
}

// Detect depot throat gate conflicts and write them as LP constraints.
// We use clique/window rows instead of pairwise rows to reduce row growth:
// all columns within one maximal gate-conflict window share one row
//   sum x_i <= 1
// This is exact for the unit-interval conflict structure induced by depot_gate_gap.
void write_depot_gate_constraints(std::ostream& out, const std::vector<Column>& columns,
                                  const Instance& instance) {
    const auto gate_rows = build_incremental_depot_gate_rows(instance, columns, 0, nullptr);
    for (const auto& row : gate_rows) {
        out << " " << row.row_name << ":";
        bool first_term = true;
        int line_len = static_cast<int>(row.row_name.size()) + 2;
        for (const auto& term : row.terms) {
            append_lp_term(out, first_term, line_len, term.coeff, term.var_name);
        }
        finish_lp_row(out, first_term, row.sense, row.rhs);
    }
}

void write_master_lp(
    const Instance& instance,
    const std::vector<Column>& columns,
    bool integer_master,
    const std::unordered_set<int>& fixed_column_ids,
    const fs::path& lp_path
) {
    std::ofstream out(lp_path);
    if (!out) {
        throw std::runtime_error("Unable to open LP file for writing: " + lp_path.string());
    }
    bool dummy_zero_used = false;
    const ActiveConflictRows active_conflict_rows = collect_active_conflict_rows(instance, columns);

    out << "Minimize\n obj:";
    bool first_term = true;
    int line_len = 5;
    for (const auto& column : columns) {
        append_lp_term(out, first_term, line_len, column.cost, var_name_column(column.id));
    }
    for (const auto& peak : instance.peaks) {
        append_lp_term(out, first_term, line_len, static_cast<double>(instance.peak_vehicle_penalty), var_name_slack_peak_cap(peak.id));
        if (peak.train_num1 > 0) {
            append_lp_term(out, first_term, line_len, static_cast<double>(instance.peak_vehicle_penalty), var_name_slack_peak_xr0(peak.id));
        }
        if (peak.train_num2 > 0) {
            append_lp_term(out, first_term, line_len, static_cast<double>(instance.peak_vehicle_penalty), var_name_slack_peak_xr1(peak.id));
        }
    }
    if (instance.max_vehicle_count > 0) {
        append_lp_term(out, first_term, line_len, static_cast<double>(instance.vehicle_cap_penalty), var_name_slack_vehicle_cap());
    }
    for (const auto& slot : instance.slots) {
        append_lp_term(out, first_term, line_len, static_cast<double>(instance.cover_penalty), var_name_slack_cover_miss(slot.id));
        append_lp_term(out, first_term, line_len, static_cast<double>(instance.cover_extra_penalty), var_name_slack_cover_extra(slot.id));
    }
    for (const auto& target : instance.first_car_targets) {
        append_lp_term(out, first_term, line_len, static_cast<double>(instance.cover_penalty), var_name_slack_first_car(target.id));
    }
    for (const auto& headway : instance.headways) {
        append_lp_term(out, first_term, line_len, static_cast<double>(instance.headway_target_penalty), var_name_headway_dev_pos(headway.id));
        append_lp_term(out, first_term, line_len, static_cast<double>(instance.headway_target_penalty), var_name_headway_dev_neg(headway.id));
    }
    for (const int conflict_id : active_conflict_rows.option_conflict_ids) {
        append_lp_term(out, first_term, line_len, static_cast<double>(instance.conflict_penalty), var_name_slack_option_conflict(conflict_id));
    }
    for (const int conflict_id : active_conflict_rows.arc_conflict_ids) {
        append_lp_term(out, first_term, line_len, static_cast<double>(instance.conflict_penalty), var_name_slack_conflict(conflict_id));
    }
    out << "\nSubject To\n";

    for (const auto& peak : instance.peaks) {
        const std::string row_name = row_name_peak_cap(peak.id);
        out << " " << row_name << ":";
        first_term = true;
        line_len = static_cast<int>(row_name.size()) + 2;
        for (const auto& column : columns) {
            if ((column.peak_mask & peak.bit_mask) != 0) {
                append_lp_term(out, first_term, line_len, 1.0, var_name_column(column.id));
            }
        }
        append_lp_term(out, first_term, line_len, -1.0, var_name_slack_peak_cap(peak.id));
        finish_lp_row(out, first_term, "<=", static_cast<double>(peak.train_num));
    }

    if (instance.max_vehicle_count > 0) {
        const std::string row_name = row_name_vehicle_cap();
        out << " " << row_name << ":";
        first_term = true;
        line_len = static_cast<int>(row_name.size()) + 2;
        for (const auto& column : columns) {
            append_lp_term(out, first_term, line_len, 1.0, var_name_column(column.id));
        }
        append_lp_term(out, first_term, line_len, -1.0, var_name_slack_vehicle_cap());
        finish_lp_row(out, first_term, "<=", static_cast<double>(instance.max_vehicle_count));
    }

    for (const auto& slot : instance.slots) {
        const std::string row_name = row_name_cover(slot.id);
        out << " " << row_name << ":";
        first_term = true;
        line_len = static_cast<int>(row_name.size()) + 2;
        for (const auto& column : columns) {
            if (column.slot_to_option.count(slot.id) != 0) {
                append_lp_term(out, first_term, line_len, 1.0, var_name_column(column.id));
            }
        }
        append_lp_term(out, first_term, line_len, 1.0, var_name_slack_cover_miss(slot.id));
        append_lp_term(out, first_term, line_len, -1.0, var_name_slack_cover_extra(slot.id));
        finish_lp_row(out, first_term, "=", 1.0);
    }

    for (const auto& headway : instance.headways) {
        const std::string lb_name = row_name_headway_lb(headway.id);
        out << " " << lb_name << ":";
        first_term = true;
        line_len = static_cast<int>(lb_name.size()) + 2;
        for (const auto& column : columns) {
            append_lp_term(out, first_term, line_len, headway_coefficient(instance, column, headway), var_name_column(column.id));
        }
        finish_lp_row(out, first_term, ">=", static_cast<double>(headway.min_headway));

        const std::string ub_name = row_name_headway_ub(headway.id);
        out << " " << ub_name << ":";
        first_term = true;
        line_len = static_cast<int>(ub_name.size()) + 2;
        for (const auto& column : columns) {
            append_lp_term(out, first_term, line_len, headway_coefficient(instance, column, headway), var_name_column(column.id));
        }
        finish_lp_row(out, first_term, "<=", static_cast<double>(headway.max_headway));

        const std::string target_name = row_name_headway_target(headway.id);
        out << " " << target_name << ":";
        first_term = true;
        line_len = static_cast<int>(target_name.size()) + 2;
        for (const auto& column : columns) {
            append_lp_term(out, first_term, line_len, headway_coefficient(instance, column, headway), var_name_column(column.id));
        }
        append_lp_term(out, first_term, line_len, -1.0, var_name_headway_dev_pos(headway.id));
        append_lp_term(out, first_term, line_len, 1.0, var_name_headway_dev_neg(headway.id));
        finish_lp_row(out, first_term, "=", static_cast<double>(headway.target_gap));
    }

    for (const int conflict_id : active_conflict_rows.option_conflict_ids) {
        const auto& conflict = instance.option_conflict_by_id.at(conflict_id);
        const std::string row_name = row_name_option_conflict(conflict.id);
        out << " " << row_name << ":";
        first_term = true;
        line_len = static_cast<int>(row_name.size()) + 2;
        for (const auto& column : columns) {
            const int coeff = option_conflict_coefficient(column, conflict);
            if (coeff == 0) {
                continue;
            }
            append_lp_term(out, first_term, line_len, static_cast<double>(coeff), var_name_column(column.id));
        }
        if (first_term) {
            dummy_zero_used = true;
            append_lp_term(out, first_term, line_len, 1.0, var_name_dummy_zero());
        }
        append_lp_term(out, first_term, line_len, -1.0, var_name_slack_option_conflict(conflict.id));
        finish_lp_row(out, first_term, "<=", 1.0);
    }

    for (const int conflict_id : active_conflict_rows.arc_conflict_ids) {
        const auto& conflict = instance.conflict_by_id.at(conflict_id);
        const std::string row_name = row_name_conflict(conflict.id);
        out << " " << row_name << ":";
        first_term = true;
        line_len = static_cast<int>(row_name.size()) + 2;
        for (const auto& column : columns) {
            append_lp_term(out, first_term, line_len, static_cast<double>(conflict_coefficient(column, conflict)), var_name_column(column.id));
        }
        if (first_term) {
            dummy_zero_used = true;
            append_lp_term(out, first_term, line_len, 1.0, var_name_dummy_zero());
        }
        append_lp_term(out, first_term, line_len, -1.0, var_name_slack_conflict(conflict.id));
        finish_lp_row(out, first_term, "<=", 1.0);
    }

    for (const auto& target : instance.first_car_targets) {
        const std::string row_name = row_name_first_car(target.id);
        out << " " << row_name << ":";
        first_term = true;
        line_len = static_cast<int>(row_name.size()) + 2;
        for (const auto& column : columns) {
            const int coeff = first_car_coefficient(column, target);
            if (coeff == 0) {
                continue;
            }
            append_lp_term(out, first_term, line_len, static_cast<double>(coeff), var_name_column(column.id));
        }
        append_lp_term(out, first_term, line_len, -1.0, var_name_slack_first_car(target.id));
        finish_lp_row(out, first_term, ">=", 1.0);
    }

    // Depot throat gate resource conflicts (depot-out and depot-in)
    if (!instance.depot_route_by_key.empty()) {
        write_depot_gate_constraints(out, columns, instance);
    }

    for (const auto& peak : instance.peaks) {
        if (peak.train_num1 <= 0) {
            continue;
        }
        const std::string row_name = row_name_peak_cap_xr0(peak.id);
        out << " " << row_name << ":";
        first_term = true;
        line_len = static_cast<int>(row_name.size()) + 2;
        for (const auto& column : columns) {
            if ((column.peak_mask_xr0 & peak.bit_mask) != 0) {
                append_lp_term(out, first_term, line_len, 1.0, var_name_column(column.id));
            }
        }
        append_lp_term(out, first_term, line_len, -1.0, var_name_slack_peak_xr0(peak.id));
        finish_lp_row(out, first_term, "<=", static_cast<double>(peak.train_num1));
    }

    for (const auto& peak : instance.peaks) {
        if (peak.train_num2 <= 0) {
            continue;
        }
        const std::string row_name = row_name_peak_cap_xr1(peak.id);
        out << " " << row_name << ":";
        first_term = true;
        line_len = static_cast<int>(row_name.size()) + 2;
        for (const auto& column : columns) {
            if ((column.peak_mask_xr1 & peak.bit_mask) != 0) {
                append_lp_term(out, first_term, line_len, 1.0, var_name_column(column.id));
            }
        }
        append_lp_term(out, first_term, line_len, -1.0, var_name_slack_peak_xr1(peak.id));
        finish_lp_row(out, first_term, "<=", static_cast<double>(peak.train_num2));
    }

    out << "Bounds\n";
    for (const auto& column : columns) {
        const std::string column_name = var_name_column(column.id);
        if (fixed_column_ids.count(column.id) != 0) {
            out << " 1 <= " << column_name << " <= 1\n";
        } else {
            out << " 0 <= " << column_name << " <= 1\n";
        }
    }
    for (const auto& peak : instance.peaks) {
        out << " 0 <= " << var_name_slack_peak_cap(peak.id) << "\n";
        if (peak.train_num1 > 0) {
            out << " 0 <= " << var_name_slack_peak_xr0(peak.id) << "\n";
        }
        if (peak.train_num2 > 0) {
            out << " 0 <= " << var_name_slack_peak_xr1(peak.id) << "\n";
        }
    }
    if (instance.max_vehicle_count > 0) {
        out << " 0 <= " << var_name_slack_vehicle_cap() << "\n";
    }
    for (const auto& slot : instance.slots) {
        out << " 0 <= " << var_name_slack_cover_miss(slot.id) << "\n";
        out << " 0 <= " << var_name_slack_cover_extra(slot.id) << "\n";
    }
    for (const auto& target : instance.first_car_targets) {
        out << " 0 <= " << var_name_slack_first_car(target.id) << "\n";
    }
    if (dummy_zero_used) {
        out << " 0 <= " << var_name_dummy_zero() << " <= 0\n";
    }
    for (const auto& headway : instance.headways) {
        out << " 0 <= " << var_name_headway_dev_pos(headway.id) << "\n";
        out << " 0 <= " << var_name_headway_dev_neg(headway.id) << "\n";
    }
    for (const int conflict_id : active_conflict_rows.option_conflict_ids) {
        out << " 0 <= " << var_name_slack_option_conflict(conflict_id) << "\n";
    }
    for (const int conflict_id : active_conflict_rows.arc_conflict_ids) {
        out << " 0 <= " << var_name_slack_conflict(conflict_id) << "\n";
    }

    if (integer_master) {
        out << "Binary\n";
        for (const auto& column : columns) {
            out << " " << var_name_column(column.id) << "\n";
        }
    }
    out << "End\n";
}

double elapsed_seconds(const std::chrono::steady_clock::time_point& start, const std::chrono::steady_clock::time_point& end) {
    return std::chrono::duration_cast<std::chrono::duration<double>>(end - start).count();
}

double parse_objective_from_status(const std::string& status_line) {
    const auto pos = status_line.rfind(' ');
    if (pos == std::string::npos) {
        return 0.0;
    }
    try {
        return std::stod(status_line.substr(pos + 1));
    } catch (...) {
        return 0.0;
    }
}

bool cbc_status_has_feasible_solution(const std::string& status_line, bool integer_master) {
    const std::string lowered = lower_copy(status_line);
    if (lowered.find("optimal") != std::string::npos) {
        return true;
    }
    if (lowered.find("stopped on time") == std::string::npos) {
        return false;
    }
    if (!integer_master) {
        return true;
    }
    return lowered.find("no integer solution") == std::string::npos;
}

MasterSolveResult parse_cbc_solution(const fs::path& solution_path, bool integer_master) {
    MasterSolveResult result;
    std::ifstream in(solution_path);
    if (!in) {
        return result;
    }

    std::string line;
    if (!std::getline(in, line)) {
        return result;
    }
    result.status = trim(line);
    result.objective = parse_objective_from_status(result.status);
    result.ok = cbc_status_has_feasible_solution(result.status, integer_master);

    while (std::getline(in, line)) {
        line = trim(line);
        if (line.empty()) {
            continue;
        }
        std::istringstream iss(line);
        std::vector<std::string> tokens;
        std::string token;
        while (iss >> token) {
            tokens.push_back(token);
        }
        if (tokens.size() < 4) {
            continue;
        }
        std::size_t index = 0;
        if (tokens[index] == "**") {
            ++index;
        }
        if (tokens.size() < index + 4) {
            continue;
        }
        const std::string& name = tokens[index + 1];
        double value = 0.0;
        double shadow = 0.0;
        try {
            value = std::stod(tokens[index + 2]);
            shadow = std::stod(tokens[index + 3]);
        } catch (...) {
            continue;
        }
        if (starts_with(name, "R_")) {
            result.row_duals[name] = shadow;
        } else {
            result.primal_values[name] = value;
        }
    }

    return result;
}

MasterSolveResult solve_master_with_cbc(
    const Instance& instance,
    const std::vector<Column>& columns,
    bool integer_master,
    const std::unordered_set<int>& fixed_column_ids,
    const fs::path& work_dir,
    const std::string& cbc_path,
    const std::string& python_exe,
    int master_time_limit_sec,
    double mip_gap,
    const std::string& tag,
    bool debug
) {
    try {
        auto result = solve_master_with_coinmp(
            instance,
            columns,
            integer_master,
            fixed_column_ids,
            work_dir,
            python_exe,
            master_time_limit_sec,
            mip_gap,
            tag,
            debug
        );
        result.requested_solver = "CBC";
        result.actual_solver = "CBC_COINMP";
        return result;
    } catch (const std::exception& e) {
        if (debug) {
            std::cout << "[debug] CoinMP bridge failed for " << tag << ", falling back to CBC CLI: "
                      << e.what() << "\n";
        }
    }

    fs::create_directories(work_dir);
    const fs::path lp_path = work_dir / (tag + ".lp");
    const fs::path solution_path = work_dir / (tag + ".sol");
    write_master_lp(instance, columns, integer_master, fixed_column_ids, lp_path);

#ifdef _WIN32
    std::vector<std::string> argv_storage = {
        cbc_path,
        lp_path.string()
    };
    if (integer_master) {
        argv_storage.push_back("sec");
        argv_storage.push_back(std::to_string(master_time_limit_sec));
        argv_storage.push_back("ratioGap");
        argv_storage.push_back(format_coeff(mip_gap));
    }
    argv_storage.insert(argv_storage.end(), {
        "solve",
        "printingOptions",
        "all",
        "solution",
        solution_path.string()
    });
    std::vector<const char*> argv;
    argv.reserve(argv_storage.size() + 1);
    for (const auto& arg : argv_storage) {
        argv.push_back(arg.c_str());
    }
    argv.push_back(nullptr);
    if (debug) {
        std::cout << "[debug] CBC argv:";
        for (const auto& arg : argv_storage) {
            std::cout << " [" << arg << "]";
        }
        std::cout << "\n";
    }
    const intptr_t exit_code = _spawnvp(_P_WAIT, argv_storage.front().c_str(), argv.data());
#else
    std::string command = quote(cbc_path) + " " + quote(lp_path.string());
    if (integer_master) {
        command += " sec " + std::to_string(master_time_limit_sec)
            + " ratioGap " + format_coeff(mip_gap);
    }
    command += " solve printingOptions all solution " + quote(solution_path.string());
    if (debug) {
        std::cout << "[debug] CBC command: " << command << "\n";
    }
    const int exit_code = std::system(command.c_str());
#endif
    if (exit_code != 0 && debug) {
        std::cout << "[debug] CBC exit code: " << exit_code << "\n";
    }
    if (!fs::exists(solution_path)) {
        throw std::runtime_error("CBC did not produce solution file: " + solution_path.string());
    }
    auto result = parse_cbc_solution(solution_path, integer_master);
    if (!result.ok) {
        const std::string lowered_status = lower_copy(result.status);
        if (!(integer_master && lowered_status.find("no integer solution") != std::string::npos)) {
            throw std::runtime_error("CBC solve failed for " + tag + ": " + result.status);
        }
    }
    result.actual_solver = "CBC";
    return result;
}

// ---------- Gurobi solver support ----------

MasterSolveResult parse_gurobi_solution(const fs::path& sol_path, const fs::path& lp_path) {
    MasterSolveResult result;
    // Gurobi .sol format: first line is comment "# Objective value = <value>"
    // then lines of "varname value"
    std::ifstream in(sol_path);
    if (!in) {
        return result;
    }
    std::string line;
    while (std::getline(in, line)) {
        line = trim(line);
        if (line.empty()) continue;
        if (line[0] == '#') {
            // Parse objective from "# Objective value = 1234.56"
            auto pos = line.find("Objective value");
            if (pos != std::string::npos) {
                auto eq = line.find('=', pos);
                if (eq != std::string::npos) {
                    try {
                        result.objective = std::stod(trim(line.substr(eq + 1)));
                    } catch (...) {}
                }
            }
            continue;
        }
        // Primal value line: "varname value"
        std::istringstream iss(line);
        std::string name;
        double value = 0.0;
        if (iss >> name >> value) {
            result.primal_values[name] = value;
        }
    }
    result.status = "Optimal";
    result.ok = true;

    // For CG we also need row duals. Gurobi writes them in a separate .ilp or we can
    // get them by solving the dual or using the attributes file.
    // Strategy: use Gurobi's ResultFile parameter with .sol for primals,
    // and write a small Python helper or use the .attr file.
    // Alternative: write a Gurobi parameter file that writes dual info.
    // For now, use Gurobi's JSON solution output which includes both primals and duals.

    return result;
}

MasterSolveResult parse_gurobi_json_solution(const fs::path& json_path) {
    MasterSolveResult result;
    std::ifstream in(json_path);
    if (!in) {
        return result;
    }
    // Read entire file
    std::string content((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());

    // Simple JSON parser for Gurobi's solution JSON format
    // Format: { "SolutionInfo": { "ObjVal": ..., ... },
    //           "Vars": [ { "VarName": "x0", "X": 1.0 }, ... ],
    //           "Constrs": [ { "ConstrName": "R_cover_0", "Pi": 1234.0 }, ... ] }

    auto find_number = [&](const std::string& key, std::size_t start_pos) -> double {
        auto pos = content.find("\"" + key + "\"", start_pos);
        if (pos == std::string::npos) return 0.0;
        pos = content.find(':', pos);
        if (pos == std::string::npos) return 0.0;
        ++pos;
        while (pos < content.size() && (content[pos] == ' ' || content[pos] == '\t')) ++pos;
        try {
            return std::stod(content.substr(pos));
        } catch (...) { return 0.0; }
    };

    auto find_string = [&](const std::string& key, std::size_t start_pos) -> std::string {
        auto pos = content.find("\"" + key + "\"", start_pos);
        if (pos == std::string::npos) return "";
        pos = content.find(':', pos);
        if (pos == std::string::npos) return "";
        ++pos;
        while (pos < content.size() && (content[pos] == ' ' || content[pos] == '\t')) ++pos;
        if (pos < content.size() && content[pos] == '"') {
            ++pos;
            auto end = content.find('"', pos);
            if (end != std::string::npos) return content.substr(pos, end - pos);
        }
        return "";
    };

    // Parse ObjVal
    result.objective = find_number("ObjVal", 0);

    const std::string error_message = find_string("Error", 0);
    if (!error_message.empty()) {
        result.status = error_message;
    }

    int status_code = 2;
    auto status_pos = content.find("\"Status\"");
    if (status_pos != std::string::npos) {
        status_code = static_cast<int>(find_number("Status", status_pos));
    }

    // Parse variable values (Vars array)
    std::size_t vars_pos = content.find("\"Vars\"");
    if (vars_pos != std::string::npos) {
        std::size_t search_pos = vars_pos;
        while (true) {
            auto vn_pos = content.find("\"VarName\"", search_pos);
            if (vn_pos == std::string::npos) break;
            std::string var_name = find_string("VarName", vn_pos);
            double var_value = find_number("X", vn_pos);
            if (!var_name.empty()) {
                result.primal_values[var_name] = var_value;
            }
            search_pos = vn_pos + 10;
            // Safety: stop if we've gone past Constrs section
            auto next_section = content.find("\"Constrs\"", vars_pos);
            if (next_section != std::string::npos && search_pos > next_section) break;
        }
    }

    // Parse constraint duals (Constrs array)
    std::size_t constrs_pos = content.find("\"Constrs\"");
    if (constrs_pos != std::string::npos) {
        std::size_t search_pos = constrs_pos;
        while (true) {
            auto cn_pos = content.find("\"ConstrName\"", search_pos);
            if (cn_pos == std::string::npos) break;
            std::string constr_name = find_string("ConstrName", cn_pos);
            double dual_value = find_number("Pi", cn_pos);
            if (!constr_name.empty()) {
                result.row_duals[constr_name] = dual_value;
            }
            search_pos = cn_pos + 13;
        }
    }

    const double sol_count = find_number("SolCount", 0);
    const bool has_solution = sol_count >= 1.0 || !result.primal_values.empty();
    result.ok = (status_code == 2)
             || (has_solution && (status_code == 9 || status_code == 13));
    if (!error_message.empty() && !has_solution) {
        result.ok = false;
        result.status = error_message;
    } else if (status_code == 2) {
        result.status = "Optimal";
    } else {
        result.status = has_solution
            ? "Feasible (status=" + std::to_string(status_code) + ")"
            : "Not optimal (status=" + std::to_string(status_code) + ")";
    }

    return result;
}

class PersistentGurobiMasterSession {
public:
    PersistentGurobiMasterSession(
        const Instance& instance,
        fs::path session_dir,
        std::string python_exe,
        bool debug
    ) : instance_(instance),
        session_dir_(std::move(session_dir)),
        python_exe_(std::move(python_exe)),
        debug_(debug) {
        request_path_ = session_dir_ / "request.json";
        response_path_ = session_dir_ / "response.json";
    }

    ~PersistentGurobiMasterSession() {
        shutdown();
    }

    MasterSolveResult solve(
        const std::vector<Column>& columns,
        const std::unordered_set<int>& fixed_column_ids,
        int master_time_limit_sec
    ) {
        start_server();
        if (!initialized_) {
            return initialize_and_solve(columns, fixed_column_ids, master_time_limit_sec);
        }
        if (columns.size() < loaded_column_count_) {
            throw std::runtime_error("Persistent master column count is inconsistent");
        }
        return add_columns_and_solve(columns, fixed_column_ids, master_time_limit_sec);
    }

    void shutdown() {
        if (!started_) {
            return;
        }
        try {
            write_request_json("{\"command\":\"shutdown\"}");
            wait_for_response(5000);
        } catch (...) {
        }
        std::error_code ec;
        fs::remove(request_path_, ec);
        fs::remove(response_path_, ec);
        started_ = false;
        initialized_ = false;
        loaded_column_count_ = 0;
        loaded_fixed_column_ids_.clear();
        loaded_active_conflict_rows_ = {};
        loaded_depot_gate_row_names_.clear();
    }

private:
    const Instance& instance_;
    fs::path session_dir_;
    fs::path request_path_;
    fs::path response_path_;
    std::string python_exe_;
    bool debug_ = false;
    bool started_ = false;
    bool initialized_ = false;
    std::size_t loaded_column_count_ = 0;
    std::unordered_set<int> loaded_fixed_column_ids_;
    ActiveConflictRows loaded_active_conflict_rows_;
    std::unordered_set<std::string> loaded_depot_gate_row_names_;

    void start_server() {
        if (started_) {
            return;
        }
        fs::create_directories(session_dir_);
        std::error_code ec;
        fs::remove(request_path_, ec);
        fs::remove(response_path_, ec);
        const fs::path script_path = resolve_tool_script_path("persistent_gurobi_master_session.py");
        if (!fs::exists(script_path)) {
            throw std::runtime_error("Persistent session script not found: " + script_path.string());
        }

#ifdef _WIN32
        std::vector<std::wstring> argv_storage = {
            fs::path(python_exe_.empty() ? "python" : python_exe_).wstring(),
            script_path.wstring(),
            L"--session-dir",
            session_dir_.wstring()
        };
        std::vector<const wchar_t*> argv;
        argv.reserve(argv_storage.size() + 1);
        for (const auto& arg : argv_storage) {
            argv.push_back(arg.c_str());
        }
        argv.push_back(nullptr);
        const intptr_t proc = _wspawnvp(_P_NOWAIT, argv_storage.front().c_str(), argv.data());
        if (proc == -1) {
            throw std::runtime_error("Failed to launch persistent Gurobi master session");
        }
#else
        std::string command = quote(python_exe_.empty() ? "python" : python_exe_)
            + " " + quote(script_path.string())
            + " --session-dir " + quote(session_dir_.string()) + " &";
        const int proc = std::system(command.c_str());
        if (proc != 0) {
            throw std::runtime_error("Failed to launch persistent Gurobi master session");
        }
#endif
        started_ = true;
    }

    MasterSolveResult initialize_and_solve(
        const std::vector<Column>& columns,
        const std::unordered_set<int>& fixed_column_ids,
        int master_time_limit_sec
    ) {
        std::ostringstream request;
        request << "{"
                << "\"command\":\"init_solve\","
                << "\"time_limit\":" << master_time_limit_sec << ","
                << "\"log_to_console\":" << (debug_ ? 1 : 0) << ",";
        append_master_model_json(request, instance_, columns, false, fixed_column_ids);
        request
                << "}";
        write_request_json(request.str());
        MasterSolveResult result = read_response_result();
        result.requested_solver = "GUROBI";
        result.actual_solver = "GUROBI_PERSISTENT";
        initialized_ = true;
        loaded_column_count_ = columns.size();
        loaded_fixed_column_ids_ = fixed_column_ids;
        loaded_active_conflict_rows_ = collect_active_conflict_rows(instance_, columns);
        loaded_depot_gate_row_names_ = collect_dynamic_row_names(build_incremental_depot_gate_rows(instance_, columns, 0));
        return result;
    }

    MasterSolveResult add_columns_and_solve(
        const std::vector<Column>& columns,
        const std::unordered_set<int>& fixed_column_ids,
        int master_time_limit_sec
    ) {
        const ActiveConflictRows current_active_conflict_rows = collect_active_conflict_rows(instance_, columns);
        const ActiveConflictRows added_conflict_rows =
            diff_active_conflict_rows(current_active_conflict_rows, loaded_active_conflict_rows_);
        const auto candidate_depot_rows = build_incremental_depot_gate_rows(instance_, columns, loaded_column_count_);
        std::vector<DynamicRowPayload> new_rows;
        std::vector<DynamicRowPayload> existing_depot_rows;
        new_rows.reserve(candidate_depot_rows.size());
        existing_depot_rows.reserve(candidate_depot_rows.size());
        for (const auto& row : candidate_depot_rows) {
            if (loaded_depot_gate_row_names_.count(row.row_name) != 0) {
                existing_depot_rows.push_back(row);
            } else {
                new_rows.push_back(row);
            }
        }
        const auto new_conflict_rows = build_incremental_conflict_rows(instance_, columns, added_conflict_rows);
        new_rows.insert(new_rows.end(), new_conflict_rows.begin(), new_conflict_rows.end());
        const auto new_variables = build_incremental_conflict_slack_variables(instance_, added_conflict_rows);
        const auto excluded_row_names = build_conflict_row_name_set(added_conflict_rows);
        const auto existing_depot_row_coeffs_by_var = build_extra_row_coeffs_by_var(existing_depot_rows);
        std::ostringstream request;
        request << "{"
                << "\"command\":\"add_columns_and_solve\","
                << "\"time_limit\":" << master_time_limit_sec << ","
                << "\"log_to_console\":" << (debug_ ? 1 : 0) << ","
                << "\"columns\":[";
        for (std::size_t index = loaded_column_count_; index < columns.size(); ++index) {
            if (index > loaded_column_count_) {
                request << ",";
            }
            const auto& column = columns[index];
            const auto row_coeffs = filter_incremental_column_row_coeffs(
                build_master_column_row_coeffs(instance_, column),
                excluded_row_names
            );
            auto augmented_row_coeffs = row_coeffs;
            const auto extra_it = existing_depot_row_coeffs_by_var.find(var_name_column(column.id));
            if (extra_it != existing_depot_row_coeffs_by_var.end()) {
                augmented_row_coeffs.insert(
                    augmented_row_coeffs.end(),
                    extra_it->second.begin(),
                    extra_it->second.end()
                );
            }
            request << "{"
                    << "\"var_name\":\"" << json_escape(var_name_column(column.id)) << "\","
                    << "\"cost\":" << format_coeff(column.cost) << ","
                    << "\"row_coeffs\":[";
            for (std::size_t coeff_index = 0; coeff_index < augmented_row_coeffs.size(); ++coeff_index) {
                if (coeff_index > 0) {
                    request << ",";
                }
                request << "{"
                        << "\"row_name\":\"" << json_escape(augmented_row_coeffs[coeff_index].row_name) << "\","
                        << "\"coeff\":" << format_coeff(augmented_row_coeffs[coeff_index].coeff)
                        << "}";
            }
            request << "]"
                    << "}";
        }
        request << "],"
                << "\"bound_updates\":[";
        bool first_bound_update = true;
        for (const int column_id : fixed_column_ids) {
            if (loaded_fixed_column_ids_.count(column_id) != 0) {
                continue;
            }
            if (!first_bound_update) {
                request << ",";
            }
            first_bound_update = false;
            request << "{"
                    << "\"var_name\":\"" << json_escape(var_name_column(column_id)) << "\","
                    << "\"lb\":1.0,"
                    << "\"ub\":1.0"
                    << "}";
        }
        request << "],"
                << "\"new_rows\":";
        append_dynamic_row_payloads_json(request, new_rows);
        request << ",\"new_variables\":";
        append_master_variable_payloads_json(request, new_variables);
        request
                << "}";
        write_request_json(request.str());
        MasterSolveResult result = read_response_result();
        result.requested_solver = "GUROBI";
        result.actual_solver = "GUROBI_PERSISTENT";
        loaded_column_count_ = columns.size();
        loaded_fixed_column_ids_ = fixed_column_ids;
        loaded_active_conflict_rows_ = current_active_conflict_rows;
        for (const auto& row : candidate_depot_rows) {
            loaded_depot_gate_row_names_.insert(row.row_name);
        }
        return result;
    }

    void write_request_json(const std::string& payload) {
        const fs::path tmp_path = request_path_.string() + ".tmp";
        {
            std::ofstream out(tmp_path);
            out << payload;
        }
        std::error_code ec;
        fs::remove(response_path_, ec);
        fs::rename(tmp_path, request_path_, ec);
        if (ec) {
            throw std::runtime_error("Failed to write persistent master request: " + ec.message());
        }
    }

    void wait_for_response(int timeout_ms) const {
        const auto start = std::chrono::steady_clock::now();
        while (!fs::exists(response_path_)) {
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - start
            ).count();
            if (elapsed > timeout_ms) {
                throw std::runtime_error("Timed out waiting for persistent master response");
            }
        }
    }

    MasterSolveResult read_response_result() {
        wait_for_response(3600000);
        MasterSolveResult result = parse_gurobi_json_solution(response_path_);
        std::error_code ec;
        fs::remove(response_path_, ec);
        if (!result.ok) {
            throw std::runtime_error("Persistent Gurobi master solve failed: " + result.status);
        }
        return result;
    }
};

class PersistentCoinMPMasterSession {
public:
    PersistentCoinMPMasterSession(
        const Instance& instance,
        fs::path session_dir,
        std::string python_exe,
        bool debug
    ) : instance_(instance),
        session_dir_(std::move(session_dir)),
        python_exe_(std::move(python_exe)),
        debug_(debug) {
        request_path_ = session_dir_ / "request.json";
        response_path_ = session_dir_ / "response.json";
    }

    ~PersistentCoinMPMasterSession() {
        shutdown();
    }

    MasterSolveResult solve(
        const std::vector<Column>& columns,
        const std::unordered_set<int>& fixed_column_ids,
        int master_time_limit_sec
    ) {
        start_server();
        if (!initialized_) {
            return initialize_and_solve(columns, fixed_column_ids, master_time_limit_sec);
        }
        if (columns.size() < loaded_column_count_) {
            throw std::runtime_error("Persistent CoinMP master column count is inconsistent");
        }
        return add_columns_and_solve(columns, fixed_column_ids, master_time_limit_sec);
    }

    void shutdown() {
        if (!started_) {
            return;
        }
        try {
            write_request_json("{\"command\":\"shutdown\"}");
            wait_for_response(5000);
        } catch (...) {
        }
        std::error_code ec;
        fs::remove(request_path_, ec);
        fs::remove(response_path_, ec);
        started_ = false;
        initialized_ = false;
        loaded_column_count_ = 0;
        loaded_fixed_column_ids_.clear();
        loaded_active_conflict_rows_ = {};
        loaded_depot_gate_row_names_.clear();
    }

private:
    const Instance& instance_;
    fs::path session_dir_;
    fs::path request_path_;
    fs::path response_path_;
    std::string python_exe_;
    bool debug_ = false;
    bool started_ = false;
    bool initialized_ = false;
    std::size_t loaded_column_count_ = 0;
    std::unordered_set<int> loaded_fixed_column_ids_;
    ActiveConflictRows loaded_active_conflict_rows_;
    std::unordered_set<std::string> loaded_depot_gate_row_names_;

    void start_server() {
        if (started_) {
            return;
        }
        fs::create_directories(session_dir_);
        std::error_code ec;
        fs::remove(request_path_, ec);
        fs::remove(response_path_, ec);
        const fs::path script_path = resolve_tool_script_path("persistent_coinmp_master_session.py");
        if (!fs::exists(script_path)) {
            throw std::runtime_error("Persistent CoinMP session script not found: " + script_path.string());
        }

#ifdef _WIN32
        std::vector<std::wstring> argv_storage = {
            fs::path(python_exe_.empty() ? "python" : python_exe_).wstring(),
            script_path.wstring(),
            L"--session-dir",
            session_dir_.wstring()
        };
        std::vector<const wchar_t*> argv;
        argv.reserve(argv_storage.size() + 1);
        for (const auto& arg : argv_storage) {
            argv.push_back(arg.c_str());
        }
        argv.push_back(nullptr);
        const intptr_t proc = _wspawnvp(_P_NOWAIT, argv_storage.front().c_str(), argv.data());
        if (proc == -1) {
            throw std::runtime_error("Failed to launch persistent CoinMP master session");
        }
#else
        std::string command = quote(python_exe_.empty() ? "python" : python_exe_)
            + " " + quote(script_path.string())
            + " --session-dir " + quote(session_dir_.string()) + " &";
        const int proc = std::system(command.c_str());
        if (proc != 0) {
            throw std::runtime_error("Failed to launch persistent CoinMP master session");
        }
#endif
        started_ = true;
    }

    MasterSolveResult initialize_and_solve(
        const std::vector<Column>& columns,
        const std::unordered_set<int>& fixed_column_ids,
        int master_time_limit_sec
    ) {
        std::ostringstream request;
        request << "{"
                << "\"command\":\"init_solve\","
                << "\"time_limit\":" << master_time_limit_sec << ","
                << "\"log_to_console\":" << (debug_ ? 1 : 0) << ",";
        append_master_model_json(request, instance_, columns, false, fixed_column_ids);
        request << "}";
        write_request_json(request.str());
        MasterSolveResult result = read_response_result();
        result.requested_solver = "CBC";
        result.actual_solver = "CBC_PERSISTENT";
        initialized_ = true;
        loaded_column_count_ = columns.size();
        loaded_fixed_column_ids_ = fixed_column_ids;
        loaded_active_conflict_rows_ = collect_active_conflict_rows(instance_, columns);
        loaded_depot_gate_row_names_ = collect_dynamic_row_names(build_incremental_depot_gate_rows(instance_, columns, 0));
        return result;
    }

    MasterSolveResult add_columns_and_solve(
        const std::vector<Column>& columns,
        const std::unordered_set<int>& fixed_column_ids,
        int master_time_limit_sec
    ) {
        const ActiveConflictRows current_active_conflict_rows = collect_active_conflict_rows(instance_, columns);
        const ActiveConflictRows added_conflict_rows =
            diff_active_conflict_rows(current_active_conflict_rows, loaded_active_conflict_rows_);
        const auto candidate_depot_rows = build_incremental_depot_gate_rows(instance_, columns, loaded_column_count_);
        std::vector<DynamicRowPayload> new_rows;
        std::vector<DynamicRowPayload> existing_depot_rows;
        new_rows.reserve(candidate_depot_rows.size());
        existing_depot_rows.reserve(candidate_depot_rows.size());
        for (const auto& row : candidate_depot_rows) {
            if (loaded_depot_gate_row_names_.count(row.row_name) != 0) {
                existing_depot_rows.push_back(row);
            } else {
                new_rows.push_back(row);
            }
        }
        const auto new_conflict_rows = build_incremental_conflict_rows(instance_, columns, added_conflict_rows);
        new_rows.insert(new_rows.end(), new_conflict_rows.begin(), new_conflict_rows.end());
        const auto new_variables = build_incremental_conflict_slack_variables(instance_, added_conflict_rows);
        const auto excluded_row_names = build_conflict_row_name_set(added_conflict_rows);
        const auto existing_depot_row_coeffs_by_var = build_extra_row_coeffs_by_var(existing_depot_rows);
        std::ostringstream request;
        request << "{"
                << "\"command\":\"add_columns_and_solve\","
                << "\"time_limit\":" << master_time_limit_sec << ","
                << "\"log_to_console\":" << (debug_ ? 1 : 0) << ","
                << "\"columns\":[";
        for (std::size_t index = loaded_column_count_; index < columns.size(); ++index) {
            if (index > loaded_column_count_) {
                request << ",";
            }
            const auto& column = columns[index];
            const auto row_coeffs = filter_incremental_column_row_coeffs(
                build_master_column_row_coeffs(instance_, column),
                excluded_row_names
            );
            auto augmented_row_coeffs = row_coeffs;
            const auto extra_it = existing_depot_row_coeffs_by_var.find(var_name_column(column.id));
            if (extra_it != existing_depot_row_coeffs_by_var.end()) {
                augmented_row_coeffs.insert(
                    augmented_row_coeffs.end(),
                    extra_it->second.begin(),
                    extra_it->second.end()
                );
            }
            request << "{"
                    << "\"var_name\":\"" << json_escape(var_name_column(column.id)) << "\","
                    << "\"cost\":" << format_coeff(column.cost) << ","
                    << "\"lb\":0.0,"
                    << "\"ub\":1.0,"
                    << "\"vtype\":\"C\","
                    << "\"row_coeffs\":[";
            for (std::size_t coeff_index = 0; coeff_index < augmented_row_coeffs.size(); ++coeff_index) {
                if (coeff_index > 0) {
                    request << ",";
                }
                request << "{"
                        << "\"row_name\":\"" << json_escape(augmented_row_coeffs[coeff_index].row_name) << "\","
                        << "\"coeff\":" << format_coeff(augmented_row_coeffs[coeff_index].coeff)
                        << "}";
            }
            request << "]"
                    << "}";
        }
        request << "],"
                << "\"bound_updates\":[";
        bool first_bound_update = true;
        for (const int column_id : fixed_column_ids) {
            if (loaded_fixed_column_ids_.count(column_id) != 0) {
                continue;
            }
            if (!first_bound_update) {
                request << ",";
            }
            first_bound_update = false;
            request << "{"
                    << "\"var_name\":\"" << json_escape(var_name_column(column_id)) << "\","
                    << "\"lb\":1.0,"
                    << "\"ub\":1.0"
                    << "}";
        }
        request << "],"
                << "\"new_rows\":";
        append_dynamic_row_payloads_json(request, new_rows);
        request << ",\"new_variables\":";
        append_master_variable_payloads_json(request, new_variables);
        request
                << "}";
        write_request_json(request.str());
        MasterSolveResult result = read_response_result();
        result.requested_solver = "CBC";
        result.actual_solver = "CBC_PERSISTENT";
        loaded_column_count_ = columns.size();
        loaded_fixed_column_ids_ = fixed_column_ids;
        loaded_active_conflict_rows_ = current_active_conflict_rows;
        for (const auto& row : candidate_depot_rows) {
            loaded_depot_gate_row_names_.insert(row.row_name);
        }
        return result;
    }

    void write_request_json(const std::string& payload) {
        const fs::path tmp_path = request_path_.string() + ".tmp";
        {
            std::ofstream out(tmp_path);
            out << payload;
        }
        std::error_code ec;
        fs::remove(response_path_, ec);
        fs::rename(tmp_path, request_path_, ec);
        if (ec) {
            throw std::runtime_error("Failed to write persistent CoinMP master request: " + ec.message());
        }
    }

    void wait_for_response(int timeout_ms) const {
        const auto start = std::chrono::steady_clock::now();
        while (!fs::exists(response_path_)) {
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - start
            ).count();
            if (elapsed > timeout_ms) {
                throw std::runtime_error("Timed out waiting for persistent CoinMP master response");
            }
        }
    }

    MasterSolveResult read_response_result() {
        wait_for_response(3600000);
        MasterSolveResult result = parse_gurobi_json_solution(response_path_);
        std::error_code ec;
        fs::remove(response_path_, ec);
        if (!result.ok) {
            throw std::runtime_error("Persistent CoinMP master solve failed: " + result.status);
        }
        return result;
    }
};

MasterSolveResult solve_master_with_coinmp(
    const Instance& instance,
    const std::vector<Column>& columns,
    bool integer_master,
    const std::unordered_set<int>& fixed_column_ids,
    const fs::path& work_dir,
    const std::string& python_exe,
    int master_time_limit_sec,
    double mip_gap,
    const std::string& tag,
    bool debug
) {
    fs::create_directories(work_dir);
    const fs::path model_json_path = work_dir / (tag + "_model.json");
    const fs::path json_sol_path = work_dir / (tag + "_sol.json");
    std::error_code ec;
    fs::remove(json_sol_path, ec);
    write_master_model_json(instance, columns, integer_master, fixed_column_ids, model_json_path);

    const fs::path script_path = resolve_tool_script_path("solve_master_with_coinmp.py");
    if (!fs::exists(script_path)) {
        throw std::runtime_error("CoinMP bridge script not found: " + script_path.string());
    }

#ifdef _WIN32
    std::vector<std::wstring> argv_storage = {
        fs::path(python_exe.empty() ? "python" : python_exe).wstring(),
        script_path.wstring(),
        L"--model-json",
        model_json_path.wstring(),
        L"--out-json",
        json_sol_path.wstring(),
        L"--integer",
        std::to_wstring(integer_master ? 1 : 0),
        L"--time-limit",
        std::to_wstring(master_time_limit_sec),
        L"--mip-gap",
        fs::path(format_coeff(mip_gap)).wstring(),
        L"--log-to-console",
        std::to_wstring(debug ? 1 : 0)
    };
    std::vector<const wchar_t*> argv;
    argv.reserve(argv_storage.size() + 1);
    for (const auto& arg : argv_storage) {
        argv.push_back(arg.c_str());
    }
    argv.push_back(nullptr);
    if (debug) {
        std::cout << "[debug] CoinMP(Python) argv:";
        for (const auto& arg : argv_storage) {
            std::cout << " [" << fs::path(arg).string() << "]";
        }
        std::cout << "\n";
    }
    const intptr_t exit_code = _wspawnvp(_P_WAIT, argv_storage.front().c_str(), argv.data());
#else
    std::string command = quote(python_exe.empty() ? "python" : python_exe)
        + " " + quote(script_path.string())
        + " --model-json " + quote(model_json_path.string())
        + " --out-json " + quote(json_sol_path.string())
        + " --integer " + std::to_string(integer_master ? 1 : 0)
        + " --time-limit " + std::to_string(master_time_limit_sec)
        + " --mip-gap " + format_coeff(mip_gap)
        + " --log-to-console " + std::to_string(debug ? 1 : 0);
    const int exit_code = std::system(command.c_str());
#endif
    if (!fs::exists(json_sol_path)) {
        throw std::runtime_error("CoinMP bridge did not produce solution file for " + tag);
    }
    auto result = parse_gurobi_json_solution(json_sol_path);
    if (!result.ok) {
        throw std::runtime_error("CoinMP bridge solve failed for " + tag + ": " + result.status);
    }
    if (exit_code != 0) {
        throw std::runtime_error("CoinMP bridge exited with code " + std::to_string(static_cast<int>(exit_code))
                                 + " for " + tag + ": " + result.status);
    }
    result.actual_solver = "CBC_COINMP";
    return result;
}

MasterSolveResult solve_master_with_gurobi(
    const Instance& instance,
    const std::vector<Column>& columns,
    bool integer_master,
    const std::unordered_set<int>& fixed_column_ids,
    const fs::path& work_dir,
    const std::string& python_exe,
    const std::string& gurobi_path,
    int master_time_limit_sec,
    double mip_gap,
    const std::string& tag,
    bool debug
) {
    fs::create_directories(work_dir);
    const fs::path json_sol_path = work_dir / (tag + "_sol.json");
    const fs::path model_json_path = work_dir / (tag + "_model.json");
    std::error_code ec;
    fs::remove(json_sol_path, ec);
    fs::remove(work_dir / (tag + ".sol"), ec);

    const fs::path script_path = resolve_tool_script_path("solve_master_with_gurobi.py");
    if (gurobi_path.empty() && fs::exists(script_path)) {
        write_master_model_json(instance, columns, integer_master, fixed_column_ids, model_json_path);
#ifdef _WIN32
        std::vector<std::wstring> argv_storage = {
            fs::path(python_exe.empty() ? "python" : python_exe).wstring(),
            script_path.wstring(),
            L"--model-json",
            model_json_path.wstring(),
            L"--out-json",
            json_sol_path.wstring(),
            L"--integer",
            std::to_wstring(integer_master ? 1 : 0),
            L"--time-limit",
            std::to_wstring(master_time_limit_sec),
            L"--mip-gap",
            fs::path(format_coeff(mip_gap)).wstring(),
            L"--log-to-console",
            std::to_wstring(debug ? 1 : 0)
        };
        std::vector<const wchar_t*> argv;
        argv.reserve(argv_storage.size() + 1);
        for (const auto& arg : argv_storage) {
            argv.push_back(arg.c_str());
        }
        argv.push_back(nullptr);
        if (debug) {
            std::cout << "[debug] Gurobi(Python) argv:";
            for (const auto& arg : argv_storage) {
                std::cout << " [" << fs::path(arg).string() << "]";
            }
            std::cout << "\n";
        }
        const intptr_t exit_code = _wspawnvp(_P_WAIT, argv_storage.front().c_str(), argv.data());
#else
        std::string command = quote(python_exe.empty() ? "python" : python_exe)
            + " " + quote(script_path.string())
            + " --model-json " + quote(model_json_path.string())
            + " --out-json " + quote(json_sol_path.string())
            + " --integer " + std::to_string(integer_master ? 1 : 0)
            + " --time-limit " + std::to_string(master_time_limit_sec)
            + " --mip-gap " + format_coeff(mip_gap)
            + " --log-to-console " + std::to_string(debug ? 1 : 0);
        const int exit_code = std::system(command.c_str());
#endif
        if (fs::exists(json_sol_path)) {
            auto result = parse_gurobi_json_solution(json_sol_path);
            if (exit_code == 0 && result.ok) {
                result.actual_solver = "GUROBI";
                return result;
            }
            if (!result.ok) {
                throw std::runtime_error("Gurobi(Python) solve failed for " + tag + ": " + result.status);
            }
            throw std::runtime_error("Gurobi(Python) exited with code " + std::to_string(static_cast<int>(exit_code))
                                     + " for " + tag + ": " + result.status);
        }
        if (debug) {
            std::cout << "[debug] Gurobi(Python) bridge failed for " << tag << ", trying CLI fallback if available\n";
        }
    }

    if (!gurobi_path.empty()) {
        const fs::path lp_path = work_dir / (tag + ".lp");
        write_master_lp(instance, columns, integer_master, fixed_column_ids, lp_path);
#ifdef _WIN32
        std::vector<std::string> argv_storage = {
            gurobi_path,
            "JSONSolDetail=1",
            "ResultFile=" + json_sol_path.string()
        };
        if (integer_master) {
            argv_storage.push_back("TimeLimit=" + std::to_string(master_time_limit_sec));
            argv_storage.push_back("MIPGap=" + format_coeff(mip_gap));
        }
        if (!debug) {
            argv_storage.push_back("LogToConsole=0");
        }
        argv_storage.push_back(lp_path.string());
        std::vector<const char*> argv;
        argv.reserve(argv_storage.size() + 1);
        for (const auto& arg : argv_storage) {
            argv.push_back(arg.c_str());
        }
        argv.push_back(nullptr);
        const intptr_t exit_code = _spawnvp(_P_WAIT, argv_storage.front().c_str(), argv.data());
#else
        std::string command = quote(gurobi_path) + " JSONSolDetail=1" + " ResultFile=" + quote(json_sol_path.string());
        if (integer_master) {
            command += " TimeLimit=" + std::to_string(master_time_limit_sec) + " MIPGap=" + format_coeff(mip_gap);
        }
        if (!debug) {
            command += " LogToConsole=0";
        }
        command += " " + quote(lp_path.string());
        const int exit_code = std::system(command.c_str());
#endif
        if (fs::exists(json_sol_path)) {
            auto result = parse_gurobi_json_solution(json_sol_path);
            if (!result.ok) {
                throw std::runtime_error("Gurobi(CLI) solve failed for " + tag + ": " + result.status);
            }
            result.actual_solver = "GUROBI";
            return result;
        }
    }

    throw std::runtime_error("Gurobi did not produce solution file for " + tag);
}

// ---------- Unified solver dispatch ----------

MasterSolveResult solve_master(
    const Instance& instance,
    const std::vector<Column>& columns,
    bool integer_master,
    const std::unordered_set<int>& fixed_column_ids,
    const fs::path& work_dir,
    const std::string& cbc_path,
    const std::string& python_exe,
    const std::string& gurobi_path,
    const std::string& solver,
    int master_time_limit_sec,
    double mip_gap,
    const std::string& tag,
    bool debug
) {
    if (solver == "GUROBI") {
        try {
            auto result = solve_master_with_gurobi(instance, columns, integer_master, fixed_column_ids, work_dir,
                                                   python_exe, gurobi_path, master_time_limit_sec, mip_gap,
                                                   tag, debug);
            result.requested_solver = "GUROBI";
            if (result.actual_solver.empty()) {
                result.actual_solver = "GUROBI";
            }
            return result;
        } catch (const std::exception& e) {
            std::cout << "[warn] Gurobi failed (" << e.what() << "), falling back to CBC\n";
            auto result = solve_master_with_cbc(instance, columns, integer_master, fixed_column_ids, work_dir,
                                                cbc_path, python_exe, master_time_limit_sec, mip_gap,
                                                tag, debug);
            result.requested_solver = "GUROBI";
            result.fallback_used = true;
            result.fallback_reason = e.what();
            if (result.actual_solver.empty()) {
                result.actual_solver = "CBC";
            }
            return result;
        }
    }
    auto result = solve_master_with_cbc(instance, columns, integer_master, fixed_column_ids, work_dir,
                                        cbc_path, python_exe, master_time_limit_sec, mip_gap,
                                        tag, debug);
    result.requested_solver = solver.empty() ? "CBC" : solver;
    if (result.actual_solver.empty()) {
        result.actual_solver = "CBC";
    }
    return result;
}

std::unordered_map<std::string, double> stabilize_row_duals(
    const std::unordered_map<std::string, double>& raw_duals,
    const std::unordered_map<std::string, double>& dual_center,
    const Config& config
) {
    if (!config.enable_dual_stabilization || dual_center.empty()) {
        return raw_duals;
    }

    std::unordered_map<std::string, double> stabilized = raw_duals;
    for (const auto& [row_name, center_value] : dual_center) {
        const double raw_value = get_value_or_zero(raw_duals, row_name);
        double stabilized_value =
            config.dual_stabilization_alpha * raw_value +
            (1.0 - config.dual_stabilization_alpha) * center_value;
        if (config.enable_dual_box) {
            const double radius = std::max(
                config.dual_box_abs,
                config.dual_box_rel * std::max(1.0, std::fabs(center_value))
            );
            stabilized_value = std::clamp(
                stabilized_value,
                center_value - radius,
                center_value + radius
            );
        }
        stabilized[row_name] = stabilized_value;
    }
    return stabilized;
}

int effective_pricing_batch_size(const Config& config, const std::vector<IterationLog>& logs) {
    const int base_batch = std::max(1, config.pricing_batch_size);
    if (!config.enable_adaptive_pricing_batch || logs.empty()) {
        return base_batch;
    }

    const int min_batch = std::max(1, std::min(config.min_pricing_batch_size, base_batch));
    const IterationLog& last_log = logs.back();
    const double abs_rc = std::fabs(last_log.best_reduced_cost);
    int batch = base_batch;

    if (last_log.active_columns >= 5000 && abs_rc < 3.0e7) {
        batch = std::min(batch, std::max(min_batch, base_batch / 2));
    }
    if (abs_rc < 2.0e7) {
        batch = std::min(batch, std::max(min_batch, base_batch / 2));
    }
    if (abs_rc < 1.0e7) {
        batch = std::min(batch, std::max(min_batch, base_batch / 4));
    }
    if (abs_rc < 5.0e6) {
        batch = std::min(batch, std::max(min_batch, base_batch / 8));
    }

    return std::max(min_batch, batch);
}

ColumnPruneStats prune_inactive_columns(
    std::vector<Column>& columns,
    const std::unordered_map<std::string, double>& primal_values,
    int iteration,
    const Config& config
) {
    ColumnPruneStats stats;
    if (!config.enable_column_pool_pruning || static_cast<int>(columns.size()) <= config.column_prune_trigger) {
        stats.pool_size_after = static_cast<int>(columns.size());
        return stats;
    }

    std::vector<Column> kept_columns;
    kept_columns.reserve(columns.size());
    const double active_epsilon = config.basis_activity_epsilon;
    for (auto& column : columns) {
        const double value = get_value_or_zero(primal_values, var_name_column(column.id));
        const bool is_active = value > active_epsilon;
        if (is_active) {
            column.inactive_iterations = 0;
            column.last_active_iteration = iteration;
        } else {
            ++column.inactive_iterations;
        }
        const int age = std::max(0, iteration - column.birth_iteration);
        const bool protect_recent = age < config.column_recent_protection;
        const bool prune_candidate =
            !column.is_legacy_seed &&
            !is_active &&
            !protect_recent &&
            age >= config.column_min_age &&
            column.inactive_iterations >= config.column_inactive_iterations;

        if (column.is_legacy_seed) {
            ++stats.kept_legacy_seed;
        } else if (is_active) {
            ++stats.kept_active;
        } else if (protect_recent) {
            ++stats.kept_recent;
        }

        if (prune_candidate) {
            ++stats.pruned_columns;
            continue;
        }
        kept_columns.push_back(std::move(column));
    }

    columns = std::move(kept_columns);
    stats.pool_size_after = static_cast<int>(columns.size());
    return stats;
}

PricingResult price_columns(
    const Instance& instance,
    const std::unordered_map<std::string, double>& row_duals,
    const std::unordered_map<std::string, double>& primal_values,
    const std::vector<Column>& columns,
    const std::unordered_set<std::string>& existing_keys,
    int next_column_id,
    int batch_size,
    const Config& config
) {
    PricingResult result;
    result.diagnostics.option_node_count = static_cast<int>(instance.options.size());
    result.diagnostics.arc_count = static_cast<int>(instance.arcs.size());
    result.diagnostics.depot_source_arc_count = static_cast<int>(instance.depot_source_arcs.size());
    result.diagnostics.depot_sink_arc_count = static_cast<int>(instance.depot_sink_arcs.size());
    const BasisNeighborhood neighborhood = build_basis_neighborhood(
        columns,
        primal_values,
        config.basis_activity_epsilon
    );
    const auto option_activity = compute_option_activity(columns, primal_values, config.basis_activity_epsilon);
    std::unordered_map<int, double> node_weight;
    std::unordered_map<int, double> arc_weight;
    std::unordered_map<int, double> cover_dual_by_slot;
    std::unordered_map<int, double> lhs_dual_by_slot;
    std::unordered_map<int, double> rhs_dual_by_slot;
    std::unordered_map<int, double> first_car_dual_by_option;
    std::unordered_map<int, double> option_conflict_dual_by_option;
    std::unordered_map<int, double> option_conflict_arc_relief_dual_by_arc;
    std::unordered_map<int, double> conflict_dual_by_event;
    std::unordered_map<std::uint64_t, double> peak_dual_by_mask;
    const double vehicle_cap_dual =
        instance.max_vehicle_count > 0
        ? get_value_or_zero(row_duals, row_name_vehicle_cap())
        : 0.0;

    for (const auto& slot : instance.slots) {
        cover_dual_by_slot[slot.id] = get_value_or_zero(row_duals, row_name_cover(slot.id));
    }
    for (const auto& peak : instance.peaks) {
        peak_dual_by_mask[peak.bit_mask] = get_value_or_zero(row_duals, row_name_peak_cap(peak.id));
    }

    std::unordered_map<std::uint64_t, double> peak_xr0_dual_by_mask;
    std::unordered_map<std::uint64_t, double> peak_xr1_dual_by_mask;
    for (const auto& peak : instance.peaks) {
        if (peak.train_num1 > 0) {
            peak_xr0_dual_by_mask[peak.bit_mask] = get_value_or_zero(row_duals, row_name_peak_cap_xr0(peak.id));
        }
        if (peak.train_num2 > 0) {
            peak_xr1_dual_by_mask[peak.bit_mask] = get_value_or_zero(row_duals, row_name_peak_cap_xr1(peak.id));
        }
    }
    for (const auto& target : instance.first_car_targets) {
        const double dual = get_value_or_zero(row_duals, row_name_first_car(target.id));
        for (const int option_id : target.valid_option_ids) {
            first_car_dual_by_option[option_id] += dual;
        }
    }
    for (const auto& headway : instance.headways) {
        const double dual_sum =
            get_value_or_zero(row_duals, row_name_headway_lb(headway.id)) +
            get_value_or_zero(row_duals, row_name_headway_ub(headway.id)) +
            get_value_or_zero(row_duals, row_name_headway_target(headway.id));
        lhs_dual_by_slot[headway.lhs_slot_id] += dual_sum;
        rhs_dual_by_slot[headway.rhs_slot_id] += dual_sum;
    }
    for (const auto& conflict : instance.option_conflicts) {
        const double dual = get_value_or_zero(row_duals, row_name_option_conflict(conflict.id));
        option_conflict_dual_by_option[conflict.option_a] += dual;
        option_conflict_dual_by_option[conflict.option_b] += dual;
        const auto forward_arc = instance.arc_lookup.find(pair_key(conflict.option_a, conflict.option_b));
        if (forward_arc != instance.arc_lookup.end()) {
            option_conflict_arc_relief_dual_by_arc[forward_arc->second] += dual;
        }
        const auto backward_arc = instance.arc_lookup.find(pair_key(conflict.option_b, conflict.option_a));
        if (backward_arc != instance.arc_lookup.end()) {
            option_conflict_arc_relief_dual_by_arc[backward_arc->second] += dual;
        }
    }
    for (const auto& row_dual : row_duals) {
        if (!starts_with(row_dual.first, "R_conflict_") || std::fabs(row_dual.second) <= kEps) {
            continue;
        }
        int conflict_id = -1;
        try {
            conflict_id = std::stoi(row_dual.first.substr(std::string("R_conflict_").size()));
        } catch (...) {
            continue;
        }
        const auto conflict_it = instance.conflict_by_id.find(conflict_id);
        if (conflict_it == instance.conflict_by_id.end()) {
            continue;
        }
        conflict_dual_by_event[conflict_it->second.event_a] += row_dual.second;
        conflict_dual_by_event[conflict_it->second.event_b] += row_dual.second;
    }

    for (const auto& option : instance.options) {
        double weight = option_base_cost(option);
        weight -= cover_dual_by_slot[option.slot_id];
        weight += static_cast<double>(option.headway_departure) * (lhs_dual_by_slot[option.slot_id] - rhs_dual_by_slot[option.slot_id]);
        weight -= first_car_dual_by_option[option.id];
        weight -= option_conflict_dual_by_option[option.id];
        if (option.peak_mask != 0) {
            if (option.xroad == 0) {
                weight -= get_value_or_zero(peak_xr0_dual_by_mask, option.peak_mask);
            } else {
                weight -= get_value_or_zero(peak_xr1_dual_by_mask, option.peak_mask);
            }
        }
        if (config.enable_tabu_pricing) {
            weight += config.tabu_option_penalty * get_value_or_zero(neighborhood.option_activity, option.id);
        }
        node_weight[option.id] = weight;
    }
    for (const auto& arc : instance.arcs) {
        double weight = arc.arc_cost;
        weight += option_conflict_arc_relief_dual_by_arc[arc.id];
        if (arc.event_id >= 0) {
            weight -= conflict_dual_by_event[arc.event_id];
        }
        if (config.enable_tabu_pricing) {
            weight += config.tabu_arc_penalty * get_value_or_zero(neighborhood.arc_activity, arc.id);
            if (arc.event_id >= 0) {
                weight += config.tabu_event_penalty * get_value_or_zero(neighborhood.event_activity, arc.event_id);
            }
        }
        arc_weight[arc.id] = weight;
    }

    struct HeuristicCandidate {
        double reduced_cost = 0.0;
        Column column;
    };
    std::vector<HeuristicCandidate> heuristic_candidates;
    const auto representative_option_ids = select_representative_options(instance, &option_activity);
    const auto path_cover_sequences = build_path_cover_sequences(instance, representative_option_ids);
    auto heuristic_columns = build_columns_from_sequences(instance, path_cover_sequences, existing_keys, next_column_id);
    heuristic_candidates.reserve(heuristic_columns.size());
    for (auto& column : heuristic_columns) {
        const double reduced_cost = compute_column_reduced_cost(instance, column, row_duals);
        if (reduced_cost >= -1e-6) {
            continue;
        }
        heuristic_candidates.push_back({reduced_cost, std::move(column)});
    }
    std::sort(heuristic_candidates.begin(), heuristic_candidates.end(), [](const HeuristicCandidate& lhs, const HeuristicCandidate& rhs) {
        if (lhs.reduced_cost != rhs.reduced_cost) {
            return lhs.reduced_cost < rhs.reduced_cost;
        }
        if (lhs.column.option_ids.size() != rhs.column.option_ids.size()) {
            return lhs.column.option_ids.size() > rhs.column.option_ids.size();
        }
        return lhs.column.key < rhs.column.key;
    });
    result.diagnostics.heuristic_candidate_count = static_cast<int>(heuristic_candidates.size());

    std::unordered_set<std::string> seen_in_batch;
    std::vector<Column> priced_columns;
    const int heuristic_quota = std::max(1, batch_size / 4);
    for (auto& candidate : heuristic_candidates) {
        if (seen_in_batch.count(candidate.column.key) != 0) {
            continue;
        }
        seen_in_batch.insert(candidate.column.key);
        priced_columns.push_back(std::move(candidate.column));
        if (static_cast<int>(priced_columns.size()) >= heuristic_quota) {
            break;
        }
    }

    auto peak_dual_for_bits = [&](std::uint64_t peak_mask) -> double {
        double total = 0.0;
        std::uint64_t remaining = peak_mask;
        while (remaining != 0) {
            const std::uint64_t bit = remaining & (~remaining + 1);
            total += get_value_or_zero(peak_dual_by_mask, bit);
            remaining &= (remaining - 1);
        }
        return total;
    };

    struct LabelState {
        int option_id = -1;
        std::uint64_t peak_mask = 0;

        bool operator==(const LabelState& other) const {
            return option_id == other.option_id && peak_mask == other.peak_mask;
        }
    };

    struct LabelStateHash {
        std::size_t operator()(const LabelState& state) const {
            const std::size_t lhs = std::hash<int>{}(state.option_id);
            const std::size_t rhs = std::hash<std::uint64_t>{}(state.peak_mask);
            return lhs ^ (rhs + 0x9e3779b97f4a7c15ULL + (lhs << 6) + (lhs >> 2));
        }
    };

    struct PricingLabel {
        double cost = 0.0;
        int option_id = -1;
        std::uint64_t peak_mask = 0;
        int parent_label = -1;
    };

    std::vector<PricingLabel> labels;
    std::unordered_map<int, std::vector<int>> labels_by_option;
    std::unordered_map<LabelState, int, LabelStateHash> best_label_by_state;

    auto add_or_relax_label = [&](int option_id, std::uint64_t peak_mask, double cost, int parent_label) -> void {
        const LabelState state{option_id, peak_mask};
        const auto existing = best_label_by_state.find(state);
        if (existing != best_label_by_state.end()) {
            PricingLabel& label = labels[existing->second];
            if (cost + kEps < label.cost) {
                label.cost = cost;
                label.parent_label = parent_label;
            }
            return;
        }
        const int label_index = static_cast<int>(labels.size());
        labels.push_back({cost, option_id, peak_mask, parent_label});
        best_label_by_state.emplace(state, label_index);
        labels_by_option[option_id].push_back(label_index);
    };

    // Explicit depot source/sink arc costs per terminal option.
    std::unordered_map<int, double> depot_out_cost_by_option;
    std::unordered_map<int, double> depot_in_cost_by_option;
    for (const auto& source_arc : instance.depot_source_arcs) {
        depot_out_cost_by_option[source_arc.option_id] = source_arc.arc_cost;
    }
    for (const auto& sink_arc : instance.depot_sink_arcs) {
        depot_in_cost_by_option[sink_arc.option_id] = sink_arc.arc_cost;
    }

    for (const auto& option : instance.options) {
        const std::uint64_t peak_mask = option.peak_mask;
        const double depot_out_cost = get_value_or_zero(depot_out_cost_by_option, option.id);
        const double start_cost =
            static_cast<double>(instance.vehicle_cost) - vehicle_cap_dual +
            node_weight[option.id] + depot_out_cost -
            peak_dual_for_bits(peak_mask);
        add_or_relax_label(option.id, peak_mask, start_cost, -1);
    }

    for (const auto& option : instance.options) {
        const auto labels_it = labels_by_option.find(option.id);
        if (labels_it == labels_by_option.end()) {
            continue;
        }
        const std::vector<int> current_label_indices = labels_it->second;
        const auto out_it = instance.outgoing_arcs_by_option.find(option.id);
        if (out_it == instance.outgoing_arcs_by_option.end()) {
            continue;
        }
        for (const int label_index : current_label_indices) {
            const PricingLabel current = labels[label_index];
            if (!std::isfinite(current.cost)) {
                continue;
            }
            for (const int arc_id : out_it->second) {
                const auto& arc = instance.arc_by_id.at(arc_id);
                const auto& next_option = instance.option_by_id.at(arc.to_option_id);
                const std::uint64_t new_peak_mask = current.peak_mask | next_option.peak_mask;
                const std::uint64_t new_bits = new_peak_mask ^ current.peak_mask;
                const double candidate_cost =
                    current.cost +
                    arc_weight[arc_id] +
                    node_weight[next_option.id] -
                    peak_dual_for_bits(new_bits);
                add_or_relax_label(next_option.id, new_peak_mask, candidate_cost, label_index);
            }
        }
    }

    struct LabelCandidate {
        double reduced_cost = 0.0;
        int label_index = -1;
    };
    std::vector<LabelCandidate> label_candidates;
    label_candidates.reserve(labels.size());
    for (int index = 0; index < static_cast<int>(labels.size()); ++index) {
        // Add depot_in cost for the terminal option of this label
        const double depot_in_cost = get_value_or_zero(depot_in_cost_by_option, labels[index].option_id);
        const double terminal_cost = labels[index].cost + depot_in_cost;
        if (terminal_cost < -1e-6) {
            label_candidates.push_back({terminal_cost, index});
        }
    }
    result.diagnostics.label_state_count = static_cast<int>(labels.size());
    result.diagnostics.label_candidate_count = static_cast<int>(label_candidates.size());
    std::sort(label_candidates.begin(), label_candidates.end(), [](const LabelCandidate& lhs, const LabelCandidate& rhs) {
        if (lhs.reduced_cost != rhs.reduced_cost) {
            return lhs.reduced_cost < rhs.reduced_cost;
        }
        return lhs.label_index < rhs.label_index;
    });

    auto reconstruct_label_sequence = [&](int label_index) -> std::vector<int> {
        std::vector<int> sequence;
        int current = label_index;
        while (current >= 0) {
            sequence.push_back(labels[current].option_id);
            current = labels[current].parent_label;
        }
        std::reverse(sequence.begin(), sequence.end());
        return sequence;
    };

    for (const auto& candidate : label_candidates) {
        std::vector<int> sequence = reconstruct_label_sequence(candidate.label_index);
        if (sequence.empty()) {
            continue;
        }
        Column column = make_column_from_sequence(instance, sequence, next_column_id + static_cast<int>(priced_columns.size()));
        if (existing_keys.count(column.key) != 0 || seen_in_batch.count(column.key) != 0) {
            continue;
        }
        const double exact_reduced_cost = compute_column_reduced_cost(instance, column, row_duals);
        if (exact_reduced_cost >= -1e-6) {
            continue;
        }
        seen_in_batch.insert(column.key);
        priced_columns.push_back(std::move(column));
        if (static_cast<int>(priced_columns.size()) >= batch_size) {
            result.columns = std::move(priced_columns);
            return result;
        }
    }

    if (config.use_bidirectional_pricing) {
        std::unordered_map<int, double> forward_cost;
        std::unordered_map<int, int> predecessor_option;
        for (const auto& option : instance.options) {
            const double depot_out_cost = get_value_or_zero(depot_out_cost_by_option, option.id);
            forward_cost[option.id] = static_cast<double>(instance.vehicle_cost) - vehicle_cap_dual + node_weight[option.id] + depot_out_cost;
            predecessor_option[option.id] = -1;
        }

        for (const auto& option : instance.options) {
            const double current_cost = forward_cost[option.id];
            if (!std::isfinite(current_cost)) {
                continue;
            }
            const auto out_it = instance.outgoing_arcs_by_option.find(option.id);
            if (out_it == instance.outgoing_arcs_by_option.end()) {
                continue;
            }
            for (const int arc_id : out_it->second) {
                const auto& arc = instance.arc_by_id.at(arc_id);
                const double candidate_cost = current_cost + arc_weight[arc_id] + node_weight[arc.to_option_id];
                if (candidate_cost + kEps < forward_cost[arc.to_option_id]) {
                    forward_cost[arc.to_option_id] = candidate_cost;
                    predecessor_option[arc.to_option_id] = option.id;
                }
            }
        }

        struct Candidate {
            double reduced_cost = 0.0;
            int meeting_option_id = -1;
        };
        std::vector<Candidate> candidates;
        std::unordered_map<int, int> successor_option;
        std::unordered_map<int, double> backward_cost;
        for (auto it = instance.options.rbegin(); it != instance.options.rend(); ++it) {
            const auto& option = *it;
            // Initialize as if this option is the last in the chain (adds depot_in cost)
            const double depot_in_cost = get_value_or_zero(depot_in_cost_by_option, option.id);
            double best_suffix = node_weight[option.id] + depot_in_cost;
            int best_successor = -1;
            const auto out_it = instance.outgoing_arcs_by_option.find(option.id);
            if (out_it != instance.outgoing_arcs_by_option.end()) {
                for (const int arc_id : out_it->second) {
                    const auto& arc = instance.arc_by_id.at(arc_id);
                    const double suffix_candidate = node_weight[option.id] + arc_weight[arc_id] + backward_cost[arc.to_option_id];
                    if (suffix_candidate + kEps < best_suffix) {
                        best_suffix = suffix_candidate;
                        best_successor = arc.to_option_id;
                    }
                }
            }
            backward_cost[option.id] = best_suffix;
            successor_option[option.id] = best_successor;
        }

        for (const auto& option : instance.options) {
            if (!std::isfinite(forward_cost[option.id]) || !std::isfinite(backward_cost[option.id])) {
                continue;
            }
            const double full_cost = forward_cost[option.id] + backward_cost[option.id] - node_weight[option.id];
            if (full_cost < -1e-6) {
                candidates.push_back({full_cost, option.id});
            }
        }

        std::sort(candidates.begin(), candidates.end(), [](const Candidate& lhs, const Candidate& rhs) {
            if (lhs.reduced_cost != rhs.reduced_cost) {
                return lhs.reduced_cost < rhs.reduced_cost;
            }
            return lhs.meeting_option_id < rhs.meeting_option_id;
        });
        result.diagnostics.bidirectional_candidate_count = static_cast<int>(candidates.size());

        for (const auto& candidate : candidates) {
            std::vector<int> sequence = reconstruct_prefix(candidate.meeting_option_id, predecessor_option);
            std::vector<int> suffix = reconstruct_suffix(candidate.meeting_option_id, successor_option);
            if (suffix.size() > 1) {
                sequence.insert(sequence.end(), suffix.begin() + 1, suffix.end());
            }
            if (sequence.empty()) {
                continue;
            }
            Column column = make_column_from_sequence(instance, sequence, next_column_id + static_cast<int>(priced_columns.size()));
            if (existing_keys.count(column.key) != 0 || seen_in_batch.count(column.key) != 0) {
                continue;
            }
            const double exact_reduced_cost = compute_column_reduced_cost(instance, column, row_duals);
            if (exact_reduced_cost >= -1e-6) {
                continue;
            }
            seen_in_batch.insert(column.key);
            priced_columns.push_back(std::move(column));
            if (static_cast<int>(priced_columns.size()) >= batch_size) {
                break;
            }
        }
    }

    result.columns = std::move(priced_columns);
    return result;
}

void write_csv_header(std::ofstream& out, const std::vector<std::string>& headers) {
    for (std::size_t i = 0; i < headers.size(); ++i) {
        if (i > 0) {
            out << ",";
        }
        out << headers[i];
    }
    out << "\n";
}

void write_iteration_log(const fs::path& file_path, const std::vector<IterationLog>& logs) {
    std::ofstream out(file_path);
    write_csv_header(out, {"iteration", "tcg_round", "master_objective", "best_reduced_cost", "active_columns", "added_columns", "fixed_columns_total", "fixed_columns_added", "pricing_batch_size", "pruned_columns", "depot_gate_rows", "depot_gate_pairwise_conflicts", "pricing_option_nodes", "pricing_arc_count", "pricing_label_states", "pricing_label_candidates", "pricing_bidirectional_candidates", "master_solve_sec", "pricing_sec", "requested_solver", "actual_solver", "fallback_used", "raw_dual_fallback_used", "incumbent_available", "best_integer_objective"});
    for (const auto& log : logs) {
        out << log.iteration << ","
            << log.tcg_round << ","
            << format_coeff(log.master_objective) << ","
            << format_coeff(log.best_reduced_cost) << ","
            << log.active_columns << ","
            << log.added_columns << ","
            << log.fixed_columns_total << ","
            << log.fixed_columns_added << ","
            << log.pricing_batch_size_used << ","
            << log.pruned_columns << ","
            << log.depot_gate_rows << ","
            << log.depot_gate_pairwise_conflicts << ","
            << log.pricing_option_nodes << ","
            << log.pricing_arc_count << ","
            << log.pricing_label_states << ","
            << log.pricing_label_candidates << ","
            << log.pricing_bidirectional_candidates << ","
            << format_coeff(log.master_solve_sec) << ","
            << format_coeff(log.pricing_sec) << ","
            << log.requested_solver << ","
            << log.actual_solver << ","
            << (log.fallback_used ? 1 : 0) << ","
            << (log.raw_dual_fallback_used ? 1 : 0) << ","
            << (log.incumbent_available ? 1 : 0) << ","
            << format_coeff(log.best_integer_objective) << "\n";
    }
}

void write_generated_columns(
    const fs::path& file_path,
    const Instance& instance,
    const std::vector<Column>& columns,
    const std::unordered_map<std::string, double>& primal_values
) {
    std::ofstream out(file_path);
    write_csv_header(out, {"column_id", "selected_value", "cost", "option_count", "arc_count", "event_count", "start_departure", "end_arrival", "start_direction", "start_xroad", "end_direction", "end_xroad", "depot_source_arc_id", "depot_sink_arc_id", "depot_out_route_id", "depot_in_route_id", "peak_ids", "option_ids", "arc_ids", "event_ids"});
    for (const auto& column : columns) {
        const double value = get_value_or_zero(primal_values, var_name_column(column.id));
        const auto peak_ids = peak_ids_from_mask(instance, column.peak_mask);
        out << column.id << ","
            << format_coeff(value) << ","
            << format_coeff(column.cost) << ","
            << column.option_ids.size() << ","
            << column.arc_ids.size() << ","
            << column.event_ids.size() << ","
            << column.start_departure << ","
            << column.end_arrival << ","
            << column.start_direction << ","
            << column.start_xroad << ","
            << column.end_direction << ","
            << column.end_xroad << ","
            << column.depot_source_arc_id << ","
            << column.depot_sink_arc_id << ","
            << column.depot_out_route_id << ","
            << column.depot_in_route_id << ","
            << "\"" << join_ints(peak_ids) << "\","
            << "\"" << join_ints(column.option_ids) << "\","
            << "\"" << join_ints(column.arc_ids) << "\","
            << "\"" << join_ints(column.event_ids) << "\"\n";
    }
}

struct SelectedDuty {
    int vehicle_id = -1;
    const Column* column = nullptr;
    double value = 0.0;
};

std::vector<SelectedDuty> collect_selected_duties(
    const Instance& instance,
    const std::vector<Column>& columns,
    const std::unordered_map<std::string, double>& primal_values
) {
    std::vector<SelectedDuty> selected;
    for (const auto& column : columns) {
        const double value = get_value_or_zero(primal_values, var_name_column(column.id));
        if (value > 0.5) {
            selected.push_back({-1, &column, value});
        }
    }
    std::sort(selected.begin(), selected.end(), [&](const SelectedDuty& lhs, const SelectedDuty& rhs) {
        const int lhs_start = instance.option_by_id.at(lhs.column->option_ids.front()).departure;
        const int rhs_start = instance.option_by_id.at(rhs.column->option_ids.front()).departure;
        if (lhs_start != rhs_start) {
            return lhs_start < rhs_start;
        }
        return lhs.column->id < rhs.column->id;
    });
    for (std::size_t index = 0; index < selected.size(); ++index) {
        selected[index].vehicle_id = static_cast<int>(index) + 1;
    }
    return selected;
}

void write_selected_duties(const fs::path& file_path, const Instance& instance, const std::vector<SelectedDuty>& duties) {
    std::ofstream out(file_path);
    write_csv_header(out, {"vehicle_id", "column_id", "selected_value", "cost", "trip_count", "arc_count", "event_count", "start_departure", "end_arrival", "start_direction", "start_xroad", "end_direction", "end_xroad", "depot_source_arc_id", "depot_sink_arc_id", "depot_out_route_id", "depot_in_route_id", "peak_ids", "option_ids", "event_ids"});
    for (const auto& duty : duties) {
        const auto& column = *duty.column;
        const auto peak_ids = peak_ids_from_mask(instance, column.peak_mask);
        out << duty.vehicle_id << ","
            << column.id << ","
            << format_coeff(duty.value) << ","
            << format_coeff(column.cost) << ","
            << column.option_ids.size() << ","
            << column.arc_ids.size() << ","
            << column.event_ids.size() << ","
            << column.start_departure << ","
            << column.end_arrival << ","
            << column.start_direction << ","
            << column.start_xroad << ","
            << column.end_direction << ","
            << column.end_xroad << ","
            << column.depot_source_arc_id << ","
            << column.depot_sink_arc_id << ","
            << column.depot_out_route_id << ","
            << column.depot_in_route_id << ","
            << "\"" << join_ints(peak_ids) << "\","
            << "\"" << join_ints(column.option_ids) << "\","
            << "\"" << join_ints(column.event_ids) << "\"\n";
    }
}

void write_selected_trips(const fs::path& file_path, const Instance& instance, const std::vector<SelectedDuty>& duties) {
    std::ofstream out(file_path);
    write_csv_header(out, {"vehicle_id", "column_id", "sequence_index", "slot_id", "option_id", "direction", "xroad", "route_id", "phase_id", "round_num", "nominal_departure", "selected_departure", "selected_arrival", "shift_seconds"});
    for (const auto& duty : duties) {
        const auto& column = *duty.column;
        for (std::size_t index = 0; index < column.option_ids.size(); ++index) {
            const auto& option = instance.option_by_id.at(column.option_ids[index]);
            const auto& slot = instance.slot_by_id.at(option.slot_id);
            out << duty.vehicle_id << ","
                << column.id << ","
                << index << ","
                << slot.id << ","
                << option.id << ","
                << option.direction << ","
                << option.xroad << ","
                << option.route_id << ","
                << slot.phase_id << ","
                << slot.round_num << ","
                << slot.nominal_departure << ","
                << option.departure << ","
                << option.arrival << ","
                << option.shift_seconds << "\n";
        }
    }
}

void write_selected_turnbacks(const fs::path& file_path, const std::vector<SelectedDuty>& duties, const Instance& instance) {
    std::ofstream out(file_path);
    write_csv_header(out, {"vehicle_id", "column_id", "sequence_index", "arc_id", "from_option_id", "to_option_id", "turnback_platform", "wait_time", "min_tb", "def_tb", "max_tb", "is_mixed", "same_turnback", "event_id"});
    for (const auto& duty : duties) {
        const auto& column = *duty.column;
        for (std::size_t index = 0; index < column.arc_ids.size(); ++index) {
            const auto& arc = instance.arc_by_id.at(column.arc_ids[index]);
            out << duty.vehicle_id << ","
                << column.id << ","
                << index << ","
                << arc.id << ","
                << arc.from_option_id << ","
                << arc.to_option_id << ","
                << arc.turnback_platform << ","
                << arc.wait_time << ","
                << arc.min_tb << ","
                << arc.def_tb << ","
                << arc.max_tb << ","
                << (arc.is_mixed ? 1 : 0) << ","
                << (arc.same_turnback ? 1 : 0) << ","
                << arc.event_id << "\n";
        }
    }
}

void write_selected_timetable(const fs::path& file_path, const Instance& instance, const std::vector<SelectedDuty>& duties) {
    struct TimetableRow {
        int vehicle_id = -1;
        int column_id = -1;
        int slot_id = -1;
        int option_id = -1;
        int direction = 0;
        int order_in_direction = 0;
        int route_id = 0;
        int xroad = 0;
        int nominal_departure = 0;
        int nominal_headway_departure = 0;
        int selected_departure = 0;
        int selected_headway_departure = 0;
        int selected_arrival = 0;
        int shift_seconds = 0;
    };

    std::vector<TimetableRow> rows;
    for (const auto& duty : duties) {
        const auto& column = *duty.column;
        for (const int option_id : column.option_ids) {
            const auto& option = instance.option_by_id.at(option_id);
            const auto& slot = instance.slot_by_id.at(option.slot_id);
            rows.push_back({
                duty.vehicle_id,
                column.id,
                slot.id,
                option_id,
                option.direction,
                slot.order_in_direction,
                option.route_id,
                option.xroad,
                slot.nominal_departure,
                slot.headway_nominal_departure,
                option.departure,
                option.headway_departure,
                option.arrival,
                option.shift_seconds
            });
        }
    }
    std::sort(rows.begin(), rows.end(), [](const TimetableRow& lhs, const TimetableRow& rhs) {
        if (lhs.selected_departure != rhs.selected_departure) {
            return lhs.selected_departure < rhs.selected_departure;
        }
        return lhs.slot_id < rhs.slot_id;
    });

    std::ofstream out(file_path);
    write_csv_header(out, {"vehicle_id", "column_id", "slot_id", "option_id", "direction", "order_in_direction", "route_id", "xroad", "nominal_departure", "nominal_headway_departure", "selected_departure", "selected_headway_departure", "selected_arrival", "deviation_seconds", "nominal_departure_hms", "nominal_headway_departure_hms", "selected_departure_hms", "selected_headway_departure_hms", "selected_arrival_hms"});
    for (const auto& row : rows) {
        out << row.vehicle_id << ","
            << row.column_id << ","
            << row.slot_id << ","
            << row.option_id << ","
            << row.direction << ","
            << row.order_in_direction << ","
            << row.route_id << ","
            << row.xroad << ","
            << row.nominal_departure << ","
            << row.nominal_headway_departure << ","
            << row.selected_departure << ","
            << row.selected_headway_departure << ","
            << row.selected_arrival << ","
            << row.shift_seconds << ","
            << format_time(row.nominal_departure) << ","
            << format_time(row.nominal_headway_departure) << ","
            << format_time(row.selected_departure) << ","
            << format_time(row.selected_headway_departure) << ","
            << format_time(row.selected_arrival) << "\n";
    }
}

double accumulate_slack(const MasterSolveResult& result, const std::string& prefix) {
    double total = 0.0;
    for (const auto& entry : result.primal_values) {
        if (starts_with(entry.first, prefix)) {
            total += entry.second;
        }
    }
    return total;
}

double peak_slack_value(const MasterSolveResult& result, int peak_id) {
    return get_value_or_zero(result.primal_values, var_name_slack_peak_cap(peak_id));
}

double vehicle_cap_slack_value(const MasterSolveResult& result) {
    return get_value_or_zero(result.primal_values, var_name_slack_vehicle_cap());
}

double integrality_gap_value(const MasterSolveResult& final_result, const MasterSolveResult& final_lp) {
    if (std::abs(final_lp.objective) <= kEps) {
        return 0.0;
    }
    return (final_result.objective - final_lp.objective) / final_lp.objective;
}

int fallback_count(
    const std::vector<IterationLog>& logs,
    const std::vector<MasterSolveResult>& extra_results
) {
    int count = 0;
    for (const auto& log : logs) {
        if (log.fallback_used) {
            ++count;
        }
    }
    for (const auto& result : extra_results) {
        if (result.fallback_used) {
            ++count;
        }
    }
    return count;
}

int raw_dual_fallback_count(const std::vector<IterationLog>& logs) {
    int count = 0;
    for (const auto& log : logs) {
        if (log.raw_dual_fallback_used) {
            ++count;
        }
    }
    return count;
}

int pruned_column_count(const std::vector<IterationLog>& logs) {
    int count = 0;
    for (const auto& log : logs) {
        count += log.pruned_columns;
    }
    return count;
}

int max_pricing_label_states(const std::vector<IterationLog>& logs) {
    int best = 0;
    for (const auto& log : logs) {
        best = std::max(best, log.pricing_label_states);
    }
    return best;
}

int last_depot_gate_rows(const std::vector<IterationLog>& logs) {
    if (logs.empty()) {
        return 0;
    }
    return logs.back().depot_gate_rows;
}

long long last_depot_gate_pairwise_conflicts(const std::vector<IterationLog>& logs) {
    if (logs.empty()) {
        return 0;
    }
    return logs.back().depot_gate_pairwise_conflicts;
}

bool persistent_master_used(const std::vector<IterationLog>& logs) {
    for (const auto& log : logs) {
        if (log.actual_solver == "GUROBI_PERSISTENT" || log.actual_solver == "CBC_PERSISTENT") {
            return true;
        }
    }
    return false;
}

bool persistent_gurobi_master_used(const std::vector<IterationLog>& logs) {
    for (const auto& log : logs) {
        if (log.actual_solver == "GUROBI_PERSISTENT") {
            return true;
        }
    }
    return false;
}

std::string first_fallback_reason(
    const std::vector<MasterSolveResult>& extra_results
) {
    for (const auto& result : extra_results) {
        if (!result.fallback_reason.empty()) {
            return result.fallback_reason;
        }
    }
    return "";
}

void write_summary_json(
    const fs::path& file_path,
    const Config& config,
    const std::string& requested_solver,
    const fs::path& instance_dir,
    const Instance& instance,
    const MasterSolveResult& selected_result,
    const MasterSolveResult& final_mip_result,
    const MasterSolveResult& lower_bound_lp,
    const MasterSolveResult& final_fixed_lp,
    const std::vector<Column>& columns,
    const std::vector<SelectedDuty>& duties,
    const std::vector<IterationLog>& logs,
    bool root_pricing_exhausted,
    bool final_round_pricing_exhausted,
    int fixed_column_count,
    int fixing_round_count,
    const std::string& selected_solution_source,
    const RunTiming& timing
) {
    const bool orthodox_tcg_active = config.enable_orthodox_tcg && config.tcg_fix_columns > 0;
    std::vector<MasterSolveResult> extra_results = {lower_bound_lp, final_mip_result};
    if (selected_solution_source != "final_mip") {
        extra_results.push_back(selected_result);
    }
    const double gap = integrality_gap_value(selected_result, lower_bound_lp);
    const int total_fallback_count = fallback_count(logs, extra_results);
    const std::string fallback_reason = first_fallback_reason(extra_results);
    std::ofstream out(file_path);
    out << "{\n";
    out << "  \"rail_path\": \"" << json_escape(config.rail_path) << "\",\n";
    out << "  \"setting_path\": \"" << json_escape(config.setting_path) << "\",\n";
    out << "  \"instance_dir\": \"" << json_escape(instance_dir.string()) << "\",\n";
    out << "  \"requested_solver\": \"" << json_escape(requested_solver) << "\",\n";
    out << "  \"lp_lower_bound_solver\": \"" << json_escape(lower_bound_lp.actual_solver) << "\",\n";
    out << "  \"final_fixed_lp_solver\": \"" << json_escape(final_fixed_lp.actual_solver) << "\",\n";
    out << "  \"final_mip_solver\": \"" << json_escape(final_mip_result.actual_solver) << "\",\n";
    out << "  \"selected_solution_source\": \"" << json_escape(selected_solution_source) << "\",\n";
    out << "  \"fallback_used\": " << (total_fallback_count > 0 ? "true" : "false") << ",\n";
    out << "  \"fallback_count\": " << total_fallback_count << ",\n";
    out << "  \"fallback_reason\": \"" << json_escape(fallback_reason) << "\",\n";
    out << "  \"status\": \"" << json_escape(selected_result.status) << "\",\n";
    out << "  \"objective\": " << format_coeff(selected_result.objective) << ",\n";
    out << "  \"final_mip_objective\": " << format_coeff(final_mip_result.objective) << ",\n";
    out << "  \"lp_lower_bound\": " << format_coeff(lower_bound_lp.objective) << ",\n";
    out << "  \"final_fixed_lp_objective\": " << format_coeff(final_fixed_lp.objective) << ",\n";
    out << "  \"integrality_gap\": " << format_coeff(gap) << ",\n";
    out << "  \"iterations\": " << logs.size() << ",\n";
    out << "  \"generated_columns\": " << columns.size() << ",\n";
    out << "  \"selected_duties\": " << duties.size() << ",\n";
    out << "  \"slot_count\": " << instance.slots.size() << ",\n";
    out << "  \"peak_count\": " << instance.peaks.size() << ",\n";
    out << "  \"headway_count\": " << instance.headways.size() << ",\n";
    out << "  \"option_conflict_count\": " << instance.option_conflicts.size() << ",\n";
    out << "  \"conflict_count\": " << instance.conflicts.size() << ",\n";
    out << "  \"seed_column_count\": " << instance.seed_column_steps.size() << ",\n";
    out << "  \"seed_phase\": " << instance.seed_phase << ",\n";
    out << "  \"max_vehicle_count\": " << instance.max_vehicle_count << ",\n";
    out << "  \"first_car\": " << instance.first_car << ",\n";
    out << "  \"orthodox_tcg_enabled\": " << (orthodox_tcg_active ? "true" : "false") << ",\n";
    out << "  \"fixed_column_count\": " << fixed_column_count << ",\n";
    out << "  \"fixing_round_count\": " << fixing_round_count << ",\n";
    out << "  \"tcg_fix_columns\": " << config.tcg_fix_columns << ",\n";
    out << "  \"tcg_fix_min_value\": " << format_coeff(config.tcg_fix_min_value) << ",\n";
    out << "  \"tcg_fix_force_value\": " << format_coeff(config.tcg_fix_force_value) << ",\n";
    out << "  \"tcg_incumbent_time_limit_sec\": " << config.tcg_incumbent_time_limit_sec << ",\n";
    out << "  \"persistent_master\": " << (persistent_master_used(logs) ? "true" : "false") << ",\n";
    out << "  \"persistent_gurobi_master\": " << (persistent_gurobi_master_used(logs) ? "true" : "false") << ",\n";
    out << "  \"dual_stabilization_enabled\": " << (config.enable_dual_stabilization ? "true" : "false") << ",\n";
    out << "  \"dual_stabilization_alpha\": " << format_coeff(config.dual_stabilization_alpha) << ",\n";
    out << "  \"dual_box_enabled\": " << (config.enable_dual_box ? "true" : "false") << ",\n";
    out << "  \"adaptive_pricing_batch_enabled\": " << (config.enable_adaptive_pricing_batch ? "true" : "false") << ",\n";
    out << "  \"pricing_batch_size\": " << config.pricing_batch_size << ",\n";
    out << "  \"min_pricing_batch_size\": " << config.min_pricing_batch_size << ",\n";
    out << "  \"column_pool_pruning_enabled\": " << (config.enable_column_pool_pruning && !orthodox_tcg_active ? "true" : "false") << ",\n";
    out << "  \"column_prune_trigger\": " << config.column_prune_trigger << ",\n";
    out << "  \"column_prune_total\": " << pruned_column_count(logs) << ",\n";
    out << "  \"pricing_max_label_states\": " << max_pricing_label_states(logs) << ",\n";
    out << "  \"depot_gate_rows_last\": " << last_depot_gate_rows(logs) << ",\n";
    out << "  \"depot_gate_pairwise_conflicts_last\": " << last_depot_gate_pairwise_conflicts(logs) << ",\n";
    out << "  \"dual_raw_fallback_count\": " << raw_dual_fallback_count(logs) << ",\n";
    out << "  \"tabu_enabled\": " << (config.enable_tabu_pricing ? "true" : "false") << ",\n";
    out << "  \"bidirectional_pricing\": " << (config.use_bidirectional_pricing ? "true" : "false") << ",\n";
    out << "  \"root_pricing_exhausted\": " << (root_pricing_exhausted ? "true" : "false") << ",\n";
    out << "  \"final_round_pricing_exhausted\": " << (final_round_pricing_exhausted ? "true" : "false") << ",\n";
    out << "  \"timing_master_sec\": " << format_coeff(timing.master_sec) << ",\n";
    out << "  \"timing_pricing_sec\": " << format_coeff(timing.pricing_sec) << ",\n";
    out << "  \"timing_other_sec\": " << format_coeff(timing.other_sec) << ",\n";
    out << "  \"timing_total_sec\": " << format_coeff(timing.total_sec) << ",\n";
    out << "  \"timing_tcg_incumbent_sec\": " << format_coeff(timing.tcg_incumbent_sec) << ",\n";
    out << "  \"timing_final_lp_sec\": " << format_coeff(timing.final_lp_sec) << ",\n";
    out << "  \"timing_final_mip_sec\": " << format_coeff(timing.final_mip_sec) << ",\n";
    out << "  \"vehicle_cap_slack\": " << format_coeff(vehicle_cap_slack_value(selected_result)) << ",\n";
    out << "  \"cover_miss_total\": " << format_coeff(accumulate_slack(selected_result, "S_cover_miss_")) << ",\n";
    out << "  \"cover_extra_total\": " << format_coeff(accumulate_slack(selected_result, "S_cover_extra_")) << ",\n";
    out << "  \"peak_slack_total\": " << format_coeff(accumulate_slack(selected_result, "S_peak_")) << ",\n";
    out << "  \"headway_target_dev\": " << format_coeff(accumulate_slack(selected_result, "S_htp_") + accumulate_slack(selected_result, "S_htn_")) << ",\n";
    out << "  \"option_conflict_slack_total\": " << format_coeff(accumulate_slack(selected_result, "S_opt_conf_")) << ",\n";
    out << "  \"arc_conflict_slack_total\": " << format_coeff(accumulate_slack(selected_result, "S_conf_")) << ",\n";
    out << "  \"peak_slacks\": [\n";
    for (std::size_t index = 0; index < instance.peaks.size(); ++index) {
        const auto& peak = instance.peaks[index];
        out << "    {\"peak_id\": " << peak.id
            << ", \"train_num\": " << peak.train_num
            << ", \"slack\": " << format_coeff(peak_slack_value(selected_result, peak.id)) << "}";
        out << (index + 1 < instance.peaks.size() ? ",\n" : "\n");
    }
    out << "  ]\n";
    out << "}\n";
}

void write_run_report(
    const fs::path& file_path,
    const Config& config,
    const std::string& requested_solver,
    const Instance& instance,
    const std::vector<Column>& columns,
    const std::vector<SelectedDuty>& duties,
    const MasterSolveResult& selected_result,
    const MasterSolveResult& final_mip_result,
    const MasterSolveResult& lower_bound_lp,
    const MasterSolveResult& final_fixed_lp,
    const std::vector<IterationLog>& logs,
    bool root_pricing_exhausted,
    bool final_round_pricing_exhausted,
    int fixed_column_count,
    int fixing_round_count,
    const std::string& selected_solution_source,
    const RunTiming& timing
) {
    const bool orthodox_tcg_active = config.enable_orthodox_tcg && config.tcg_fix_columns > 0;
    std::vector<MasterSolveResult> extra_results = {lower_bound_lp, final_mip_result};
    if (selected_solution_source != "final_mip") {
        extra_results.push_back(selected_result);
    }
    const double gap = integrality_gap_value(selected_result, lower_bound_lp);
    const int total_fallback_count = fallback_count(logs, extra_results);
    const std::string fallback_reason = first_fallback_reason(extra_results);
    std::ofstream out(file_path);
    out << "# C++ Truncated Column Generation Report\n\n";
    out << "## Run Summary\n\n";
    out << "- Status: `" << selected_result.status << "`\n";
    out << "- Requested master solver: `" << requested_solver << "`\n";
    out << "- LP lower-bound solver: `" << lower_bound_lp.actual_solver << "`\n";
    out << "- Final fixed-set LP solver: `" << final_fixed_lp.actual_solver << "`\n";
    out << "- Final MIP actual solver: `" << final_mip_result.actual_solver << "`\n";
    out << "- Selected integer solution source: `" << selected_solution_source << "`\n";
    out << "- Solver fallback used: `" << (total_fallback_count > 0 ? "yes" : "no") << "`\n";
    out << "- Solver fallback count: `" << total_fallback_count << "`\n";
    if (!fallback_reason.empty()) {
        out << "- Solver fallback reason: `" << fallback_reason << "`\n";
    }
    out << "- Exported integer objective: `" << format_coeff(selected_result.objective) << "`\n";
    out << "- Final MIP objective: `" << format_coeff(final_mip_result.objective) << "`\n";
    out << "- LP lower bound: `" << format_coeff(lower_bound_lp.objective) << "`\n";
    out << "- Final fixed-set LP objective: `" << format_coeff(final_fixed_lp.objective) << "`\n";
    out << "- Integrality gap: `" << format_coeff(gap) << "`\n";
    out << "- Iterations: `" << logs.size() << "`\n";
    out << "- Generated columns: `" << columns.size() << "`\n";
    out << "- Selected duties: `" << duties.size() << "`\n";
    out << "- Peak windows: `" << instance.peaks.size() << "`\n";
    out << "- First car target: `" << instance.first_car << "`\n";
    out << "- Slots: `" << instance.slots.size() << "`\n";
    out << "- Headway rows: `" << instance.headways.size() * 2 << "`\n";
    out << "- Option conflict rows: `" << instance.option_conflicts.size() << "`\n";
    out << "- Turnback conflict rows: `" << instance.conflicts.size() << "`\n\n";
    out << "- Legacy seed phase: `" << instance.seed_phase << "`\n";
    out << "- Legacy seed columns loaded: `" << instance.seed_column_steps.size() << "`\n";
    out << "- Root pricing exhausted: `" << (root_pricing_exhausted ? "yes" : "no") << "`\n";
    out << "- Final round pricing exhausted: `" << (final_round_pricing_exhausted ? "yes" : "no") << "`\n";
    out << "- Fixed columns: `" << fixed_column_count << "`\n";
    out << "- TCG fixing rounds: `" << fixing_round_count << "`\n";
    out << "- Orthodox TCG: `" << (orthodox_tcg_active ? "on" : "off") << "`\n";
    out << "- TCG fix columns / min / force value: `" << config.tcg_fix_columns
        << " / " << format_coeff(config.tcg_fix_min_value)
        << " / " << format_coeff(config.tcg_fix_force_value) << "`\n";
    out << "- TCG incumbent time limit (s): `" << config.tcg_incumbent_time_limit_sec << "`\n";
    out << "- Persistent master: `" << (persistent_master_used(logs) ? "on" : "off") << "`\n";
    out << "- Dual stabilization: `" << (config.enable_dual_stabilization ? "on" : "off") << "`\n";
    out << "- Dual stabilization alpha: `" << format_coeff(config.dual_stabilization_alpha) << "`\n";
    out << "- Adaptive pricing batch: `" << (config.enable_adaptive_pricing_batch ? "on" : "off") << "`\n";
    out << "- Pricing batch size / min batch size: `" << config.pricing_batch_size << " / " << config.min_pricing_batch_size << "`\n";
    out << "- Column pool pruning: `" << (config.enable_column_pool_pruning && !orthodox_tcg_active ? "on" : "off") << "`\n";
    out << "- Column prune trigger: `" << config.column_prune_trigger << "`\n";
    out << "- Total pruned columns: `" << pruned_column_count(logs) << "`\n";
    out << "- Max pricing label states: `" << max_pricing_label_states(logs) << "`\n";
    out << "- Last depot gate clique rows / pairwise conflicts: `" << last_depot_gate_rows(logs) << " / " << last_depot_gate_pairwise_conflicts(logs) << "`\n";
    out << "- Dual raw fallback count: `" << raw_dual_fallback_count(logs) << "`\n";
    out << "- Timing master/pricing/other (s): `" << format_coeff(timing.master_sec) << " / " << format_coeff(timing.pricing_sec) << " / " << format_coeff(timing.other_sec) << "`\n";
    out << "- Timing TCG incumbent/final LP/final MIP (s): `" << format_coeff(timing.tcg_incumbent_sec) << " / " << format_coeff(timing.final_lp_sec) << " / " << format_coeff(timing.final_mip_sec) << "`\n";
    out << "- Timing total (s): `" << format_coeff(timing.total_sec) << "`\n";
    out << "- Cover miss / extra slack: `" << format_coeff(accumulate_slack(selected_result, "S_cover_miss_"))
        << " / " << format_coeff(accumulate_slack(selected_result, "S_cover_extra_")) << "`\n";
    out << "- Option / arc conflict slack: `" << format_coeff(accumulate_slack(selected_result, "S_opt_conf_"))
        << " / " << format_coeff(accumulate_slack(selected_result, "S_conf_")) << "`\n\n";
    if (!root_pricing_exhausted) {
        out << "> Warning: root pricing did not exhaust all negative reduced-cost columns before hitting the iteration budget, so the LP lower bound is truncated.\n\n";
    } else if (!final_round_pricing_exhausted) {
        out << "> Warning: the last fixed-column TCG round hit the iteration budget before pricing exhaustion, so the final fixed-set master is truncated.\n\n";
    }
    out << "## Pricing Configuration\n\n";
    out << "- Tabu heuristic: `" << (config.enable_tabu_pricing ? "on" : "off") << "`\n";
    out << "- Bi-direction label search: `" << (config.use_bidirectional_pricing ? "on" : "off") << "`\n";
    out << "- Tabu option penalty: `" << format_coeff(config.tabu_option_penalty) << "`\n";
    out << "- Tabu arc penalty: `" << format_coeff(config.tabu_arc_penalty) << "`\n";
    out << "- Tabu event penalty: `" << format_coeff(config.tabu_event_penalty) << "`\n\n";
    out << "## Modeling Notes\n\n";
    out << "- Headway is modeled explicitly in the master problem with adjacent-slot lower/upper bound rows.\n";
    out << "- Headway uniformity also has an explicit target-gap deviation objective.\n";
    out << "- Peak vehicle count is soft by XML peak window; a duty counts for every peak that contains one of its departures.\n";
    out << "- First-car is enforced as a hard non-early option filter on the exported big-route first-car candidates.\n";
    out << "- Slot coverage is now soft: missing or duplicate slot coverage is allowed with separate penalties.\n";
    out << "- Depot source/sink are priced as explicit endpoint arcs attached to trip options, not as implicit post-hoc time offsets.\n";
    out << "- Same-vehicle internal continuation of an option-conflict pair is relieved when the pair is realized by a priced turnback arc inside one duty.\n";
    out << "- Arrival/departure spacing and turnback event conflicts are soft rows with slack penalties in the master, while intra-duty feasibility is carried by the pricing DAG.\n";
    out << "- Turnback resource is modeled through hard turnback occupancy event-conflict rows.\n";
    out << "- Minimum/default/maximum turnback times come from schedule XML `TurnbackMode` fields.\n";
    out << "- Same-turnback semantics follow the current Python `Engineering.judgeSameTurnback` rule.\n";
    out << "- Orthodox TCG first tries to fix every LP column with value at least the force threshold; if none survive the hard-row screening, it falls back to the top-N columns above the base threshold, then re-runs pricing on the same pool.\n";
    out << "- Mixed-route different-turnback arrival adjustment follows the current Python `RailInfo.computeNewArrival` rule.\n\n";
    out << "## Interface Compatibility\n\n";
    out << "- CLI keeps the current Python-style `-r/-u/-o/-m` inputs.\n";
    out << "- The solver reuses the existing XML parsing and route semantics through `tools/export_cg_instance.py`.\n";
    out << "- Final outputs include CSV/JSON reports and a Python-style Excel export bridge under the chosen output directory.\n";
    out << "- This implementation is truncated column generation only; it does not add branch-and-price.\n\n";
    out << "## Files\n\n";
    out << "- `generated_columns.csv`: all generated duties and final selected values.\n";
    out << "- `selected_duties.csv`: final selected vehicle duties.\n";
    out << "- `selected_trips.csv`: trip-by-trip duty decomposition.\n";
    out << "- `selected_turnbacks.csv`: chosen turnback arcs and resource events.\n";
    out << "- `selected_timetable.csv`: timetable view for the chosen options.\n";
    out << "- `summary.json`: machine-readable summary.\n";
}

fs::path resolve_tool_script_path(const std::string& script_name) {
    const std::vector<fs::path> candidates = {
        fs::absolute(fs::path("tools") / script_name),
        fs::absolute(fs::path("..") / "tools" / script_name)
    };
    for (const auto& candidate : candidates) {
        if (fs::exists(candidate)) {
            return candidate;
        }
    }
    return candidates.front();
}

bool python_has_gurobipy(const std::string& python_exe, bool debug) {
    const std::string python_cmd = python_exe.empty() ? "python" : python_exe;
#ifdef _WIN32
    std::vector<std::wstring> argv_storage = {
        fs::path(python_cmd).wstring(),
        L"-c",
        L"__import__('gurobipy')"
    };
    std::vector<const wchar_t*> argv;
    argv.reserve(argv_storage.size() + 1);
    for (const auto& arg : argv_storage) {
        argv.push_back(arg.c_str());
    }
    argv.push_back(nullptr);
    const intptr_t exit_code = _wspawnvp(_P_WAIT, argv_storage.front().c_str(), argv.data());
    if (debug) {
        std::cout << "[debug] gurobipy probe exit=" << exit_code << "\n";
    }
    return exit_code == 0;
#else
    const std::string command = quote(python_cmd) + " -c \"__import__('gurobipy')\" >/dev/null 2>&1";
    const int exit_code = std::system(command.c_str());
    if (debug) {
        std::cout << "[debug] gurobipy probe exit=" << exit_code << "\n";
    }
    return exit_code == 0;
#endif
}

bool python_has_coinmp(const std::string& python_exe, bool debug) {
    const std::string python_cmd = python_exe.empty() ? "python" : python_exe;
    const fs::path script_path = resolve_tool_script_path("solve_master_with_coinmp.py");
    if (!fs::exists(script_path)) {
        return false;
    }
#ifdef _WIN32
    std::vector<std::wstring> argv_storage = {
        fs::path(python_cmd).wstring(),
        script_path.wstring(),
        L"--self-check"
    };
    std::vector<const wchar_t*> argv;
    argv.reserve(argv_storage.size() + 1);
    for (const auto& arg : argv_storage) {
        argv.push_back(arg.c_str());
    }
    argv.push_back(nullptr);
    const intptr_t exit_code = _wspawnvp(_P_WAIT, argv_storage.front().c_str(), argv.data());
    if (debug) {
        std::cout << "[debug] coinmp probe exit=" << exit_code << "\n";
    }
    return exit_code == 0;
#else
    const std::string command = quote(python_cmd) + " " + quote(script_path.string()) + " --self-check >/dev/null 2>&1";
    const int exit_code = std::system(command.c_str());
    if (debug) {
        std::cout << "[debug] coinmp probe exit=" << exit_code << "\n";
    }
    return exit_code == 0;
#endif
}

bool bool_from_text(const std::string& value) {
    return value == "1" || value == "true" || value == "TRUE" || value == "True";
}

void print_usage() {
    std::cout
        << "urban_rail_cg usage:\n"
        << "  -r, --rail_info <path>      Schedule XML path\n"
        << "  -u, --user_setting <path>   User setting XML path\n"
        << "  -o, --output_dir <path>     Output root directory\n"
        << "  -m, --mixed_operation <0|1> Allow mixed operation\n"
        << "  --instance-dir <path>       Reuse/export CG instance directory\n"
        << "  --python <exe>              Python executable for exporter\n"
        << "  --solver <AUTO|CBC|GUROBI>  Master solver selection\n"
        << "  --cbc <exe>                 CBC executable path\n"
        << "  --gurobi <exe>              Gurobi CLI path\n"
        << "  --baseline-xlsx <path>      Optional baseline workbook for comparison export\n"
        << "  --max-iterations <n>        Truncated CG iteration limit\n"
        << "  --min-iterations <n>        Minimum CG iterations before early stop\n"
        << "  --pricing-batch <n>         Max priced columns per iteration\n"
        << "  --min-pricing-batch <n>     Minimum adaptive priced columns per iteration\n"
        << "  --column-pruning <0|1>      Prune old inactive columns from the RMP pool\n"
        << "  --column-prune-trigger <n>  Start pruning when pool size exceeds this value\n"
        << "  --column-min-age <n>        Minimum age before a column can be pruned\n"
        << "  --column-inactive-iters <n> Inactive iterations before pruning\n"
        << "  --column-recent-protect <n> Protect newly added columns for this many iterations\n"
        << "  --master-time-limit <sec>   LP master solve time limit\n"
        << "  --final-mip-time-limit <sec> Final master MIP time limit\n"
        << "  --tcg-incumbent-time-limit <sec> Time limit for interim integer masters after fixing\n"
        << "  --mip-gap <v>               Integer master relative MIP gap\n"
        << "  --orthodox-tcg <0|1>        Enable fix-and-reprice orthodox TCG rounds\n"
        << "  --tcg-fix-columns <n>       Fallback top-N columns fixed when no force-threshold column survives\n"
        << "  --tcg-fix-min-value <v>     Base LP value threshold for fallback fixing candidates\n"
        << "  --tcg-fix-force-value <v>   Fix every feasible LP column with value at least this threshold\n"
        << "  --seed-phase <n>            Export legacy seed columns (0,4,5,6)\n"
        << "  --persistent-master <0|1>   Keep iterative in-memory LP master resident when supported\n"
        << "  --dual-stabilization <0|1>  Enable stabilized pricing duals\n"
        << "  --dual-alpha <v>            Convex weight on current duals\n"
        << "  --dual-box <0|1>            Enable box clipping around dual center\n"
        << "  --dual-box-abs <v>          Absolute dual box radius\n"
        << "  --dual-box-rel <v>          Relative dual box radius\n"
        << "  --adaptive-batch <0|1>      Shrink pricing batch as reduced cost approaches 0\n"
        << "  --tabu <0|1>                Enable basis-neighborhood tabu heuristic\n"
        << "  --tabu-option-penalty <v>   Tabu penalty for option reuse\n"
        << "  --tabu-arc-penalty <v>      Tabu penalty for arc reuse\n"
        << "  --tabu-event-penalty <v>    Tabu penalty for event reuse\n"
        << "  --bidirectional-pricing <0|1>  Toggle bi-direction label search\n"
        << "  --shift-step <sec>          Explicit option shift step\n"
        << "  --reuse-instance            Skip exporter and reuse existing instance\n"
        << "  --export-only               Only export instance, do not solve\n"
        << "  -d, --debug [true|false]    Enable debug logging\n";
}

Config parse_args(int argc, char* argv[]) {
    Config config;
    for (int index = 1; index < argc; ++index) {
        const std::string arg = argv[index];
        auto require_value = [&](const std::string& name) -> std::string {
            if (index + 1 >= argc) {
                throw std::runtime_error("Missing value for argument: " + name);
            }
            ++index;
            return argv[index];
        };

        if (arg == "-h" || arg == "--help") {
            print_usage();
            std::exit(0);
        } else if (arg == "-r" || arg == "--rail_info" || arg == "--rail") {
            config.rail_path = require_value(arg);
        } else if (arg == "-u" || arg == "--user_setting" || arg == "--setting") {
            config.setting_path = require_value(arg);
        } else if (arg == "-o" || arg == "--output_dir" || arg == "--output") {
            config.output_dir = require_value(arg);
        } else if (arg == "-m" || arg == "--mixed_operation" || arg == "--mixed") {
            config.mixed_operation = std::stoi(require_value(arg));
        } else if (arg == "--instance-dir") {
            config.instance_dir = require_value(arg);
        } else if (arg == "--python") {
            config.python_exe = require_value(arg);
        } else if (arg == "--solver") {
            config.solver = upper_copy(require_value(arg));
        } else if (arg == "--cbc") {
            config.cbc_path = require_value(arg);
        } else if (arg == "--gurobi") {
            config.gurobi_path = require_value(arg);
            config.solver = "GUROBI";
        } else if (arg == "--baseline-xlsx") {
            config.baseline_xlsx = require_value(arg);
        } else if (arg == "--max-iterations") {
            config.max_iterations = std::stoi(require_value(arg));
        } else if (arg == "--min-iterations") {
            config.min_iterations = std::stoi(require_value(arg));
        } else if (arg == "--pricing-batch") {
            config.pricing_batch_size = std::stoi(require_value(arg));
        } else if (arg == "--min-pricing-batch") {
            config.min_pricing_batch_size = std::stoi(require_value(arg));
        } else if (arg == "--column-pruning") {
            config.enable_column_pool_pruning = bool_from_text(require_value(arg));
        } else if (arg == "--column-prune-trigger") {
            config.column_prune_trigger = std::stoi(require_value(arg));
        } else if (arg == "--column-min-age") {
            config.column_min_age = std::stoi(require_value(arg));
        } else if (arg == "--column-inactive-iters") {
            config.column_inactive_iterations = std::stoi(require_value(arg));
        } else if (arg == "--column-recent-protect") {
            config.column_recent_protection = std::stoi(require_value(arg));
        } else if (arg == "--master-time-limit") {
            config.master_time_limit_sec = std::stoi(require_value(arg));
        } else if (arg == "--final-mip-time-limit") {
            config.final_mip_time_limit_sec = std::stoi(require_value(arg));
        } else if (arg == "--tcg-incumbent-time-limit") {
            config.tcg_incumbent_time_limit_sec = std::stoi(require_value(arg));
        } else if (arg == "--mip-gap") {
            config.mip_gap = std::stod(require_value(arg));
        } else if (arg == "--orthodox-tcg") {
            config.enable_orthodox_tcg = bool_from_text(require_value(arg));
        } else if (arg == "--tcg-fix-columns") {
            config.tcg_fix_columns = std::stoi(require_value(arg));
        } else if (arg == "--tcg-fix-min-value") {
            config.tcg_fix_min_value = std::stod(require_value(arg));
        } else if (arg == "--tcg-fix-force-value") {
            config.tcg_fix_force_value = std::stod(require_value(arg));
        } else if (arg == "--seed-phase") {
            config.seed_phase = std::stoi(require_value(arg));
        } else if (arg == "--persistent-master") {
            config.enable_persistent_gurobi_master = bool_from_text(require_value(arg));
        } else if (arg == "--dual-stabilization") {
            config.enable_dual_stabilization = bool_from_text(require_value(arg));
        } else if (arg == "--dual-alpha") {
            config.dual_stabilization_alpha = std::stod(require_value(arg));
        } else if (arg == "--dual-box") {
            config.enable_dual_box = bool_from_text(require_value(arg));
        } else if (arg == "--dual-box-abs") {
            config.dual_box_abs = std::stod(require_value(arg));
        } else if (arg == "--dual-box-rel") {
            config.dual_box_rel = std::stod(require_value(arg));
        } else if (arg == "--adaptive-batch") {
            config.enable_adaptive_pricing_batch = bool_from_text(require_value(arg));
        } else if (arg == "--tabu") {
            config.enable_tabu_pricing = bool_from_text(require_value(arg));
        } else if (arg == "--tabu-option-penalty") {
            config.tabu_option_penalty = std::stod(require_value(arg));
        } else if (arg == "--tabu-arc-penalty") {
            config.tabu_arc_penalty = std::stod(require_value(arg));
        } else if (arg == "--tabu-event-penalty") {
            config.tabu_event_penalty = std::stod(require_value(arg));
        } else if (arg == "--bidirectional-pricing") {
            config.use_bidirectional_pricing = bool_from_text(require_value(arg));
        } else if (arg == "--shift-step") {
            config.shift_step = std::stoi(require_value(arg));
        } else if (arg == "--reuse-instance") {
            config.reuse_instance = true;
        } else if (arg == "--export-only") {
            config.export_only = true;
        } else if (arg == "-d" || arg == "--debug") {
            if (index + 1 < argc && argv[index + 1][0] != '-') {
                config.debug = bool_from_text(require_value(arg));
            } else {
                config.debug = true;
            }
        } else if (arg == "-a" || arg == "--algorithm") {
            config.algorithm = require_value(arg);
        } else if (arg == "-s" || arg == "--solver") {
            config.solver = require_value(arg);
        } else if (arg == "-i" || arg == "--init") {
            config.arrange_init = bool_from_text(require_value(arg));
        } else if (arg == "-p" || arg == "--n_phase") {
            config.n_phase = std::stoi(require_value(arg));
        } else if (arg == "-t" || arg == "--obj_type") {
            config.obj_type = std::stoi(require_value(arg));
        } else {
            throw std::runtime_error("Unknown argument: " + arg);
        }
    }
    return config;
}

fs::path resolve_instance_dir(const Config& config) {
    if (!config.instance_dir.empty()) {
        return fs::absolute(config.instance_dir);
    }
    return fs::absolute(fs::path(config.output_dir) / "cg_instance");
}

fs::path resolve_solution_dir(const Config& config) {
    return fs::absolute(fs::path(config.output_dir) / "cg_solution");
}

void export_instance_if_needed(const Config& config, const fs::path& instance_dir) {
    const fs::path manifest_path = instance_dir / "manifest.txt";
    if (config.reuse_instance && fs::exists(manifest_path)) {
        return;
    }
    if (config.rail_path.empty() || config.setting_path.empty()) {
        throw std::runtime_error("rail_info and user_setting are required unless --reuse-instance points to an existing exported instance.");
    }

    fs::create_directories(instance_dir);
    const fs::path script_path = resolve_tool_script_path("export_cg_instance.py");
    if (!fs::exists(script_path)) {
        throw std::runtime_error("Exporter script not found: " + script_path.string());
    }

#ifdef _WIN32
    std::vector<std::wstring> argv_storage = {
        fs::path(config.python_exe).wstring(),
        script_path.wstring(),
        L"--rail",
        fs::absolute(config.rail_path).wstring(),
        L"--setting",
        fs::absolute(config.setting_path).wstring(),
        L"--out",
        instance_dir.wstring(),
        L"--mixed",
        std::to_wstring(config.mixed_operation),
        L"--seed-phase",
        std::to_wstring(config.seed_phase)
    };
    if (config.shift_step > 0) {
        argv_storage.push_back(L"--shift-step");
        argv_storage.push_back(std::to_wstring(config.shift_step));
    }
    std::vector<const wchar_t*> argv;
    argv.reserve(argv_storage.size() + 1);
    for (const auto& arg : argv_storage) {
        argv.push_back(arg.c_str());
    }
    argv.push_back(nullptr);
    if (config.debug) {
        std::cout << "[debug] Export argv:";
        for (const auto& arg : argv_storage) {
            std::cout << " [" << fs::path(arg).string() << "]";
        }
        std::cout << "\n";
    }
    const intptr_t exit_code = _wspawnvp(_P_WAIT, argv_storage.front().c_str(), argv.data());
#else
    std::string command = quote(config.python_exe)
        + " " + quote(script_path.string())
        + " --rail " + quote(fs::absolute(config.rail_path).string())
        + " --setting " + quote(fs::absolute(config.setting_path).string())
        + " --out " + quote(instance_dir.string())
        + " --mixed " + std::to_string(config.mixed_operation)
        + " --seed-phase " + std::to_string(config.seed_phase);
    if (config.shift_step > 0) {
        command += " --shift-step " + std::to_string(config.shift_step);
    }
    if (config.debug) {
        std::cout << "[debug] Export command: " << command << "\n";
    }
    const int exit_code = std::system(command.c_str());
#endif
    if (exit_code != 0) {
        throw std::runtime_error("Instance export failed with exit code " + std::to_string(exit_code));
    }
    if (!fs::exists(manifest_path)) {
        throw std::runtime_error("Instance export finished without manifest: " + manifest_path.string());
    }
}

void export_solution_artifacts(const Config& config, const fs::path& instance_dir, const fs::path& solution_dir) {
    const fs::path script_path = resolve_tool_script_path("export_cg_solution_excel.py");
    if (!fs::exists(script_path)) {
        throw std::runtime_error("Solution export script not found: " + script_path.string());
    }

#ifdef _WIN32
    std::vector<std::wstring> argv_storage = {
        fs::path(config.python_exe).wstring(),
        script_path.wstring(),
        L"--instance-dir",
        instance_dir.wstring(),
        L"--solution-dir",
        solution_dir.wstring(),
        L"--out",
        solution_dir.wstring()
    };
    if (!config.baseline_xlsx.empty()) {
        argv_storage.push_back(L"--baseline");
        argv_storage.push_back(fs::absolute(config.baseline_xlsx).wstring());
    }
    std::vector<const wchar_t*> argv;
    argv.reserve(argv_storage.size() + 1);
    for (const auto& arg : argv_storage) {
        argv.push_back(arg.c_str());
    }
    argv.push_back(nullptr);
    if (config.debug) {
        std::cout << "[debug] Solution-export argv:";
        for (const auto& arg : argv_storage) {
            std::cout << " [" << fs::path(arg).string() << "]";
        }
        std::cout << "\n";
    }
    const intptr_t exit_code = _wspawnvp(_P_WAIT, argv_storage.front().c_str(), argv.data());
#else
    std::string command = quote(config.python_exe)
        + " " + quote(script_path.string())
        + " --instance-dir " + quote(instance_dir.string())
        + " --solution-dir " + quote(solution_dir.string())
        + " --out " + quote(solution_dir.string());
    if (!config.baseline_xlsx.empty()) {
        command += " --baseline " + quote(fs::absolute(config.baseline_xlsx).string());
    }
    if (config.debug) {
        std::cout << "[debug] Solution-export command: " << command << "\n";
    }
    const int exit_code = std::system(command.c_str());
#endif
    if (exit_code != 0) {
        throw std::runtime_error("Solution export failed with exit code " + std::to_string(exit_code));
    }
}

}  // namespace

int main(int argc, char* argv[]) {
    try {
        const Config config = parse_args(argc, argv);
        const fs::path output_root = fs::absolute(config.output_dir);
        const fs::path instance_dir = resolve_instance_dir(config);
        const fs::path solution_dir = resolve_solution_dir(config);
        fs::create_directories(output_root);

        export_instance_if_needed(config, instance_dir);
        if (config.export_only) {
            std::cout << "Exported CG instance to: " << instance_dir.string() << "\n";
            return 0;
        }

        Instance instance;
        load_instance(instance_dir, instance);

        std::string cbc_path = config.cbc_path.empty() ? instance.cbc_path : config.cbc_path;
        if (cbc_path.empty()) {
            cbc_path = "cbc";
        }
        std::string gurobi_path = config.gurobi_path;
        std::string solver_name = config.solver;
        // Auto-detect Gurobi only in AUTO mode.
        if (solver_name == "AUTO") {
            if (python_has_gurobipy(config.python_exe, config.debug)) {
                solver_name = "GUROBI";
                std::cout << "  Auto-detected Gurobi Python API via `gurobipy`\n";
            }
        }
        if (solver_name == "AUTO" && gurobi_path.empty()) {
#ifdef _WIN32
            auto try_gurobi = [&](const fs::path& candidate) -> bool {
                if (fs::exists(candidate)) {
                    gurobi_path = candidate.string();
                    solver_name = "GUROBI";
                    std::cout << "  Auto-detected Gurobi: " << gurobi_path << "\n";
                    return true;
                }
                return false;
            };
            // 1) GUROBI_HOME env var
            const char* gurobi_home = std::getenv("GUROBI_HOME");
            if (gurobi_home) {
                try_gurobi(fs::path(gurobi_home) / "bin" / "gurobi_cl.exe");
            }
            // 2) Common installation paths
            if (gurobi_path.empty()) {
                const std::vector<std::string> search_dirs = {
                    "G:\\Gurobi\\win64\\bin",
                    "C:\\gurobi\\win64\\bin",
                    "C:\\gurobi1100\\win64\\bin",
                    "C:\\gurobi1001\\win64\\bin",
                    "C:\\gurobi952\\win64\\bin",
                };
                for (const auto& dir : search_dirs) {
                    if (try_gurobi(fs::path(dir) / "gurobi_cl.exe")) {
                        break;
                    }
                }
            }
#endif
        }
        if (solver_name == "AUTO") {
            solver_name = "CBC";
        }

        if (config.debug) {
            std::cout << "[debug] slots=" << instance.slots.size()
                      << " peaks=" << instance.peaks.size()
                      << " options=" << instance.options.size()
                      << " arcs=" << instance.arcs.size()
                      << " headways=" << instance.headways.size()
                      << " option_conflicts=" << instance.option_conflicts.size()
                      << " conflicts=" << instance.conflicts.size()
                      << " tabu=" << (config.enable_tabu_pricing ? 1 : 0)
                      << " bidirectional=" << (config.use_bidirectional_pricing ? 1 : 0)
                      << " solver=" << solver_name << "\n";
        } else {
            std::cout << "  Solver: " << solver_name
                      << "  batch_size=" << config.pricing_batch_size
                      << "  max_iter=" << config.max_iterations << "\n";
        }

        std::vector<Column> columns = build_initial_columns(instance);
        std::unordered_set<std::string> column_keys;
        for (const auto& column : columns) {
            column_keys.insert(column.key);
        }

        std::vector<IterationLog> logs;
        int next_column_id = static_cast<int>(columns.size());
        RunTiming timing;
        std::unordered_map<std::string, double> dual_center;
        const bool orthodox_tcg_active = config.enable_orthodox_tcg && config.tcg_fix_columns > 0;
        const bool allow_column_pool_pruning = config.enable_column_pool_pruning && !orthodox_tcg_active;
        if (config.enable_column_pool_pruning && !allow_column_pool_pruning) {
            std::cout << "  Column pruning disabled while orthodox TCG fixing is active to preserve the full column pool.\n";
        }
        std::unordered_set<int> fixed_column_ids;
        int tcg_round = 0;
        int fixing_round_count = 0;
        bool root_pricing_exhausted = false;
        bool final_round_pricing_exhausted = false;
        std::optional<MasterSolveResult> root_lp_result;
        MasterSolveResult best_integer_result;
        std::string best_integer_source;
        bool has_best_integer_result = false;
        const bool persistent_master_supported =
            config.enable_persistent_gurobi_master &&
            (
                (solver_name == "GUROBI" && python_has_gurobipy(config.python_exe, config.debug)) ||
                (solver_name == "CBC" && python_has_coinmp(config.python_exe, config.debug))
            );
        bool persistent_master_disabled = false;
        std::optional<PersistentGurobiMasterSession> persistent_gurobi_lp_session;
        std::optional<PersistentCoinMPMasterSession> persistent_coinmp_lp_session;
        auto reset_persistent_lp_session = [&]() {
            if (persistent_gurobi_lp_session.has_value()) {
                persistent_gurobi_lp_session.reset();
            }
            if (persistent_coinmp_lp_session.has_value()) {
                persistent_coinmp_lp_session.reset();
            }
        };
        auto ensure_persistent_lp_session = [&]() {
            if (!persistent_master_supported ||
                persistent_master_disabled ||
                persistent_gurobi_lp_session.has_value() ||
                persistent_coinmp_lp_session.has_value()) {
                return;
            }
            if (solver_name == "GUROBI") {
                persistent_gurobi_lp_session.emplace(
                    instance,
                    solution_dir / "_persistent_gurobi_master",
                    config.python_exe,
                    config.debug
                );
                return;
            }
            if (solver_name == "CBC") {
                persistent_coinmp_lp_session.emplace(
                    instance,
                    solution_dir / "_persistent_coinmp_master",
                    config.python_exe,
                    config.debug
                );
            }
        };
        auto has_persistent_lp_session = [&]() {
            return persistent_gurobi_lp_session.has_value() || persistent_coinmp_lp_session.has_value();
        };
        auto solve_with_persistent_lp_session = [&](const std::vector<Column>& solve_columns,
                                                   const std::unordered_set<int>& solve_fixed_column_ids,
                                                   int time_limit_sec) {
            if (persistent_gurobi_lp_session.has_value()) {
                return persistent_gurobi_lp_session->solve(solve_columns, solve_fixed_column_ids, time_limit_sec);
            }
            if (persistent_coinmp_lp_session.has_value()) {
                return persistent_coinmp_lp_session->solve(solve_columns, solve_fixed_column_ids, time_limit_sec);
            }
            throw std::runtime_error("Persistent master session is not initialized");
        };

        ensure_persistent_lp_session();
        const auto solve_start = std::chrono::steady_clock::now();
        for (int iteration = 1; iteration <= config.max_iterations; ++iteration) {
            const fs::path iteration_dir = solution_dir / ("iter_" + std::to_string(iteration));
            const auto iter_master_start = std::chrono::steady_clock::now();
            MasterSolveResult lp_result;
            ensure_persistent_lp_session();
            if (has_persistent_lp_session()) {
                try {
                    lp_result = solve_with_persistent_lp_session(columns, fixed_column_ids, config.master_time_limit_sec);
                } catch (const std::exception& e) {
                    std::cout << "[warn] Persistent master failed (" << e.what()
                              << "), falling back to one-shot master solves\n";
                    reset_persistent_lp_session();
                    persistent_master_disabled = true;
                    lp_result = solve_master(
                        instance,
                        columns,
                        false,
                        fixed_column_ids,
                        iteration_dir,
                        cbc_path,
                        config.python_exe,
                        gurobi_path,
                        solver_name,
                        config.master_time_limit_sec,
                        config.mip_gap,
                        "master_lp",
                        config.debug
                    );
                }
            } else {
                lp_result = solve_master(
                    instance,
                    columns,
                    false,
                    fixed_column_ids,
                    iteration_dir,
                    cbc_path,
                    config.python_exe,
                    gurobi_path,
                    solver_name,
                    config.master_time_limit_sec,
                    config.mip_gap,
                    "master_lp",
                    config.debug
                );
            }
            const auto iter_master_end = std::chrono::steady_clock::now();
            const double iter_master_sec = elapsed_seconds(iter_master_start, iter_master_end);
            timing.master_sec += iter_master_sec;

            const auto iter_pricing_start = std::chrono::steady_clock::now();
            const int current_column_count = static_cast<int>(columns.size());
            const DepotGateStats depot_gate_stats = compute_depot_gate_stats(instance, columns);
            const int pricing_batch_size = effective_pricing_batch_size(config, logs);
            const auto pricing_duals = stabilize_row_duals(lp_result.row_duals, dual_center, config);
            PricingResult pricing_result = price_columns(
                instance,
                pricing_duals,
                lp_result.primal_values,
                columns,
                column_keys,
                next_column_id,
                pricing_batch_size,
                config
            );
            std::vector<Column> new_columns = std::move(pricing_result.columns);
            PricingDiagnostics pricing_diagnostics = pricing_result.diagnostics;
            bool raw_dual_fallback_used = false;
            const std::unordered_map<std::string, double>* reduced_cost_duals = &pricing_duals;
            if (new_columns.empty() && config.enable_dual_stabilization && !dual_center.empty()) {
                PricingResult raw_pricing_result = price_columns(
                    instance,
                    lp_result.row_duals,
                    lp_result.primal_values,
                    columns,
                    column_keys,
                    next_column_id,
                    pricing_batch_size,
                    config
                );
                new_columns = std::move(raw_pricing_result.columns);
                if (!new_columns.empty()) {
                    raw_dual_fallback_used = true;
                    reduced_cost_duals = &lp_result.row_duals;
                    pricing_diagnostics = raw_pricing_result.diagnostics;
                }
            }
            const auto iter_pricing_end = std::chrono::steady_clock::now();
            const double iter_pricing_sec = elapsed_seconds(iter_pricing_start, iter_pricing_end);
            timing.pricing_sec += iter_pricing_sec;

            double best_reduced_cost = 0.0;
            for (const auto& column : new_columns) {
                const double reduced_cost = compute_column_reduced_cost(instance, column, *reduced_cost_duals);
                if (reduced_cost < best_reduced_cost) {
                    best_reduced_cost = reduced_cost;
                }
            }
            dual_center = raw_dual_fallback_used ? lp_result.row_duals : pricing_duals;
            ColumnPruneStats prune_stats;
            if (!new_columns.empty() && allow_column_pool_pruning) {
                prune_stats = prune_inactive_columns(columns, lp_result.primal_values, iteration, config);
                if (prune_stats.pruned_columns > 0) {
                    column_keys.clear();
                    for (const auto& column : columns) {
                        column_keys.insert(column.key);
                    }
                    if (has_persistent_lp_session()) {
                        reset_persistent_lp_session();
                    }
                }
            }

            IterationLog iter_log;
            iter_log.iteration = iteration;
            iter_log.tcg_round = tcg_round;
            iter_log.master_objective = lp_result.objective;
            iter_log.best_reduced_cost = best_reduced_cost;
            iter_log.active_columns = current_column_count;
            iter_log.added_columns = static_cast<int>(new_columns.size());
            iter_log.fixed_columns_total = static_cast<int>(fixed_column_ids.size());
            iter_log.fixed_columns_added = 0;
            iter_log.pricing_batch_size_used = pricing_batch_size;
            iter_log.pruned_columns = prune_stats.pruned_columns;
            iter_log.depot_gate_rows = depot_gate_stats.clique_row_count;
            iter_log.depot_gate_pairwise_conflicts = depot_gate_stats.pairwise_conflict_count;
            iter_log.pricing_option_nodes = pricing_diagnostics.option_node_count;
            iter_log.pricing_arc_count = pricing_diagnostics.arc_count;
            iter_log.pricing_label_states = pricing_diagnostics.label_state_count;
            iter_log.pricing_label_candidates = pricing_diagnostics.label_candidate_count;
            iter_log.pricing_bidirectional_candidates = pricing_diagnostics.bidirectional_candidate_count;
            iter_log.master_solve_sec = iter_master_sec;
            iter_log.pricing_sec = iter_pricing_sec;
            iter_log.requested_solver = lp_result.requested_solver;
            iter_log.actual_solver = lp_result.actual_solver;
            iter_log.fallback_used = lp_result.fallback_used;
            iter_log.raw_dual_fallback_used = raw_dual_fallback_used;
            iter_log.incumbent_available = has_best_integer_result;
            iter_log.best_integer_objective = has_best_integer_result ? best_integer_result.objective : 0.0;

            if (config.debug) {
                std::cout << "[debug] iter=" << iteration
                          << " round=" << tcg_round
                          << " obj=" << lp_result.objective
                          << " batch=" << pricing_batch_size
                          << " labels=" << pricing_diagnostics.label_state_count
                          << " gate_rows=" << depot_gate_stats.clique_row_count
                          << " pruned=" << prune_stats.pruned_columns
                          << " new_columns=" << new_columns.size()
                          << " fixed=" << fixed_column_ids.size()
                          << " best_rc=" << best_reduced_cost << "\n";
            } else if (iteration % 10 == 0 || iteration <= 3) {
                std::cout << "  iter " << iteration
                          << "  round=" << tcg_round
                          << "  obj=" << static_cast<long long>(lp_result.objective)
                          << "  rc=" << static_cast<long long>(best_reduced_cost)
                          << "  batch=" << pricing_batch_size
                          << "  cols=" << columns.size() + new_columns.size()
                          << "  fixed=" << fixed_column_ids.size()
                          << "  labels=" << pricing_diagnostics.label_state_count
                          << "\n";
                std::cout.flush();
            }

            if (new_columns.empty()) {
                if (fixed_column_ids.empty()) {
                    root_pricing_exhausted = true;
                    root_lp_result = lp_result;
                }

                std::vector<int> newly_fixed_column_ids;
                if (orthodox_tcg_active) {
                    newly_fixed_column_ids = select_tcg_fix_column_ids(
                        instance,
                        columns,
                        lp_result.primal_values,
                        fixed_column_ids,
                        config
                    );
                }
                iter_log.fixed_columns_added = static_cast<int>(newly_fixed_column_ids.size());
                iter_log.fixed_columns_total = static_cast<int>(fixed_column_ids.size() + newly_fixed_column_ids.size());

                if (!newly_fixed_column_ids.empty()) {
                    for (const int column_id : newly_fixed_column_ids) {
                        fixed_column_ids.insert(column_id);
                    }
                    ++fixing_round_count;
                    ++tcg_round;
                    dual_center.clear();

                    const auto interim_mip_start = std::chrono::steady_clock::now();
                    try {
                        const MasterSolveResult interim_result = solve_master(
                            instance,
                            columns,
                            true,
                            fixed_column_ids,
                            solution_dir / ("tcg_round_" + std::to_string(tcg_round)),
                            cbc_path,
                            config.python_exe,
                            gurobi_path,
                            solver_name,
                            config.tcg_incumbent_time_limit_sec,
                            config.mip_gap,
                            "master_mip_tcg_round_" + std::to_string(tcg_round),
                            config.debug
                        );
                        const auto interim_mip_end = std::chrono::steady_clock::now();
                        const double interim_mip_sec = elapsed_seconds(interim_mip_start, interim_mip_end);
                        timing.tcg_incumbent_sec += interim_mip_sec;
                        timing.master_sec += interim_mip_sec;
                        update_best_integer_result(
                            interim_result,
                            "tcg_round_" + std::to_string(tcg_round),
                            best_integer_result,
                            best_integer_source,
                            has_best_integer_result
                        );
                    } catch (const std::exception& e) {
                        const auto interim_mip_end = std::chrono::steady_clock::now();
                        const double interim_mip_sec = elapsed_seconds(interim_mip_start, interim_mip_end);
                        timing.tcg_incumbent_sec += interim_mip_sec;
                        timing.master_sec += interim_mip_sec;
                        std::cout << "[warn] Interim TCG integer master failed (" << e.what()
                                  << "), continuing with the incumbent cache unchanged\n";
                    }

                    iter_log.incumbent_available = has_best_integer_result;
                    iter_log.best_integer_objective = has_best_integer_result ? best_integer_result.objective : 0.0;
                    logs.push_back(iter_log);
                    write_iteration_log(solution_dir / "iterations_live.csv", logs);
                    std::cout << "  Pricing exhausted at iteration " << iteration
                              << "; fixed " << newly_fixed_column_ids.size()
                              << " high-value columns, total fixed=" << fixed_column_ids.size()
                              << ", next TCG round=" << tcg_round << "\n";
                    continue;
                }

                final_round_pricing_exhausted = true;
                logs.push_back(iter_log);
                write_iteration_log(solution_dir / "iterations_live.csv", logs);
                std::cout << "  Pricing exhausted at iteration " << iteration
                          << " for TCG round " << tcg_round << "\n";
                break;
            }

            logs.push_back(iter_log);
            write_iteration_log(solution_dir / "iterations_live.csv", logs);
            for (auto& column : new_columns) {
                column.id = next_column_id++;
                column.birth_iteration = iteration;
                column_keys.insert(column.key);
                columns.push_back(std::move(column));
            }
        }
        if (has_persistent_lp_session()) {
            reset_persistent_lp_session();
        }

        if (!root_pricing_exhausted) {
            std::cout << "  Warning: reached max_iterations before root pricing exhaustion; the reported LP bound is truncated.\n";
        } else if (!final_round_pricing_exhausted) {
            std::cout << "  Warning: reached max_iterations before the last fixed-column round finished pricing; the final fixed-set master is truncated.\n";
        }

        const auto final_lp_start = std::chrono::steady_clock::now();
        const MasterSolveResult final_fixed_lp = solve_master(
            instance,
            columns,
            false,
            fixed_column_ids,
            solution_dir / "final_master",
            cbc_path,
            config.python_exe,
            gurobi_path,
            solver_name,
            config.master_time_limit_sec,
            config.mip_gap,
            "master_lp_final",
            config.debug
        );
        const auto final_lp_end = std::chrono::steady_clock::now();
        timing.final_lp_sec = elapsed_seconds(final_lp_start, final_lp_end);
        timing.master_sec += timing.final_lp_sec;
        const MasterSolveResult lower_bound_lp = root_lp_result.has_value() ? *root_lp_result : final_fixed_lp;
        std::cout << "  Final fixed-set LP objective: " << final_fixed_lp.objective << "\n";
        std::cout << "  LP bound used for reporting: " << lower_bound_lp.objective << "\n";
        std::cout << "  Total columns generated: " << columns.size() << "\n";

        const auto final_mip_start = std::chrono::steady_clock::now();
        const MasterSolveResult final_mip_result = solve_master(
            instance,
            columns,
            true,
            fixed_column_ids,
            solution_dir / "final_master",
            cbc_path,
            config.python_exe,
            gurobi_path,
            solver_name,
            config.final_mip_time_limit_sec,
            config.mip_gap,
            "master_mip",
            config.debug
        );
        const auto final_mip_end = std::chrono::steady_clock::now();
        timing.final_mip_sec = elapsed_seconds(final_mip_start, final_mip_end);
        timing.master_sec += timing.final_mip_sec;
        update_best_integer_result(
            final_mip_result,
            "final_mip",
            best_integer_result,
            best_integer_source,
            has_best_integer_result
        );
        if (!final_mip_result.ok) {
            std::cout << "  Warning: final integer master did not return a feasible integer incumbent: "
                      << final_mip_result.status << "\n";
        }
        if (!has_best_integer_result) {
            throw std::runtime_error(
                "No feasible integer incumbent was found by interim or final integer masters; "
                "final MIP status: " + final_mip_result.status
            );
        }
        const MasterSolveResult& selected_integer_result = best_integer_result;
        std::cout << "  Final MIP objective: " << final_mip_result.objective << "\n";
        std::cout << "  Exported integer objective: " << selected_integer_result.objective
                  << " (" << best_integer_source << ")\n";
        if (lower_bound_lp.objective > 0) {
            const double gap = integrality_gap_value(selected_integer_result, lower_bound_lp);
            std::cout << "  Integrality gap: " << (gap * 100.0) << "%\n";
        }

        const auto duties = collect_selected_duties(instance, columns, selected_integer_result.primal_values);
        const auto solve_end = std::chrono::steady_clock::now();
        timing.total_sec = elapsed_seconds(solve_start, solve_end);
        timing.other_sec = std::max(0.0, timing.total_sec - timing.master_sec - timing.pricing_sec);
        write_iteration_log(solution_dir / "iterations.csv", logs);
        write_generated_columns(solution_dir / "generated_columns.csv", instance, columns, selected_integer_result.primal_values);
        write_selected_duties(solution_dir / "selected_duties.csv", instance, duties);
        write_selected_trips(solution_dir / "selected_trips.csv", instance, duties);
        write_selected_turnbacks(solution_dir / "selected_turnbacks.csv", duties, instance);
        write_selected_timetable(solution_dir / "selected_timetable.csv", instance, duties);
        write_summary_json(
            solution_dir / "summary.json",
            config,
            solver_name,
            instance_dir,
            instance,
            selected_integer_result,
            final_mip_result,
            lower_bound_lp,
            final_fixed_lp,
            columns,
            duties,
            logs,
            root_pricing_exhausted,
            final_round_pricing_exhausted,
            static_cast<int>(fixed_column_ids.size()),
            fixing_round_count,
            best_integer_source,
            timing
        );
        write_run_report(
            solution_dir / "run_report.md",
            config,
            solver_name,
            instance,
            columns,
            duties,
            selected_integer_result,
            final_mip_result,
            lower_bound_lp,
            final_fixed_lp,
            logs,
            root_pricing_exhausted,
            final_round_pricing_exhausted,
            static_cast<int>(fixed_column_ids.size()),
            fixing_round_count,
            best_integer_source,
            timing
        );
        export_solution_artifacts(config, instance_dir, solution_dir);

        std::cout << "Solved truncated CG instance.\n";
        std::cout << "  Instance: " << instance_dir.string() << "\n";
        std::cout << "  Solution: " << solution_dir.string() << "\n";
        std::cout << "  Duties: " << duties.size() << "\n";
        std::cout << "  Columns: " << columns.size() << "\n";
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "urban_rail_cg error: " << ex.what() << "\n";
        return 1;
    }
}
