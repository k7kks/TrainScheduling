import xml.etree.ElementTree as ET
from typing import Optional
from UserSetting import UserSetting
from RailInfo import RailInfo
from Station import Station
from Path import Path

class DataReader:
    """
    DataReader类用于读取用户设置和铁路信息文件：即读取两个xml
    """
    
    def __init__(self, debug: bool):
        """构造函数"""
        self.debug_mode = debug
        DataReader.debug_mode = debug  # 同时更新类变量
        # print(f"self.debug_mode ={self.debug_mode}")
        # 是否输出调试信息的标志

    @staticmethod
    def read_setting_file(fdir: str) -> UserSetting:#### 按最新版main的接口去修改
        """
        从指定目录读取用户设置xml文件，并返回包含所有信息的UserSetting对象
        Args:
            fdir: 指向要读取文件的目录字符串
        Returns:
            UserSetting: 包含所有用户设置信息的对象
            - fdir: str 表示参数 fdir 的类型是字符串（str）
            -> UserSetting 表示函数返回值的类型是 UserSetting 类型
        """
        us = UserSetting()
        
        try:
            # 使用ElementTree解析XML
            tree = ET.parse(fdir)
            root = tree.getroot()
            
            # Step1.解析场段信息(可用车辆数和可停车辆数)
            if DataReader.debug_mode:
                print("-----------------Parsing Depot info-----------------")      
            depots_info = root.find('DepotsInfo')  #新版xml文件里面暂时没这个信息，后续可能要改
            if depots_info is not None:
                for depot in depots_info.findall('DepotInfo'):
                    depot_id = depot.find('DepotId').text
                    train_num = depot.find('UsableTrainNum').text
                    parking_cap = depot.find('CanParkedTrainNum').text
                    
                    us.addDepot(depot_id, train_num, parking_cap)
                    
                    if DataReader.debug_mode:
                        print(f"Depot ID: {depot_id} Train capacity:{train_num} Parking capacity:{parking_cap}")
            # # Step2.解析出入库路径信息
            # if DataReader.debug_mode:
            #     print("-----------------Parsing Depot Routes----------------")
            # depot_routes = root.find('DepotRoutesParameter')
            # if depot_routes is not None:
            #     # 创建一个字典，用于按RouteCategoryId分组存储路线信息
            #     route_category_dict = {}
                
            #     for route in depot_routes.findall('DepotRouteParameter'):
            #         # 解析路由类别ID
            #         route_category_id = route.find('RouteCategoryId').text
                    
            #         # 解析方向属性
            #         up_or_down = route.find('UpOrDown').text == 'true'
            #         out_or_in = route.find('OutOrIn').text == 'true'
                    
            #         # 生成方向和出入库描述
            #         direction = 'Up' if up_or_down else 'Down'
            #         in_out = 'Out' if out_or_in else 'In'
                    
            #         # 解析路径详情
            #         route_details = []
            #         for detail in route.findall('.//RouteDetail'):  # 使用XPath语法进行更灵活的查找
            #             route_ids_node = detail.find('RouteIds')
            #             if route_ids_node is not None and route_ids_node.text:
            #                 # 处理带空格的逗号分隔符（如"123, 456"）
            #                 ids_str = route_ids_node.text.replace(' ', '')
            #                 ids = [int(id_str) for id_str in ids_str.split(',') if id_str]
            #             else:
            #                 ids = []  # 默认空数组
                        
            #             # 安全获取Used节点
            #             used_node = detail.find('Used')
            #             used = used_node.text == 'true' if used_node is not None else False
                        
            #             route_details.append({
            #                 'route_ids': ids,
            #                 'used': used
            #             })
                    
            #         if route_details:  # 只有当有路径详情时才处理
            #             # 如果该路由类别ID尚未在字典中，则初始化
            #             if route_category_id not in route_category_dict:
            #                 route_category_dict[route_category_id] = {
            #                     'up_in': [],
            #                     'down_in': [],
            #                     'up_out': [],
            #                     'down_out': []
            #                 }
                        
            #             # 根据方向和出入库类型，将路线ID添加到相应的列表中
            #             if direction == 'Up' and in_out == 'Out':
            #                 route_category_dict[route_category_id]['up_out'] = route_details[0]['route_ids']
            #             elif direction == 'Down' and in_out == 'Out':
            #                 route_category_dict[route_category_id]['down_out'] = route_details[0]['route_ids']
            #             elif direction == 'Up' and in_out == 'In':
            #                 route_category_dict[route_category_id]['up_in'] = route_details[0]['route_ids']
            #             elif direction == 'Down' and in_out == 'In':
            #                 route_category_dict[route_category_id]['down_in'] = route_details[0]['route_ids']
                
            #     # 遍历字典，为每个路由类别创建一个DepotRoutesInfo对象
            #     for route_category_id, routes in route_category_dict.items():
            #         us.addDepotRoutes(
            #             'Up', 'Out',  # 这两个参数在DepotRoutesInfo中实际上只是标记，不影响功能
            #             routes['up_in'],
            #             routes['down_in'],
            #             routes['up_out'],
            #             routes['down_out']
            #         )
                    
            #         if DataReader.debug_mode:
            #             print(f"Route Category ID: {route_category_id}")
            #             print(f"  Up In: {routes['up_in']}, Down In: {routes['down_in']}")
            #             print(f"  Up Out: {routes['up_out']}, Down Out: {routes['down_out']}")
                        
            #     # 打印depot_routes_infos的维度
            #     if DataReader.debug_mode:
            #         print(f"Total depot_routes_infos count: {len(us.depot_routes_infos)}")
            # Step2.解析出入库路径信息
            if DataReader.debug_mode:
                print("-----------------Parsing Depot Routes----------------")
            depot_routes = root.find('DepotRoutesParameter')
            if depot_routes is not None:
                # 创建一个字典，用于按RouteCategoryId分组存储路线信息
                route_category_dict = {}
                
                for route in depot_routes.findall('DepotRouteParameter'):
                    # 解析路由类别ID
                    route_category_id = route.find('RouteCategoryId').text
                    
                    # 解析方向属性
                    up_or_down = route.find('UpOrDown').text == 'true'
                    out_or_in = route.find('OutOrIn').text == 'true'
                    
                    # 生成方向和出入库描述
                    direction = 'Up' if up_or_down else 'Down'
                    in_out = 'Out' if out_or_in else 'In'
                    
                    # 解析路径详情
                    route_details = []
                    for detail in route.findall('.//RouteDetail'):  # 使用XPath语法进行更灵活的查找
                        route_ids_node = detail.find('RouteIds')
                        if route_ids_node is not None and route_ids_node.text:
                            # 处理带空格的逗号分隔符（如"123, 456"）
                            ids_str = route_ids_node.text.replace(' ', '')
                            ids = [int(id_str) for id_str in ids_str.split(',') if id_str]
                        else:
                            ids = []  # 默认空数组
                        
                        # 读取RouteType属性
                        route_type_node = detail.find('RouteType')
                        route_type = route_type_node.text if route_type_node is not None else "default"
                        
                        # 安全获取Used节点
                        used_node = detail.find('Used')
                        used = used_node.text == 'true' if used_node is not None else False
                        
                        route_details.append({
                            'route_ids': ids,
                            'route_type': route_type,
                            'used': used
                        })
                    
                    if route_details:  # 只有当有路径详情时才处理
                        # 如果该路由类别ID尚未在字典中，则初始化
                        if route_category_id not in route_category_dict:
                            route_category_dict[route_category_id] = {
                                'up_in': [],
                                'down_in': [],
                                'up_out': [],
                                'down_out': [],
                                'up_in_type': "default",
                                'down_in_type': "default",
                                'up_out_type': "default",
                                'down_out_type': "default"
                            }
                        
                        # 根据方向和出入库类型，将路线ID和路线类型添加到相应的列表中
                        if direction == 'Up' and in_out == 'Out':
                            route_category_dict[route_category_id]['up_out'] = route_details[0]['route_ids']
                            route_category_dict[route_category_id]['up_out_type'] = route_details[0]['route_type']
                        elif direction == 'Down' and in_out == 'Out':
                            route_category_dict[route_category_id]['down_out'] = route_details[0]['route_ids']
                            route_category_dict[route_category_id]['down_out_type'] = route_details[0]['route_type']
                        elif direction == 'Up' and in_out == 'In':
                            route_category_dict[route_category_id]['up_in'] = route_details[0]['route_ids']
                            route_category_dict[route_category_id]['up_in_type'] = route_details[0]['route_type']
                        elif direction == 'Down' and in_out == 'In':
                            route_category_dict[route_category_id]['down_in'] = route_details[0]['route_ids']
                            route_category_dict[route_category_id]['down_in_type'] = route_details[0]['route_type']
                
                # 遍历字典，为每个路由类别创建一个DepotRoutesInfo对象
                for route_category_id, routes in route_category_dict.items():
                    # 创建带有路线类型的路线字符串，即使路线为空也要包含类型信息
                    # 确保即使路线列表为空，也能正确传递路线类型信息
                    # 如果路线列表为空，添加一个占位符，以确保字符串格式正确
                    up_in_str = f"{routes['up_in_type']}:" + (",".join(map(str, routes['up_in'])) if routes['up_in'] else "empty")
                    down_in_str = f"{routes['down_in_type']}:" + (",".join(map(str, routes['down_in'])) if routes['down_in'] else "empty")
                    up_out_str = f"{routes['up_out_type']}:" + (",".join(map(str, routes['up_out'])) if routes['up_out'] else "empty")
                    down_out_str = f"{routes['down_out_type']}:" + (",".join(map(str, routes['down_out'])) if routes['down_out'] else "empty")
                    
                    us.addDepotRoutes(
                        'Up', 'Out',  # 这两个参数在DepotRoutesInfo中实际上只是标记，不影响功能
                        up_in_str,
                        down_in_str,
                        up_out_str,
                        down_out_str
                    )
                    
                    if DataReader.debug_mode:
                        print(f"Route Category ID: {route_category_id}")
                        print(f"  Up In: {up_in_str}, Down In: {down_in_str}")
                        print(f"  Up Out: {up_out_str}, Down Out: {down_out_str}")
                        
                # 打印depot_routes_infos的维度
                if DataReader.debug_mode:
                    print(f"Total depot_routes_infos count: {len(us.depot_routes_infos)}")

            # Step3.解析各峰期信息
            first_set = False
            if DataReader.debug_mode:
                print("--------------------Parsing Peak info-------------------")
                
            peaks_param = root.find('PeaksParameter')
            if peaks_param is not None:
                for peak in peaks_param.findall('PeakParameter'):
                    # 峰期起始时间
                    peak_time_start = peak.find('StartTime').text
                    if not first_set:
                        first_set = True
                        us.setFirstCarTime(peak_time_start)
                        
                    # 峰期结束时间    
                    peak_time_end = peak.find('EndTime').text
                    us.setLastCarTime(peak_time_end)
                    
                    # 上下行路径信息
                    route_cat1 = peak.find('RouteCategory1').text
                    up_route1 = peak.find('UpRoute1').text
                    dn_route1 = peak.find('DownRoute1').text

                    # route_cat2 = peak.find('RouteCategory2').text
                    # up_route2 = peak.find('UpRoute2').text
                    # dn_route2 = peak.find('DownRoute2').text

                    # 安全获取第二条路径信息，如果不存在则设置默认值
                    route_cat2_node = peak.find('RouteCategory2')
                    route_cat2 = route_cat2_node.text if route_cat2_node is not None else "-1"
                    up_route2_node = peak.find('UpRoute2')
                    up_route2 = up_route2_node.text if up_route2_node is not None else "-1"
                    dn_route2_node = peak.find('DownRoute2')
                    dn_route2 = dn_route2_node.text if dn_route2_node is not None else "-1"

                    # 运营参数
                    # or_rate1 = peak.find('OperaRate1').text
                    # or_rate2 = peak.find('OperaRate2').text
                    # 安全获取运营参数
                    or_rate1_node = peak.find('OperaRate1')
                    or_rate1 = or_rate1_node.text if or_rate1_node is not None else "-1"
                    
                    or_rate2_node = peak.find('OperaRate2')
                    or_rate2 = or_rate2_node.text if or_rate2_node is not None else "-1"
                    perf_lvl = peak.find('PerformalLevelId').text
                    train_num = peak.find('TrainNum').text
                    interval = peak.find('Interval').text
                    forbid = peak.find('ForbiddenDepotId').text
                    #大小交路各自运用的列车数
                    num1 = int(peak.find('TrainNum1').text)
                    num2= int(peak.find('TrainNum2').text)
                    us.addPeak(peak_time_start, peak_time_end,
                              route_cat1, up_route1, dn_route1,
                              route_cat2, up_route2, dn_route2,
                              or_rate1, or_rate2, perf_lvl,
                              train_num,num1,num2, interval, forbid)
                              
                    if DataReader.debug_mode:
                        print(f"Peak interval: {peak_time_start} ~ {peak_time_end} Train numbers:{train_num} Interval:{interval}")
                        
        except ET.ParseError as e:
            print("Error: Malformed XML file")
            print(e)
            raise
        except IOError as e:
            print("Error: Issue with the XML file (not found, inaccessible, etc.)")
            print(e)
            raise
        except Exception as e:
            print("General error occurred:: Setting file")
            print(e)
            raise
            
        return us
        
    @staticmethod
    def read_file(fdir: str) -> RailInfo:
        """
        从指定目录读取铁路信息xml文件，并返回包含所有信息的RailInfo对象
        Args:
            fdir: 指向要读取文件的目录字符串
        Returns:
            RailInfo: 包含所有铁路网格信息的对象
        """
        prob_def = RailInfo(DataReader.debug_mode)
        
        try:
            # 使用ElementTree解析XML
            tree = ET.parse(fdir)
            root = tree.getroot()
            
            # 解析通用信息
            if DataReader.debug_mode:
                print("------------------Parsing General info---------------------")
                
            general_info = root.find('GeneralInfo')
            if general_info is not None:
                version = general_info.find('Version').text
                if DataReader.debug_mode:
                    print(f"Version: {version}")
                    
            # 解析站点信息
            if DataReader.debug_mode:
                print("-----------------Parsing Station info--------------------")
                
            station_info = root.find('StationInfo')
            if station_info is not None:
                for station in station_info.findall('Station'):
                    # 站点基本信息
                    station_id = station.find('Id').text
                    station_name = station.find('Name').text
                    abbv_name = station.find('AbbrName').text if station.find('AbbrName') is not None else ""
                    station_type = station.find('Type').text
                    current_kp = station.find('CenterKp').text
                    is_equip_station = station.find('IsEquimentStation').text
                    #创建Station对象
                    station_tmp = Station(station_id, station_name, abbv_name,
                                                 station_type, current_kp, is_equip_station)
                                                 
                    if DataReader.debug_mode:
                        print(f"Station ID: {station_id} Station name:{station_name}")
                        print(f"     abbrv name:{abbv_name} Station type:{station_type}")
                        print(f"     current kp:{current_kp} equip station:{is_equip_station}")
                    
                    # 解析站台信息
                    for platform in station.findall('./Platforms/Platform'):
                        platform_id = platform.find('Id').text
                        platform_name = platform.find('Name').text
                        platform_type = platform.find('Type').text
                        platform_dir = platform.find('Direction').text
                        is_virtual = platform.find('IsVirtual').text
                        dest_code = platform.find('Destcode').text
                        
                        link_plat = ""
                        if platform.find('LinkPlatform') is not None:
                            link_plat = platform.find('LinkPlatform').text
                            
                        default_time = platform.find('DefaultDwellTime').text
                        default_pl = platform.find('DefaultPL').text
                        depot_id = ""
                        if platform.find('DepotId') is not None:
                            depot_id = platform.find('DepotId').text#获取所属场段的ID
                        min_track_time = "0"
                        if platform.find('MinimumTrackTime') is not None:
                            min_track_time = platform.find('MinimumTrackTime').text
                            
                        min_dwell_time = "0"
                        if platform.find('MinimumDwellTime') is not None:
                            min_dwell_time = platform.find('MinimumDwellTime').text
                            
                        max_dwell_time = "0"
                        if platform.find('MaximumDwellTime') is not None:
                            max_dwell_time = platform.find('MaximumDwellTime').text
                            
                        station_tmp.addPlatform(platform_id, platform_name, platform_type,
                                              platform_dir, is_virtual, dest_code, link_plat,
                                              default_time, default_pl, min_track_time,
                                              min_dwell_time, max_dwell_time,depot_id)
                                              
                        if DataReader.debug_mode:
                            print(f"    platform ID: {platform_id} platform name:{platform_name}")
                            print(f"    platform type:{platform_type} platform dir:{platform_dir}")
                            print(f"    virtual?:{is_virtual} destinition code:{dest_code}")
                            print(f"    default time:{default_time} default plan:{default_pl}")
                            
                    # 解析调头信息
                    for turnback in station.findall('./TurnbackModes/TurnbackMode'):
                        turnback_id = turnback.find('Id').text
                        turnback_name = turnback.find('Name').text
                        show_name = turnback.find('ShowName').text
                        tb_dest_code = turnback.find('TurnbackDestcode').text
                        min_tb_time = turnback.find('MinimumTurnbackTime').text
                        def_tb_time = turnback.find('DefaultTurnbackTime').text
                        max_tb_time = turnback.find('MaximumTurnbackTime').text
                        
                        station_tmp.addTurnback(turnback_id, turnback_name, show_name,
                                              tb_dest_code, min_tb_time, def_tb_time, max_tb_time)
                                              
                        if DataReader.debug_mode:
                            print(f"   !turnback ID: {turnback_id} platform name:{turnback_name}")
                            print(f"   show name:{show_name} destinition code:{tb_dest_code}")
                            print(f"   min time:{min_tb_time} default time:{def_tb_time}")
                            print(f"   max time:{max_tb_time}")
                            
                    prob_def.addStation(station_tmp)
                    
            # 解析路线信息
            if DataReader.debug_mode:
                print("--------------------Parsing route info----------------------")
                
            route_info = root.find('RouteInfo')
            if route_info is not None:
                for route in route_info.findall('.//Routes/Route'):
                    route_id = route.find('Id').text
                    route_name = route.find('Name').text
                    up_route = route.find('DefaultUpRouteId').text
                    down_route = route.find('DefaultDownRouteId').text
                    
                    prob_def.addRoute(route_id, route_name, up_route, down_route)
                    
                    if DataReader.debug_mode:
                        print(f"   *route ID: {route_id} route name:{route_name}")
                        print(f"   up_route_:{up_route} down_route_:{down_route}")
                # 提取路径信息,每个路由可以有多个从站点A到站点B的路径
                for path in route_info.findall('.//Paths/Path'):
                    path_id = path.find('Id').text
                    route_name = path.find('Name').text
                    path_route_id = path.find('RouteId').text
                    dir = path.find('Direction').text
                    is_reverse = path.find('IsReverse').text
                    
                    path_tmp = Path(path_id, route_name, path_route_id, dir, is_reverse)
                    
                    if DataReader.debug_mode:
                        print(f"   --path ID: {path_id} path name:{route_name}")
                        print(f"   path-route ID:{path_route_id} direction:{dir}")
                        print(f"     is reverse:{is_reverse}")
                        
                    # 解析该路径经过的所有platform的destcode
                    for dest in path.findall('./DestcodesOfPath/Destcode'):
                        dest_code = dest.find('Destcode')
                        if dest_code is not None:
                            dest_code_text = dest_code.text
                            path_tmp.addNode(dest_code_text)
                            if DataReader.debug_mode:
                                print(f"      /dest code: {dest_code_text}")
                                
                    if DataReader.debug_mode:
                        print(f" -- Added: {len(path_tmp.nodeList)} dests!")
                        
                    prob_def.addPath(path_tmp)
                        
                    if DataReader.debug_mode:
                        print(f"! Added: {len(prob_def.pathList)} Paths!")  

            # 解析运行等级信息
            if DataReader.debug_mode:
                print("----------------------------Parsing PerformanceLevel info-------------------------")
                
            perf_level_info = root.find('PerformanceLevelInfo')
            if perf_level_info is not None:
                # 提取性能等级信息
                for perf in perf_level_info.findall('.//PerformanceLevels/PerformanceLevel'):
                    # 解析性能等级节点信息
                    # 这主要是性能等级ID和名称之间的关系
                    # 同时包含性能等级的顺序(哪个是最快的)
                    perf_id = perf.find('Id').text
                    perf_name = perf.find('Name').text
                    speed = perf.find('Speed').text
                    
                    prob_def.addPerfLevel(perf_id, perf_name, speed)
                    
                    if DataReader.debug_mode:
                        print(f"   --perf lv ID: {perf_id}"
                              f"   perf lv name:{perf_name}"
                              f"   speed:{speed}")
                              
                if DataReader.debug_mode:
                    print(f"! Added: {len(prob_def.speedLevels_name)} Performance levels!")
                    
                # 提取性能等级信息(不同性能等级下两个站台之间的运行时间)
                add_time = 0
                for pbs in perf_level_info.findall('.//PerformanceLevelsBetweenStation/PerformanceLevelBetweenStation'):
                    # 解析性能等级节点信息
                    # 重要字段:
                    #     StartDestcode (出发站台)
                    #     EndDestcode (到达站台)
                    #     [RunTime...] (每个对应运行等级的运行时间)
                    start_id = pbs.find('StartDestcode').text
                    dest_id = pbs.find('EndDestcode').text
                    
                    # if DataReader.debug_mode:
                    #     print(f"   []start ID: {start_id}"
                    #           f"   dest ID:{dest_id}")
                              
                    # 解析每个性能等级对应的运行时间
                    for dest in pbs.findall('RunTimeOfPerformanceLevel'):
                        perf_lv_id = dest.find('PerformanceLevelId').text
                        run_time = dest.find('RunTime').text
                        
                        prob_def.addTravelInterval(start_id, dest_id, perf_lv_id, run_time)
                        add_time += 1
                        
                        # if DataReader.debug_mode:
                        #     print(f"   {{perf_lv_ID_: {perf_lv_id}"
                        #           f"   run_time_:{run_time}")
                                  
                if DataReader.debug_mode:
                    print(f"! Added: {len(prob_def.travel_time_map)} interval time!    ----  {add_time}")            
        except ET.ParseError as e:
            print("Error: Malformed XML file")
            print(e)
            raise
        except IOError as e:
            print("Error: Issue with the XML file (not found, inaccessible, etc.)")
            print(e)
            raise
        except Exception as e:
            print("General error occurred:: Rail info file")
            print(e)
            raise
            
        return prob_def