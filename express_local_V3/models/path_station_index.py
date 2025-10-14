"""
PathStationIndex - 路径站点索引映射模型

职责：建立path顺序与station之间的精确映射关系，消除dest_code与station_id混用的隐患
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class PathStationNode:
    """
    路径中的单个站点节点
    
    核心设计理念：
    - path_index: 在路径中的唯一顺序编号（0-based），作为主键
    - dest_code: 站台目的地码（来自path.nodeList），是输出层的唯一标识
    - station_id: 真实车站ID（可能为None，如折返轨、虚拟节点）
    - station_name: 车站名称（用于日志和调试）
    """
    path_index: int                # 在路径中的顺序（0, 1, 2, ...）
    dest_code: str                 # 站台目的地码（关键！输出用）
    station_id: Optional[str]      # 真实车站ID（可能为None）
    station_name: Optional[str]    # 车站名称
    direction: Optional[str] = None  # 方向标记（"up"/"down"，可选）
    is_virtual: bool = False       # 是否为虚拟节点（折返轨等）
    
    def __repr__(self) -> str:
        virtual_flag = "[虚拟]" if self.is_virtual else ""
        return f"Node[{self.path_index}]{virtual_flag} {self.dest_code} ({self.station_name or 'N/A'})"


class PathStationIndex:
    """
    路径站点索引映射表
    
    核心功能：
    1. 提供dest_code -> station_id的精确映射
    2. 支持按path_index顺序遍历
    3. 标记虚拟节点（折返轨、出入库）
    
    使用场景：
    - TimetableBuilder: 按path_index顺序生成entry
    - RouteSolution: 按path_index索引entry获取站台码
    - 越行检测: 通过path_index精确匹配同站点的快慢车entry
    """
    
    def __init__(self, route_id: str):
        """
        Args:
            route_id: 路径ID（用于日志标识）
        """
        self.route_id = route_id
        self.nodes: List[PathStationNode] = []
        
        # 索引加速查询
        self._dest_code_to_node: Dict[str, PathStationNode] = {}
        self._station_id_to_nodes: Dict[str, List[PathStationNode]] = {}
        self._path_index_to_node: Dict[int, PathStationNode] = {}
    
    def add_node(self, 
                 path_index: int,
                 dest_code: str,
                 station_id: Optional[str] = None,
                 station_name: Optional[str] = None,
                 direction: Optional[str] = None,
                 is_virtual: bool = False):
        """
        添加路径节点
        
        Args:
            path_index: 路径顺序索引
            dest_code: 站台目的地码（必需）
            station_id: 车站ID（可选，虚拟节点可为None）
            station_name: 车站名称（可选）
            direction: 方向（"up"/"down"）
            is_virtual: 是否为虚拟节点（折返轨等）
        """
        node = PathStationNode(
            path_index=path_index,
            dest_code=dest_code,
            station_id=station_id,
            station_name=station_name,
            direction=direction,
            is_virtual=is_virtual
        )
        
        self.nodes.append(node)
        
        # 构建索引
        self._path_index_to_node[path_index] = node
        self._dest_code_to_node[dest_code] = node
        
        if station_id:
            if station_id not in self._station_id_to_nodes:
                self._station_id_to_nodes[station_id] = []
            self._station_id_to_nodes[station_id].append(node)
    
    def get_node_by_index(self, path_index: int) -> Optional[PathStationNode]:
        """通过路径索引获取节点"""
        return self._path_index_to_node.get(path_index)
    
    def get_node_by_dest_code(self, dest_code: str) -> Optional[PathStationNode]:
        """通过站台目的地码获取节点"""
        return self._dest_code_to_node.get(dest_code)
    
    def get_nodes_by_station_id(self, station_id: str) -> List[PathStationNode]:
        """
        通过车站ID获取所有节点（可能有多个，如上下行）
        
        返回列表按path_index排序
        """
        nodes = self._station_id_to_nodes.get(station_id, [])
        return sorted(nodes, key=lambda n: n.path_index)
    
    def get_station_id_at_index(self, path_index: int) -> Optional[str]:
        """获取指定path_index的station_id（快捷方法）"""
        node = self.get_node_by_index(path_index)
        return node.station_id if node else None
    
    def get_dest_code_at_index(self, path_index: int) -> Optional[str]:
        """获取指定path_index的dest_code（快捷方法）"""
        node = self.get_node_by_index(path_index)
        return node.dest_code if node else None
    
    def find_matching_node(self, entry_station_id: str, hint_dest_code: Optional[str] = None) -> Optional[PathStationNode]:
        """
        智能匹配节点（用于兼容旧代码迁移）
        
        策略：
        1. 如果提供了hint_dest_code，优先精确匹配dest_code
        2. 否则通过station_id查找，如有多个则返回第一个
        
        Args:
            entry_station_id: entry中的station_id
            hint_dest_code: 提示的dest_code（可选）
        
        Returns:
            匹配的节点，如果没有匹配返回None
        """
        # 策略1: 精确匹配dest_code
        if hint_dest_code:
            node = self.get_node_by_dest_code(hint_dest_code)
            if node and (node.station_id == entry_station_id or node.is_virtual):
                return node
        
        # 策略2: 通过station_id匹配
        nodes = self.get_nodes_by_station_id(entry_station_id)
        if nodes:
            return nodes[0]  # 返回第一个匹配
        
        return None
    
    @property
    def total_nodes(self) -> int:
        """路径节点总数"""
        return len(self.nodes)
    
    @property
    def non_virtual_nodes(self) -> List[PathStationNode]:
        """非虚拟节点列表"""
        return [node for node in self.nodes if not node.is_virtual]
    
    def validate(self) -> Tuple[bool, List[str]]:
        """
        验证索引完整性
        
        Returns:
            (is_valid, error_messages)
        """
        errors = []
        
        # 检查1: path_index连续性
        indices = [node.path_index for node in self.nodes]
        if indices != list(range(len(indices))):
            errors.append(f"path_index不连续: {indices}")
        
        # 检查2: dest_code唯一性
        dest_codes = [node.dest_code for node in self.nodes]
        if len(dest_codes) != len(set(dest_codes)):
            duplicates = [dc for dc in dest_codes if dest_codes.count(dc) > 1]
            errors.append(f"dest_code重复: {set(duplicates)}")
        
        # 检查3: 虚拟节点必须没有station_id
        for node in self.nodes:
            if node.is_virtual and node.station_id:
                errors.append(f"虚拟节点{node.dest_code}不应有station_id: {node.station_id}")
        
        is_valid = len(errors) == 0
        return is_valid, errors
    
    def __repr__(self) -> str:
        virtual_count = sum(1 for node in self.nodes if node.is_virtual)
        return f"PathStationIndex(route={self.route_id}, nodes={len(self.nodes)}, virtual={virtual_count})"
    
    def debug_print(self):
        """打印调试信息"""
        print(f"\n=== {repr(self)} ===")
        for node in self.nodes:
            print(f"  {node}")
        
        is_valid, errors = self.validate()
        if not is_valid:
            print("\n[验证错误]:")
            for error in errors:
                print(f"  - {error}")


def build_path_station_index_from_path(path, rail_info) -> PathStationIndex:
    """
    从Path对象构建PathStationIndex
    
    核心逻辑：
    1. 遍历path.nodeList（dest_code列表）
    2. 通过rail_info.platform_station_map查找每个dest_code对应的station_id
    3. 标记虚拟节点（无法匹配到station的）
    
    Args:
        path: Path对象（包含nodeList, id, path_route_id等）
        rail_info: RailInfo对象（用于查询dest_code -> station映射）
    
    Returns:
        构建好的PathStationIndex
    """
    # Path类使用id作为路径ID，path_route_id作为所属交路ID
    index = PathStationIndex(route_id=path.id)
    
    # 遍历path.nodeList
    for path_idx, dest_code in enumerate(path.nodeList):
        # 通过platform_station_map查找station_id
        station_id = rail_info.platform_station_map.get(dest_code)
        
        if station_id:
            # 找到对应的真实车站
            station = rail_info.stationList.get(station_id)
            station_name = station.name if station else f"站台{dest_code}"
            
            index.add_node(
                path_index=path_idx,
                dest_code=dest_code,
                station_id=station_id,
                station_name=station_name,
                direction=_infer_direction_from_path(path, path_idx),
                is_virtual=False
            )
        else:
            # 虚拟节点（折返轨、出入库等）
            index.add_node(
                path_index=path_idx,
                dest_code=dest_code,
                station_id=None,
                station_name=f"站台{dest_code}",
                direction=None,
                is_virtual=True
            )
    
    return index


def _infer_direction_from_path(path, path_index: int) -> Optional[str]:
    """
    推断方向（基于path属性或其他规则）
    
    TODO: 根据实际path对象的属性完善此逻辑
    """
    # 简单实现：根据path的方向属性
    if hasattr(path, 'direction'):
        return path.direction
    
    # 如果没有明确方向信息，返回None
    return None

