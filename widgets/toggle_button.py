from PyQt5.QtWidgets import QPushButton, QLabel, QWidget
from PyQt5.QtCore import Qt, QPropertyAnimation, QRect, pyqtSignal

class ToggleButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)  # 让按钮可切换状态
        self.setFixedSize(60, 30)  # 设置大小
        self.updateStyle()

        # 绑定点击事件
        self.toggled.connect(self.updateStyle)

    def updateStyle(self):
        """ 根据当前状态更新样式 """
        if self.isChecked():
            self.setStyleSheet("""
                QPushButton {
                    background-color: #0078D7;
                    border-radius: 15px;
                    color: white;
                    font-weight: bold;
                }
            """)
            self.setText("ON")
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #CCCCCC;
                    border-radius: 15px;
                    color: black;
                    font-weight: bold;
                }
            """)
            self.setText("OFF")


class ToggleToolButton(QWidget):
    toggled = pyqtSignal(bool)  # ✅ 自定义状态变化信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(60, 30)  # 设置固定大小

        # 背景（Toggle 开关底部）
        self.bg_label = QLabel(self)
        self.bg_label.setGeometry(0, 0, 60, 30)
        self.bg_label.setStyleSheet("background-color: #CCCCCC; border-radius: 15px;")

        # 滑动小球
        self.circle = QPushButton(self)
        self.circle.setGeometry(3, 3, 24, 24)  # 小球初始位置
        self.circle.setStyleSheet("background-color: white; border-radius: 12px; border: 1px solid #CCCCCC;")
        self.circle.setEnabled(False)  # 让小球不可点击

        # 绑定点击事件
        self.is_on = False
        self.setStyleSheet("border: none;")  # 去掉默认边框
        self.mousePressEvent = self.toggle  # 绑定鼠标点击事件

        # ✅ 修正：创建动画对象（避免重复创建）
        self.anim = QPropertyAnimation(self.circle, b"geometry")
        self.anim.setDuration(200)  # 动画时长 200ms

    def toggle(self, event=None):
        """ 切换开关状态 """
        self.setChecked(not self.is_on)

    def setChecked(self, state):
        """ 通过代码设置开关状态，并触发信号 """
        if self.is_on != state:  # 只有状态变化时才更新
            self.is_on = state
            self.update_ui()
            self.toggled.emit(self.is_on)  # ✅ 触发信号，通知外部状态变化

    def isChecked(self):
        """ 获取当前状态 """
        return self.is_on

    def update_ui(self):
        """ 更新 UI（小球动画 & 颜色变化） """
        # ✅ 先更新背景颜色
        if self.is_on:
            self.bg_label.setStyleSheet("background-color: #0078D7; border-radius: 15px;")
        else:
            self.bg_label.setStyleSheet("background-color: #CCCCCC; border-radius: 15px;")

        # ✅ 修正小球滑动动画
        start_x = 3 if not self.is_on else 33  # 3（OFF 左侧），33（ON 右侧）
        self.anim.stop()  # 先停止上一次动画，避免冲突
        self.anim.setStartValue(self.circle.geometry())  # 起始位置
        self.anim.setEndValue(QRect(start_x, 3, 24, 24))  # 目标位置
        self.anim.start()  # 播放动画
