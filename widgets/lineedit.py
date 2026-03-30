from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtGui import QIntValidator, QKeyEvent
from PyQt5.QtCore import Qt, pyqtSignal


class HexAddressInput(QLineEdit):
    """
    十六进制寄存器地址输入框
    - 自动显示前缀 0x
    - 只允许输入 0-9、a-f、A-F
    - 支持上下箭头调整地址
    - 返回值为整数（方便后续使用）
    """
    
    valueChanged = pyqtSignal(int)

    def __init__(self, parent=None, default_address: int = 0x0000, max_address: int = 0xFFFF):
        super().__init__(parent)
        
        self.max_address = max_address
        self._current_value = default_address
        
        self.setup_ui()
        self.set_value(default_address)

    def setup_ui(self):
        """初始化设置"""
        self.setPlaceholderText("0000")
        self.setMaxLength(6)
        self.setMinimumWidth(110)
        self.setAlignment(Qt.AlignLeft)
        
        font = self.font()
        font.setFamily("Consolas")
        font.setPointSize(10)
        self.setFont(font)

        # 安装事件过滤器，控制输入
        self.installEventFilter(self)

    def set_value(self, value: int):
        """设置地址值（整数）"""
        value = max(0, min(value, self.max_address))
        self._current_value = value
        # 显示时带 0x 前缀
        self.setText(f"0x{value:04X}")
        self.valueChanged.emit(value)

    def get_value(self) -> int:
        """获取当前地址的整数值"""
        return self._current_value

    def text(self) -> str:
        """重写 text()，返回带 0x 的字符串"""
        return super().text()

    # ====================== 事件处理 ======================
    def eventFilter(self, obj, event):
        if obj == self and event.type() == event.KeyPress:
            return self._handle_key_press(event)
        return super().eventFilter(obj, event)

    def _handle_key_press(self, event: QKeyEvent):
        key = event.key()
        text = event.text().upper()

        # 允许的控制键
        if key in (Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_Left, Qt.Key_Right, 
                   Qt.Key_Home, Qt.Key_End, Qt.Key_Tab):
            return False

        # 允许上下箭头调整地址
        if key == Qt.Key_Up:
            self.set_value(self._current_value + 1)
            return True
        if key == Qt.Key_Down:
            self.set_value(self._current_value - 1)
            return True

        # 只允许十六进制字符 0-9 A-F
        if text and text[0] in "0123456789ABCDEF":
            # 计算新值
            current_hex = self.text().replace("0x", "").upper()
            new_hex = (current_hex + text)[-4:]   # 最多保留4位
            try:
                new_value = int(new_hex, 16)
                self.set_value(new_value)
            except:
                pass
            return True

        return True

    def focusOutEvent(self, event):
        """失去焦点时规范化显示"""
        try:
            text = self.text().replace("0x", "").strip()
            if text:
                value = int(text, 16)
                self.set_value(value)
            else:
                self.set_value(0)
        except:
            self.set_value(self._current_value)
        super().focusOutEvent(event)