from PyQt5.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QSpinBox, QStatusBar, QVBoxLayout, QWidget
from modbus.modbus_rtu import AsyncModbusRTUClient, ModbusRTUClient
from PyQt5.QtCore import Qt
import serial.tools.list_ports
from widgets.combobox import BaudrateComboBox, ConverterComboBox, DataBitsComboBox, ParityComboBox, StopBitsComboBox
from common.const import WITHOUT_SERIAL
from widgets.lineedit import HexAddressInput
from widgets.spinbox import SlaveIdSpinBox


class MainWindow(QMainWindow):
    
    def __init__(self):
        super(MainWindow, self).__init__()
        self.setWindowTitle("Modbus RTU Client Tool")
        self.client = None
        self.selected_port = None
        self.initUI()
        
    def initUI(self):
        self.setGeometry(100, 100, 1024, 768)
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.main_layout = QVBoxLayout(self.main_widget)
        self.create_serial_panel()
        self.create_input_panel()
        self.create_output_panel()
        self.create_status_bar()
        
    def create_serial_panel(self):
        title = QLabel("Select a serial")
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(300)
        
        baudrate_title = QLabel("Baudrate:")
        self.baudrate_combo = BaudrateComboBox()
        
        parity_title = QLabel("Parity:")
        self.parity_combo = ParityComboBox()
        
        databits_title = QLabel("Data Bits:")
        self.databits_combo = DataBitsComboBox()
        
        stopbits_title = QLabel("Stop Bits:")
        self.stopbits_combo = StopBitsComboBox()
        
        slave_id_title = QLabel("Slave ID:")
        self.slave_id_spinbox = SlaveIdSpinBox()
        
        self.refresh_btn = QPushButton("Refresh serial ports")
        self.refresh_btn.clicked.connect(self.refresh_port)
        
        self.confirm_btn = QPushButton("Open Serial Port")
        self.confirm_btn.clicked.connect(self.confirm_selection)
        
        h_layout = QHBoxLayout()
        h_layout.addWidget(title)
        h_layout.addWidget(self.port_combo)
        h_layout.addWidget(baudrate_title)
        h_layout.addWidget(self.baudrate_combo)
        h_layout.addWidget(parity_title)
        h_layout.addWidget(self.parity_combo)
        h_layout.addWidget(databits_title)
        h_layout.addWidget(self.databits_combo)
        h_layout.addWidget(stopbits_title)
        h_layout.addWidget(self.stopbits_combo)
        h_layout.addWidget(slave_id_title)
        h_layout.addWidget(self.slave_id_spinbox)
        h_layout.addWidget(self.refresh_btn)
        h_layout.addWidget(self.confirm_btn)
        self.main_layout.addLayout(h_layout)
        
        self.refresh_port()
    
    def create_input_panel(self):
        addr_title: QLabel = QLabel("Address:")
        self.reg_addr_input: HexAddressInput = HexAddressInput()
        
        reg_count_title: QLabel = QLabel("Count:")
        self.reg_count_input: QSpinBox = QSpinBox()
        self.reg_count_input.setRange(1, 100)
        
        little_endian_title: QLabel = QLabel("Endian:")
        self.little_endian_combo: QComboBox = QComboBox()
        self.little_endian_combo.addItem("Little Endian")
        self.little_endian_combo.addItem("Big Endian")
        
        convert_title: QLabel = QLabel("Convert:")
        self.convert_combo: ConverterComboBox = ConverterComboBox()
        
        dara_read_btn: QPushButton = QPushButton("Read Registers")
        dara_read_btn.clicked.connect(self.read_registers)  # 连接读取寄存器的槽函数
        
        self.update_endian_enabled()
        self.reg_count_input.valueChanged.connect(self.update_endian_enabled)
        
        h_layout = QHBoxLayout()
        h_layout.addWidget(addr_title)
        h_layout.addWidget(self.reg_addr_input)
        h_layout.addWidget(reg_count_title)
        h_layout.addWidget(self.reg_count_input)
        h_layout.addWidget(little_endian_title)
        h_layout.addWidget(self.little_endian_combo)
        h_layout.addWidget(convert_title)
        h_layout.addWidget(self.convert_combo)
        h_layout.addWidget(dara_read_btn)
        self.main_layout.addLayout(h_layout)
    
    def create_output_panel(self):
        
        self.result_label = QLabel("Register read results:")
        self.result_label.setStyleSheet("font-size: 20px; font-weight: bold;")

        
        v_layout = QVBoxLayout(self)
        v_layout.addWidget(self.result_label)
        self.main_layout.addLayout(v_layout)
    
    def create_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.status_bar.setStyleSheet("QStatusBar { background-color: azure; }")
        
        # 1. 最左侧：用于显示临时操作状态（新增）
        self.status_message_label = QLabel("")
        self.status_message_label.setMinimumWidth(400)   # 根据需要调整宽度
        self.status_bar.addWidget(self.status_message_label, 0)   # stretch=0，不扩展
        
        # 2. 中间居中的版权信息
        copyright_label = QLabel("Copyright © 2026 H&B Asia & Kunlunbot. All Rights Reserved.")
        copyright_label.setAlignment(Qt.AlignCenter)
        self.status_bar.addWidget(copyright_label, 1)   # stretch=1，让它占据中间空间并居中
        
        # 3. 分隔符（竖线）
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        self.status_bar.addWidget(separator)
        
        # 4. 右边的软件作者信息
        author_label = QLabel('Author: <a href="mailto:yonghao.bai@kunlunbot.cn">Yonghao Bai</a>')
        author_label.setOpenExternalLinks(True)
        author_label.setAlignment(Qt.AlignRight)
        
        author_label.setStyleSheet("""
            QLabel {
                color: #0066cc;
                padding-right: 10px;
            }
            QLabel:hover {
                color: #ff6600;
                text-decoration: underline;
            }
        """)
        
        self.status_bar.addWidget(author_label)
        
    
    def refresh_port(self):
        self.port_combo.clear()
        
        ports = serial.tools.list_ports.comports()
        if not ports:
            self.port_combo.addItem(WITHOUT_SERIAL)
            QMessageBox.warning(self, "Info", "The system has not detected any serial port devices!")
            return
        sorted_ports = sorted(ports, key=lambda p: p.device)
        
        
        for port in sorted_ports:
            text = f"{port.device}"
            if port.description and port.description != "n/a":
                text += f" ({port.description})"
            self.port_combo.addItem(text, userData=port.device)
            
        if self.port_combo.count() > 0:
            self.port_combo.setCurrentIndex(0)
    
    def confirm_selection(self):
        if self.port_combo.currentText() == WITHOUT_SERIAL:
            QMessageBox.warning(self, "Warning", "No available serial port!")
            return
        if self.client and self.client.connected:
            self.client.close()
            self.confirm_btn.setText("Open Serial Port")
            QMessageBox.information(self, "Info", f"Serial port {self.selected_port} closed")
            return
        else:
            self.selected_port = self.port_combo.currentData()
            self.confirm_btn.setText("Close Serial Port")
            self.client = ModbusRTUClient(
                self.selected_port, 
                baudrate=self.baudrate_combo.get_current_baud(),
                parity=self.parity_combo.get_current_parity(),
                bytesize=self.databits_combo.get_current_data_bits(),
                stopbits=self.stopbits_combo.get_current_stop_bits(),
                slave_id=self.slave_id_spinbox.get_slave_id(),
                timeout=1)
            if not self.client.connect():
                QMessageBox.critical(self, "Error", f"Unable to connect to serial port {self.selected_port}!")
                self.client = None
                self.confirm_btn.setText("Open Serial Port")
        
    def read_registers(self):
        if not self.client or not self.client.connected:
            QMessageBox.warning(self, "Warning", "Please open the serial port first!")
            return
        address = self.reg_addr_input.get_value()
        count = self.reg_count_input.value()
        self.status_message_label.setText(
            f"Reading {count} register(s) from 0x{address:04X} ..."
        )
        self.result_label.setText("Reading...")
        little_endian = self.little_endian_combo.currentText() == "Little Endian"
        result = self.client.read_data(add=self.reg_addr_input.get_value(), count=self.reg_count_input.value(), converter=self.convert_combo.get_converter(), little_endian=little_endian)
        self.result_label.setText(f"Read Result: {result}")

    def update_endian_enabled(self):
        """当 Count >= 2 时启用 Endian ComboBox，否则禁用"""
        count = self.reg_count_input.value()
        enabled = (count == 2)
        
        self.little_endian_combo.setEnabled(enabled)
        
        if not enabled:
            self.little_endian_combo.setStyleSheet("QComboBox { color: gray; }")
        else:
            self.little_endian_combo.setStyleSheet("")
