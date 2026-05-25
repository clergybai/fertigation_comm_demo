from dialogs.mainwnd import MainWindow
from PyQt5.QtWidgets import QApplication
from common.utils.modbus_logger import QtModbusLogHandler
import logging
import sys


if __name__ == "__main__":
    # 配置 pymodbus 日志
    pymodbus_logger = logging.getLogger("pymodbus")
    pymodbus_logger.setLevel(logging.DEBUG)
    
    # 挂载拦截器
    pymodbus_logger.addHandler(QtModbusLogHandler())
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
