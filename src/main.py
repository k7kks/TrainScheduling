import sys
import time
from typing import List
from Engineering import Engineering
from Util import util

class main:
    """
    列车调度程序的主类
    负责处理命令行参数和程序流程控制
    """
    # 类变量定义
    debug: bool = False
    # 默认铁路系统信息文件位置
    # ftar: str = "../data/input_data/Schedule-cs4.xml"
    # ftar: str = "../data/input_data/Schedule-wx.xml"
    ftar: str = "../data/input_data/Schedule-fs.xml"
    # 默认高峰期计划信息
    # ftar_setting: str = "../data/input_data/长沙4_大小交路.xml"
    # ftar_setting: str = "../data/input_data/无锡2.xml"
    ftar_setting: str = "../data/input_data/佛山3_test.xml"
    # ftar_setting: str = "../data/input_data/佛山3.xml"
    # 默认输出目录
    dir: str = "../data/output_data/results"
    
    @classmethod
    def parseArg(cls, args: List[str]) -> None:
        """
        解析命令行输入参数的函数
        包括输入文件和需要管理的阶段信息
        """
        if len(args) % 2 != 0:
            print("Wrong input arg format, each arg should be in \"OPTION VALUE\" format")
            sys.exit(0)
            
        print(f"# Args: {len(args)}")
        # 遍历参数
        for i_arg in range(len(args) // 2):
            opt = args[i_arg * 2]
            value = args[i_arg * 2 + 1]
            
            print(f"{i_arg}: {opt} -> {value}")
            
            if opt in ["-r", "--rail_info"]:
                cls.ftar = value
            elif opt in ["-u", "--user_setting"]:
                cls.ftar_setting = value
            elif opt in ["-o", "--output_dir"]:
                cls.dir = value
            elif opt in ["-d", "--debug"]:
                if value in ["true", "1"]:
                    cls.debug = True
                
    @classmethod
    def main(cls, args: List[str]) -> None:
        """
        运行列车调度程序的主函数
        Args:
            args: 命令行参数列表
            param1: 铁路系统信息文件的目录
            param2: 用户输入文件的目录
                两个文件都必须是.xml格式
            param3: 存储输出文件的文件夹目录
        """
        # 获取输入参数并解析到字段
        cls.parseArg(args)
        
        # 创建问题定义（包括铁路系统信息和用户输入）
        read_start = time.time()
        eng = Engineering(cls.debug, cls.ftar, cls.ftar_setting)#这些路径属性需要传到求解类里面

        read_time = time.time() - read_start
        
        # 运行算法
        alg_start = time.time()
        try:
            eng.run_alg()
        except Exception as e:
            print("算法生成时刻表时出错", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(0)
        alg_time = time.time() - alg_start
        
        # 输出包含生成时刻表信息的xls文件
        write_start = time.time()
        # 首先写入xls文件
        eng.write_excel(cls.dir, True)
        # 转换为xlsx格式
        eng.convert_to_xlsx(cls.dir)
        write_time = time.time() - write_start
        
        print(f"{util.ANSI_GREEN} [信息] {util.ANSI_WHITE}读取时间: {read_time}秒")
        print(f"{util.ANSI_GREEN} [信息] {util.ANSI_WHITE}算法运行时间: {alg_time}秒")
        print(f"{util.ANSI_GREEN} [信息] {util.ANSI_WHITE}写入XLSX时间: {write_time}秒")
        print(f"{util.ANSI_GREEN} [信息] {util.ANSI_WHITE}总时间: {read_time + alg_time + write_time}秒")

if __name__ == "__main__":
    main.main(sys.argv[1:])