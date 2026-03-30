from PyQt5.QtWidgets import QSpinBox
from PyQt5.QtCore import Qt


class SlaveIdSpinBox(QSpinBox):
    """Modbus Slave ID 输入框（默认值为 1，范围 1~247）"""
    
    def __init__(self, parent=None, default_slave_id: int = 1):
        super().__init__(parent)
        self.setup_ui(default_slave_id)
    
    def setup_ui(self, default_value: int):
        """初始化配置"""
        self.setRange(1, 247)           # Modbus 标准范围
        self.setValue(default_value)    # 设置默认值
        self.setSingleStep(1)           # 步长为1
        self.setWrapping(False)         # 不循环
        
        self.setMinimumWidth(110)
        self.setAlignment(Qt.AlignCenter)
        self.setSuffix("  ")           # 轻微右边距
        
        self.setToolTip("Modbus Slave ID (1 ~ 247)")
    
    def get_slave_id(self) -> int:
        """获取当前 Slave ID"""
        return self.value()
    
    def set_slave_id(self, slave_id: int):
        """外部设置 Slave ID（自动限制范围）"""
        self.setValue(max(1, min(247, slave_id)))