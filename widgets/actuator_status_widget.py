from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt


class ActuatorStatusWidget(QWidget):
    """单个 Actuator 的状态显示控件（一排小方块）"""
    
    def __init__(self, device_id: str, states: list, parent=None):
        super().__init__(parent)
        self.device_id = device_id
        self.states = states or []
        
        self.init_ui()
    
    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)
        
        # Device ID 标签
        id_label = QLabel(f"{self.device_id[:8]}:")
        id_label.setStyleSheet("color: #aaaaaa; font-size: 14px; min-width: 90px;")
        layout.addWidget(id_label)
        
        # 显示每个通道的小方块
        for i, state in enumerate(self.states):
            square = QLabel()
            square.setFixedSize(28, 28)
            square.setAlignment(Qt.AlignCenter)
            
            if state:  # True → 实心绿色
                square.setStyleSheet("""
                    background-color: #00ff88;
                    border: 2px solid #00cc66;
                    border-radius: 4px;
                    color: #004d00;
                """)
                square.setText("✓")
            else:  # False → 空心绿色
                square.setStyleSheet("""
                    background-color: transparent;
                    border: 2px solid #00cc66;
                    border-radius: 4px;
                    color: #00cc66;
                """)
                square.setText("○")
            
            layout.addWidget(square)
        
        layout.addStretch(1)