# utils/modbus_logger.py
import logging
from PyQt5.QtCore import QObject, pyqtSignal

class ModbusLogSignaler(QObject):
    # 定义全局信号
    sig_modbus_packet = pyqtSignal(str, str)

# 实例化全局通知单例
modbus_notifier = ModbusLogSignaler()

class QtModbusLogHandler(logging.Handler):
    def emit(self, record):
        try:
            log_msg = record.getMessage()
            
            # 同时兼容新老版本的关键字匹配
            target_keyword = None
            direction = "TX" # 默认发送
            
            if "Processing:" in log_msg:
                target_keyword = "Processing:"
                direction = "TX"
            elif "send:" in log_msg:
                target_keyword = "send:"
                direction = "TX"
            elif "SEND:" in log_msg:
                target_keyword = "SEND:"
                direction = "TX"
            elif "recv:" in log_msg:
                target_keyword = "recv:"
                direction = "RX"
            elif "RECV:" in log_msg:
                target_keyword = "RECV:"
                direction = "RX"

            # 如果匹配到了任何一种 Modbus 报文特征
            if target_keyword:
                # 提取关键字后面的报文内容
                raw_packet = log_msg.split(target_keyword)[1].strip()
                
                # 归一化清洗：将 ['0x1', '0x5'] 或 ['01', '03'] 统一转换为标准大写无前缀 ['01', '05']
                clean_bytes = []
                
                # 兼容老版本可能带有逗号或十六进制前缀的情况，用空格或逗号切分
                # 例如处理 "0x1 0x5" 或者 "01,03,00" 或者 "01 03"
                raw_items = raw_packet.replace(",", " ").split()
                
                for item in raw_items:
                    if not item: 
                        continue
                    # 自动识别 0x 格式、纯 hex 格式并转换为整数
                    val = int(item, 16)
                    # 格式化为双位十六进制，如 1 -> "01", 10 -> "0A"
                    clean_bytes.append(f"{val:02X}")
                
                formatted_packet = " ".join(clean_bytes)
                
                # 过滤可能解析出来的空报文
                if formatted_packet:
                    # 跨线程安全发射信号给 MainWindow
                    modbus_notifier.sig_modbus_packet.emit(direction, formatted_packet)
                
        except Exception as e:
            # 避免日志解析本身的鲁棒性问题影响底层串口的正常通信
            print(f"Log Handler 兼容解析 Modbus 报文失败: {e}")