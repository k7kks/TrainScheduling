"""
快慢车运行图自动编制程序 V3

基于发车时间均衡性的快慢车运行图自动编制系统
复用src文件夹的输入输出接口
参考快慢车铺画规则设计的全新算法

主要特点：
1. 复用src的输入输出接口（DataReader、Engineering等）
2. 目标函数以发车时间均衡性为主（参照大小交路）
3. 基于快慢车铺画规则的算法设计
4. 输出格式与大小交路一致
5. 支持快慢车越行、大小交路套跑等功能

Version: 3.0.0
Author: CRRC Urban Rail Transit Team
Date: 2024-10-11
"""

__version__ = "3.0.0"
__author__ = "CRRC Urban Rail Transit Team"

from .main import ExpressLocalSchedulerV3

__all__ = ['ExpressLocalSchedulerV3']

