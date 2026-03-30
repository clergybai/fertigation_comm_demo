from PyQt5.QtWidgets import QComboBox
from serial import (PARITY_NONE, PARITY_EVEN, PARITY_ODD, PARITY_MARK, PARITY_SPACE, FIVEBITS, SIXBITS, SEVENBITS, EIGHTBITS, STOPBITS_ONE, STOPBITS_ONE_POINT_FIVE, STOPBITS_TWO)
from typing import Callable, Any, Optional

from modbus.modbus_rtu import bcd_to_decimal, int_to_float



class BaudrateComboBox(QComboBox):
    """通用的波特率选择下拉框"""
    
    def __init__(self, parent=None, default_baud: int = 9600):
        super().__init__(parent)
        
        self.common_baudrates = [
            300, 600, 1200, 2400, 4800, 9600,
            19200, 38400, 57600, 115200,
            230400, 460800, 921600
        ]
        
        self.setup_ui(default_baud)
    
    def setup_ui(self, default_baud: int):
        """初始化下拉框内容"""
        self.clear()
        
        for baud in self.common_baudrates:
            self.addItem(f"{baud} bps", userData=baud)
        
        self.set_current_baud(default_baud)
        
        self.setMinimumWidth(140)
    
    def set_current_baud(self, baud: int):
        """通过数值设置当前选中的波特率"""
        index = self.findData(baud)
        if index != -1:
            self.setCurrentIndex(index)
        else:
            self.addItem(f"{baud} bps", userData=baud)
            self.setCurrentIndex(self.count() - 1)
    
    def get_current_baud(self) -> int:
        """获取当前选中的波特率数值（推荐使用这个）"""
        return self.currentData()
    
    def get_current_baud_text(self) -> str:
        """获取显示的文字"""
        return self.currentText()


class ParityComboBox(QComboBox):
    """通用的串口校验位选择下拉框"""
    
    def __init__(self, parent=None, default_parity: str = 'N'):
        super().__init__(parent)
        
        self.setup_ui(default_parity)
    
    def setup_ui(self, default_parity: str):
        """初始化下拉框"""
        self.clear()
        
        # 定义常用校验位（显示名称 + 实际 serial 库使用的常量）
        parity_options = [
            ("None",     PARITY_NONE,  "N"),
            ("Even",     PARITY_EVEN,  "E"),
            ("Odd",      PARITY_ODD,   "O"),
            ("Mark",              PARITY_MARK,  "M"),
            ("Space",             PARITY_SPACE, "S"),
        ]
        
        for display_text, parity_const, short_name in parity_options:
            # 显示给用户看的文字
            self.addItem(display_text, userData=parity_const)
        
        # 设置默认值（常用是 None）
        self.set_current_parity(default_parity)
        
        self.setMinimumWidth(180)   # 让下拉框显示完整文字
    
    def set_current_parity(self, parity: str):
        """
        通过字符设置当前校验位
        支持传入: 'N', 'E', 'O', 'M', 'S' 或直接传入 serial 常量
        """
        parity_map = {
            'N': PARITY_NONE,
            'E': PARITY_EVEN,
            'O': PARITY_ODD,
            'M': PARITY_MARK,
            'S': PARITY_SPACE,
            PARITY_NONE:  PARITY_NONE,
            PARITY_EVEN:  PARITY_EVEN,
            PARITY_ODD:   PARITY_ODD,
            PARITY_MARK:  PARITY_MARK,
            PARITY_SPACE: PARITY_SPACE,
        }
        
        target = parity_map.get(parity, PARITY_NONE)
        
        index = self.findData(target)
        if index != -1:
            self.setCurrentIndex(index)
    
    def get_current_parity(self):
        """返回 serial 库可直接使用的校验位常量（推荐使用）"""
        return self.currentData()
    
    def get_current_parity_name(self) -> str:
        """返回显示的文字"""
        return self.currentText()


class DataBitsComboBox(QComboBox):
    """通用的串口数据位选择下拉框（默认 8 位）"""
    
    def __init__(self, parent=None, default_data_bits: int = 8):
        super().__init__(parent)
        self.setup_ui(default_data_bits)
    
    def setup_ui(self, default_data_bits: int):
        """初始化下拉框内容"""
        self.clear()
        
        # 标准数据位选项
        options = [
            ("5 bit", FIVEBITS),
            ("6 bit", SIXBITS),
            ("7 bit", SEVENBITS),
            ("8 bit", EIGHTBITS),      # 最常用
        ]
        
        for text, value in options:
            self.addItem(text, userData=value)
        
        # 设置默认选中 8 位
        self.set_current_data_bits(default_data_bits)
        
        # 调整宽度，让文字完整显示
        self.setMinimumWidth(130)
    
    def set_current_data_bits(self, bits: int):
        """设置当前选中的数据位"""
        index = self.findData(bits)
        if index >= 0:
            self.setCurrentIndex(index)
        else:
            # 如果传入非标准值，自动添加
            self.addItem(f"{bits} bit", userData=bits)
            self.setCurrentIndex(self.count() - 1)
    
    def get_current_data_bits(self) -> int:
        """获取当前选中的数据位数值，可直接用于 serial.Serial(bytesize=...)"""
        return self.currentData()
    
    def get_current_text(self) -> str:
        """获取显示的文字"""
        return self.currentText()


class StopBitsComboBox(QComboBox):
    """通用的串口停止位选择下拉框（默认 1 位）"""
    
    def __init__(self, parent=None, default_stop_bits: float = 1):
        super().__init__(parent)
        self.setup_ui(default_stop_bits)
    
    def setup_ui(self, default_stop_bits: float):
        """初始化下拉框"""
        self.clear()
        
        # 常用停止位选项
        options = [
            ("1",   STOPBITS_ONE),
            ("1.5", STOPBITS_ONE_POINT_FIVE),
            ("2",   STOPBITS_TWO),
        ]
        
        for display_text, stop_const in options:
            self.addItem(display_text, userData=stop_const)
        
        self.set_current_stop_bits(default_stop_bits)
        
        self.setMinimumWidth(130)
    
    def set_current_stop_bits(self, stop_bits: float):
        """通过数值设置当前停止位"""
        index = self.findData(stop_bits)
        if index >= 0:
            self.setCurrentIndex(index)
        else:
            self.addItem(f"{stop_bits} stopbits", userData=stop_bits)
            self.setCurrentIndex(self.count() - 1)
    
    def get_current_stop_bits(self):
        """返回 serial 库可直接使用的停止位常量"""
        return self.currentData()
    
    def get_current_text(self) -> str:
        """返回显示的文字"""
        return self.currentText()

class ConverterComboBox(QComboBox):
    """
    数据转换类型选择下拉框
    选项：Raw Data / To Int / To Float
    """
    
    def __init__(self, parent=None, default_index: int = 1):   # 默认选中 To Int
        super().__init__(parent)
        self.setup_ui(default_index)
    
    def setup_ui(self, default_index: int):
        self.clear()
        
        self.options = [
            ("Raw Data",  None,          "不进行转换，显示原始寄存器值"),
            ("To Int",    bcd_to_decimal,           "转换为整数"),
            ("To Float",  int_to_float,         "转换为浮点数"),
        ]
        
        for display_text, converter_func, tooltip in self.options:
            self.addItem(display_text)
            self.setItemData(self.count() - 1, {
                "converter": converter_func,
                "tooltip": tooltip
            })
        
        # 设置默认选中项（默认选中 To Int）
        self.setCurrentIndex(default_index)
        
        self.setMinimumWidth(120)
        self.setToolTip("Select data conversion method")
        
        self.currentIndexChanged.connect(self._on_index_changed)
    
    def _on_index_changed(self, index: int):
        """当选择变化时，更新 tooltip"""
        if index >= 0:
            data = self.itemData(index)
            if data and "tooltip" in data:
                self.setToolTip(data["tooltip"])
    
    def get_converter(self) -> Optional[Callable[[Any], Any]]:
        """获取当前选中的转换函数"""
        data = self.itemData(self.currentIndex())
        if data:
            return data.get("converter")
        return None
    
    def get_converter_name(self) -> str:
        """获取当前选中的显示名称"""
        return self.currentText()
    
    def get_current_option(self) -> dict:
        """获取当前选项的完整信息"""
        data = self.itemData(self.currentIndex())
        return {
            "name": self.currentText(),
            "converter": data.get("converter") if data else None,
            "index": self.currentIndex()
        }