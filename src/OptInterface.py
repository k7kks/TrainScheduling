from typing import Dict, List, Optional
import sys
from gurobipy import GRB, Model, Env
from clp import CLP, CLPVariable, CLPExpression
from .util import util

class OptInterface:
    """
    OptInterface类提供了Gurobi和CLP两种优化求解器的统一接口。
    支持:
    - 创建和销毁模型
    - 添加变量和约束
    - 求解优化问题
    - 获取求解结果
    """
    
    def __init__(self, solver_type: str = "CLP"):
        """
        构造函数
        Args:
            solver_type: 求解器类型,可选"Gurobi"或"CLP"
        """
        # Gurobi字段
        self.env: Optional[Env] = None
        self.modelGRB: Optional[Model] = None
        
        # 全局属性
        self.solver_type: str = solver_type
        self.Str2VarGRB: Dict[str, GRB.Var] = {}
        self.Str2VarCLP: Dict[str, CLPVariable] = {}
        
        # CLP字段
        self.clp: Optional[CLP] = None
        self.clp_status = None
        
    def create_model(self) -> None:
        """创建优化模型"""
        if self.solver_type == "Gurobi":
            try:
                self.env = Env(True)
                self.env.start()
                # 创建空模型
                self.modelGRB = Model(env=self.env)
            except Exception as e:
                print(e)
        elif self.solver_type == "CLP":
            self.clp = CLP().minimization()
            
    def dispose(self) -> None:
        """释放模型资源"""
        if self.solver_type == "Gurobi":
            try:
                if self.modelGRB:
                    self.modelGRB.dispose()
                if self.env:
                    self.env.dispose()
            except Exception as e:
                print(e)
        elif self.solver_type == "CLP":
            if self.clp:
                self.clp.reset()
            self.clp_status = None
            
    def build(self) -> None:
        """清空变量映射"""
        self.Str2VarGRB.clear()
        self.Str2VarCLP.clear()
        
    def writeModel(self, fnm: str = "model.lp") -> None:
        """
        将模型写入文件
        Args:
            fnm: 输出文件名
        """
        if self.solver_type == "Gurobi":
            try:
                util.pf("Writing model")
                if self.modelGRB:
                    self.modelGRB.write(fnm)
            except Exception as e:
                util.pf("ERROR:::Writing model")
                print(e)
        elif self.solver_type == "CLP":
            try:
                if self.clp:
                    lp_string = str(self.clp)
                    with open(fnm, 'a') as f:
                        f.write(lp_string)
            except Exception as e:
                print(e)
                sys.exit(0)
                
    def addVar_(self, lb: float, ub: float, obj: float, 
                var_type: str, var_name: str) -> None:
        """
        添加变量
        Args:
            lb: 下界
            ub: 上界
            obj: 目标函数系数
            var_type: 变量类型
            var_name: 变量名
        """
        if self.solver_type == "Gurobi":
            try:
                if self.modelGRB:
                    id_Var = self.modelGRB.addVar(lb, ub, obj, var_type, var_name)
                    self.Str2VarGRB[var_name] = id_Var
            except Exception as e:
                print(e)
        elif self.solver_type == "CLP":
            if self.clp:
                id_Var = self.clp.addVariable()
                id_Var.bounds(lb, ub)
                if var_name:
                    id_Var.name(var_name)
                id_Var.obj(obj)
                self.Str2VarCLP[var_name] = id_Var
                
    def checkHasVar_(self, var_name: str) -> bool:
        """
        检查变量是否存在
        Args:
            var_name: 变量名
        Returns:
            是否存在该变量
        """
        if self.solver_type == "Gurobi":
            return var_name in self.Str2VarGRB
        elif self.solver_type == "CLP":
            return var_name in self.Str2VarCLP
        return False
        
    def addConstr_(self, vnms: List[str], coeffs: List[float], 
                   sense: str, rhs: float, cons_name: str) -> None:
        """
        添加约束
        Args:
            vnms: 变量名列表
            coeffs: 系数列表
            sense: 约束类型 (<,>,=)
            rhs: 右侧常数
            cons_name: 约束名
        """
        if self.solver_type == "Gurobi":
            try:
                if self.modelGRB:
                    # 创建线性表达式
                    expr_tb_time = 0
                    for i, vname in enumerate(vnms):
                        v = self.Str2VarGRB[vname]
                        expr_tb_time += coeffs[i] * v
                    self.modelGRB.addConstr(expr_tb_time, sense, rhs, cons_name)
            except Exception as e:
                for i, vname in enumerate(vnms):
                    v = self.Str2VarGRB[vname]
                    print(f"{vname}  {v}")
                print(e)
                sys.exit(0)
        elif self.solver_type == "CLP":
            if self.clp:
                cons = self.clp.createExpression()
                for i, vname in enumerate(vnms):
                    v = self.Str2VarCLP[vname]
                    cons.add(coeffs[i], v)
                if sense == '<':
                    cons.leq(rhs)
                elif sense == '>':
                    cons.geq(rhs)
                elif sense == '=':
                    cons.eq(rhs)
                    
    def retrieve_X(self, varName: str) -> int:
        """
        获取整数变量的解
        Args:
            varName: 变量名
        Returns:
            变量的整数解
        """
        res = 0
        if self.solver_type == "Gurobi":
            try:
                v = self.Str2VarGRB[varName]
                res = round(v.X)
            except Exception as e:
                print(e)
                sys.exit(0)
        elif self.solver_type == "CLP":
            v = self.Str2VarCLP[varName]
            res = round(v.getSolution())
        return res
        
    def retrieve_realX(self, varName: str) -> float:
        """
        获取实数变量的解
        Args:
            varName: 变量名
        Returns:
            变量的实数解
        """
        res = 0.0
        if self.solver_type == "Gurobi":
            try:
                v = self.Str2VarGRB[varName]
                res = v.X
            except Exception as e:
                print(e)
                sys.exit(0)
        elif self.solver_type == "CLP":
            v = self.Str2VarCLP[varName]
            res = v.getSolution()
        return res
        
    def optimize(self) -> None:
        """执行优化求解"""
        if self.solver_type == "Gurobi":
            try:
                if self.modelGRB:
                    self.modelGRB.optimize()
            except Exception as e:
                print(e)
        elif self.solver_type == "CLP":
            if self.clp:
                self.clp_status = self.clp.solve()
                
    def getobjval(self) -> float:
        """
        获取目标函数值
        Returns:
            目标函数的最优值
        """
        objval = 0.0
        if self.solver_type == "Gurobi":
            try:
                if self.modelGRB:
                    objval = self.modelGRB.ObjVal
            except Exception as e:
                print(e)
                sys.exit(1)
        elif self.solver_type == "CLP":
            if self.clp:
                objval = self.clp.getObjectiveValue()
        return objval
        
    def isSolved2Opt(self) -> bool:
        """
        检查是否求得最优解
        Returns:
            是否找到最优解
        """
        if self.solver_type == "Gurobi":
            stat = -1
            try:
                if self.modelGRB:
                    stat = self.modelGRB.Status
            except Exception as e:
                print(e)
                sys.exit(1)
            return stat == GRB.OPTIMAL
        elif self.solver_type == "CLP":
            return self.clp_status == CLP.STATUS.OPTIMAL
        return False