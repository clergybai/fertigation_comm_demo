import time
import json

from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QAction, QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QSpinBox, QStatusBar, QTextEdit, QVBoxLayout, QWidget, QLineEdit
from modbus.modbus_rtu import AsyncModbusRTUClient, ModbusRTUClient
from PyQt5.QtCore import QTimer, Qt
import serial.tools.list_ports
from widgets.combobox import BaudrateComboBox, ConverterComboBox, DataBitsComboBox, ParityComboBox, StopBitsComboBox
from widgets.actuator_status_widget import ActuatorStatusWidget
from common.const import WITHOUT_SERIAL, CONFIG_FILE
from common.utils.modbus_logger import modbus_notifier
from widgets.lineedit import HexAddressInput
from widgets.spinbox import SlaveIdSpinBox
from common.mqtt import MqttClient
from PyQt5.QtCore import QSettings
import os

from widgets.toggle_button import ToggleToolButton


class MainWindow(QMainWindow):
    
    def __init__(self):
        super(MainWindow, self).__init__()
        self.setWindowTitle("Modbus RTU Client Tool")
        # 初始化 QSettings（推荐使用组织名 + 应用名）
        self.settings = QSettings("Kunlunbot", "ModbusRTUClientTool")
        
        self.config_file = CONFIG_FILE
        
        self.client = None
        self.selected_port = None
        self.ca_cert_pem = None  # 用于存储加载的 CA 证书内容
        self.mqtt = MqttClient()
        
        self.current_cfg = []
        self.freq_seconds = 300
        self.actuator_cfg = []
        self.actuator_freq = 10
        # last_actuator_states record last discrete status
        self.last_actuator_states = {}
        self.read_timer = QTimer()
        self.read_timer.timeout.connect(self.read_modbus_by_cfg)
        
        self.actuator_read_timer = QTimer()
        self.actuator_read_timer.timeout.connect(self.read_actuators_by_cfg)
        
        self.current_output = None
        self.pause_mqtt_publish = False
        self.relay_status = [False] * 8
        self.log_text = None
        self.is_controlling_now = False
        
        self.initUI()
        # 程序启动后立即加载上次的配置
        self.load_mqtt_settings()
        self.load_current_cfg()
        
    def initUI(self):
        self.setGeometry(100, 100, 1024, 768)
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.main_layout = QVBoxLayout(self.main_widget)
        self.create_serial_panel()
        self.create_input_panel()
        self.create_output_panel()
        self.create_relay_panel()
        self.create_realtime_data_panel()
        self.create_status_bar()
        self.create_mqtt_panel()
        self.create_log_panel()
        
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
        
        self.read_id_btn: QPushButton = QPushButton("Read Device Slave ID")
        self.read_id_btn.setStyleSheet("background-color: #0066cc; color: white; font-weight: bold;")
        self.read_id_btn.clicked.connect(self.read_slave_id)
        
        dara_read_btn: QPushButton = QPushButton("Read Registers")
        dara_read_btn.clicked.connect(self.read_registers)  # 连接读取寄存器的槽函数
        
        self.update_endian_enabled()
        self.reg_count_input.valueChanged.connect(self.update_endian_enabled)
        
        new_id_title = QLabel("New Slave ID:")
        self.new_slave_id_input = QSpinBox()
        self.new_slave_id_input.setRange(1, 255)
        self.new_slave_id_input.setValue(2)
        self.new_slave_id_input.setFixedWidth(65)
        
        self.change_id_btn = QPushButton("Change Slave Id")
        self.change_id_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff9900; 
                color: white; 
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e68a00;
            }
        """)
        self.change_id_btn.clicked.connect(self.change_device_slave_id)
        
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
        h_layout.addWidget(self.read_id_btn)
        h_layout.addSpacing(15)  # 在读取和修改之间加个小间距，防止误触
        h_layout.addWidget(new_id_title)
        h_layout.addWidget(self.new_slave_id_input)
        h_layout.addWidget(self.change_id_btn)
        
        h_layout.addStretch(1)
        self.main_layout.addLayout(h_layout)
    
    def create_output_panel(self):
        
        self.result_label = QLabel("Register read results:")
        self.result_label.setStyleSheet("font-size: 20px; font-weight: bold;")

        
        v_layout = QVBoxLayout(self)
        v_layout.addWidget(self.result_label)
        self.main_layout.addLayout(v_layout)
    
    def create_relay_panel(self):
        """485 继电器控制面板 - 高度固定不变"""
        group = QFrame()
        group.setFrameShape(QFrame.StyledPanel)
        group.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #cccccc;
                border-radius: 6px;
            }
        """)
        group.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        group.setFixedHeight(200)

        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        title = QLabel("485 Relay Control")
        title.setStyleSheet("font-weight: bold; font-size: 25px; color: #0066cc;")
        title.setFixedHeight(30)
        layout.addWidget(title)

        # 第一行：所有控制控件
        control_layout = QHBoxLayout()
        
        # 通道
        channel_label = QLabel("Channel:")
        # channel_label.setFixedWidth(45)
        self.relay_channel_spin = QSpinBox()
        self.relay_channel_spin.setRange(0, 7)
        self.relay_channel_spin.setValue(0)
        # self.relay_channel_spin.setFixedWidth(70)

        control_layout.addWidget(channel_label)
        control_layout.addWidget(self.relay_channel_spin)
        control_layout.addSpacing(15)

        # 控制按钮
        self.relay_on_btn = QPushButton("ON")
        self.relay_off_btn = QPushButton("OFF")
        self.relay_toggle_btn = QPushButton("Toggle")
        self.relay_flash_btn = QPushButton("Flash")
        self.relay_read_btn = QPushButton("读取状态")

        self.relay_on_btn.clicked.connect(self.relay_turn_on)
        self.relay_off_btn.clicked.connect(self.relay_turn_off)
        self.relay_toggle_btn.clicked.connect(self.relay_toggle)
        self.relay_flash_btn.clicked.connect(self.relay_flash)
        self.relay_read_btn.clicked.connect(self.read_coils_status)

        for btn in [self.relay_on_btn, self.relay_off_btn, self.relay_toggle_btn, self.relay_read_btn]:
            btn.setFixedWidth(90)
            control_layout.addWidget(btn)
        
        # Flash 延时输入框
        self.flash_delay_spin = QSpinBox()
        self.flash_delay_spin.setRange(100, 5000)
        self.flash_delay_spin.setValue(800)
        self.flash_delay_spin.setSingleStep(100)
        self.flash_delay_spin.setSuffix(" ms")
        self.flash_delay_spin.setFixedWidth(110)

        control_layout.addWidget(self.relay_flash_btn)
        control_layout.addWidget(self.flash_delay_spin)
        control_layout.addSpacing(20)

        # 读取数量
        read_label = QLabel("Read Coil Number:")
        # read_label.setFixedWidth(70)
        self.coil_count_spin = QSpinBox()
        self.coil_count_spin.setRange(1, 16)
        self.coil_count_spin.setValue(8)
        # self.coil_count_spin.setFixedWidth(70)

        self.read_coils_btn = QPushButton("Read All Coils")
        self.read_coils_btn.clicked.connect(self.read_coils_status)

        control_layout.addWidget(read_label)
        control_layout.addWidget(self.coil_count_spin)
        control_layout.addWidget(self.read_coils_btn)
        control_layout.addStretch(1)

        layout.addLayout(control_layout)

        # ==================== Toggle 显示区域 - 固定高度 ====================
        self.coils_status_layout = QHBoxLayout()
        self.coils_status_layout.setSpacing(12)

        # 使用固定高度的容器
        toggle_container = QWidget()
        toggle_container.setFixedHeight(110)           # ← 固定高度
        toggle_container.setLayout(self.coils_status_layout)
        
        layout.addWidget(toggle_container)
        # =====================================================================

        self.main_layout.addWidget(group)

        # 初始化显示
        self.update_coils_display()
    
    def create_realtime_data_panel(self):
        """创建实时数据 LED 显示面板 - 升级为左右分栏无干涉布局"""
        group = QFrame()
        self.realtime_group = group
        group.setFrameShape(QFrame.StyledPanel)
        group.setStyleSheet("QFrame { background-color: #1e1e1e; border: 1px solid #444; }")
        
        # 整体采用垂直布局：上面放总标题，下面放分栏内容
        main_vbox = QVBoxLayout(group)
        main_vbox.setContentsMargins(10, 10, 10, 10)
        
        # 总标题
        title = QLabel("Real-time Data Monitor")
        title.setStyleSheet("font-weight: bold; font-size: 25px; color: #00ffcc; padding-bottom: 5px; border-bottom: 1px solid #333;")
        main_vbox.addWidget(title)

        # 🌟 核心：创建左右分栏的水平布局
        split_layout = QHBoxLayout()
        split_layout.setSpacing(20)  # 左右两侧的间距

        # --- 【左分栏】：Sensor 区域 ---
        sensor_box = QWidget()
        sensor_box.setStyleSheet("QWidget { border: none; background: transparent; }")
        self.sensor_display = QVBoxLayout(sensor_box)
        self.sensor_display.setContentsMargins(0, 5, 0, 0)
        
        sensor_title = QLabel("📡 Sensors / Tags")
        sensor_title.setStyleSheet("color: #00ffff; font-size: 20px; font-weight: bold;")
        self.sensor_display.addWidget(sensor_title)
        self.sensor_display.addSpacing(5)
        # 这里预留一个容纳动态数据的垂直布局
        self.sensor_data_container = QVBoxLayout()
        self.sensor_display.addLayout(self.sensor_data_container)
        self.sensor_display.addStretch(1) # 撑起底部

        # --- 【右分栏】：Actuator 区域 ---
        actuator_box = QWidget()
        actuator_box.setStyleSheet("QWidget { border: none; background: transparent; }")
        self.actuator_display = QVBoxLayout(actuator_box)
        self.actuator_display.setContentsMargins(0, 5, 0, 0)
        
        actuator_title = QLabel("⚙️ Actuators / Relays")
        actuator_title.setStyleSheet("color: #ff9900; font-size: 20px; font-weight: bold;")
        self.actuator_display.addWidget(actuator_title)
        self.actuator_display.addSpacing(5)
        # 这里预留一个容纳动态数据的垂直布局
        self.actuator_data_container = QVBoxLayout()
        self.actuator_display.addLayout(self.actuator_data_container)
        self.actuator_display.addStretch(1) # 撑起底部

        # 将左右两块塞入分栏布局
        split_layout.addWidget(sensor_box, stretch=1)
        
        # 中间加一条暗色的垂直分界线，让界面更精致
        v_line = QFrame()
        v_line.setFrameShape(QFrame.VLine)
        v_line.setStyleSheet("background-color: #333333;")
        split_layout.addWidget(v_line)
        
        split_layout.addWidget(actuator_box, stretch=1)

        # 把分栏布局塞回主面板
        main_vbox.addLayout(split_layout)
        self.main_layout.addWidget(group, stretch=3)
    
    def create_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.setStyleSheet("QStatusBar { background-color: azure; }")
        
        # 1. 最左侧：用于显示临时操作状态（新增）
        self.status_message_label = QLabel("")
        self.status_message_label.setMinimumWidth(380)   # 根据需要调整宽度
        self.status_bar.addWidget(self.status_message_label, 0)   # stretch=0，不扩展
        
        # 2. MQTT 连接状态
        self.mqtt_status_label = QLabel("MQTT: 未连接")
        self.mqtt_status_label.setStyleSheet("color: #666666;")
        self.status_bar.addWidget(self.mqtt_status_label, 0)
        
        # 3. 设备 SN 显示（永久显示）
        self.sn_label = QLabel("SN: ------")
        self.sn_label.setStyleSheet("color: #0066cc; font-weight: bold;")
        self.sn_label.setContextMenuPolicy(Qt.CustomContextMenu)        # 关键：启用自定义右键菜单
        self.sn_label.customContextMenuRequested.connect(self.show_sn_context_menu)  # 连接右键信号
        self.status_bar.addWidget(self.sn_label, 0)
        
        # 4. 中间居中的版权信息
        copyright_label = QLabel("Copyright © 2026 H&B Asia & Kunlunbot. All Rights Reserved.")
        copyright_label.setAlignment(Qt.AlignCenter)
        self.status_bar.addWidget(copyright_label, 1)   # stretch=1，让它占据中间空间并居中
        
        # 5. 分隔符（竖线）
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        self.status_bar.addWidget(separator)
        
        # 6. 右边的软件作者信息
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
    
    def create_mqtt_panel(self):
        group = QFrame()
        self.mqtt_group = group
        group.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(group)

        self.mqtt_layout = layout
        btn_layout = QHBoxLayout()
        self.mqtt_btn_layout = btn_layout

        title = QLabel("MQTT Broker Configuration")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")

        # Broker 地址
        broker_layout = QHBoxLayout()
        broker_layout.addWidget(QLabel("Broker:"))
        self.mqtt_broker_input = QLineEdit("broker.emqx.io")
        self.mqtt_broker_input.setMinimumWidth(250)
        broker_layout.addWidget(self.mqtt_broker_input)

        # Port + Tenant ID + Freq
        config_layout = QHBoxLayout()
        
        # Port
        config_layout.addWidget(QLabel("Port:"))
        self.mqtt_port_input = QSpinBox()
        self.mqtt_port_input.setRange(1, 65535)
        self.mqtt_port_input.setValue(8883)
        config_layout.addWidget(self.mqtt_port_input)

        # Tenant ID
        config_layout.addSpacing(20)
        config_layout.addWidget(QLabel("Tenant ID:"))
        self.mqtt_tenant_id_input = QLineEdit()
        self.mqtt_tenant_id_input.setPlaceholderText("Input Tenant ID")
        self.mqtt_tenant_id_input.setMinimumWidth(150)
        config_layout.addWidget(self.mqtt_tenant_id_input)

        # 读取频率
        config_layout.addSpacing(30)
        config_layout.addWidget(QLabel("Read Freq (sec):"))
        self.freq_input = QSpinBox()
        self.freq_input.setRange(1, 3600)        # 1秒 ~ 1小时
        self.freq_input.setValue(300)
        self.freq_input.setSingleStep(10)
        self.freq_input.valueChanged.connect(self.on_freq_changed)   # 实时响应修改
        config_layout.addWidget(self.freq_input)
        
        # 新增：Actuator Frequency
        config_layout.addSpacing(20)
        config_layout.addWidget(QLabel("Actuator Freq (sec):"))
        self.actuator_freq_input = QSpinBox()
        self.actuator_freq_input.setRange(1, 3600)
        self.actuator_freq_input.setValue(300)
        self.actuator_freq_input.setSingleStep(10)
        self.actuator_freq_input.valueChanged.connect(self.on_actuator_freq_changed)
        config_layout.addWidget(self.actuator_freq_input)

        # CA + Username + Password 放在同一行
        auth_layout = QHBoxLayout()
        
        # CA Certificate
        auth_layout.addWidget(QLabel("CA Certificate:"))
        self.mqtt_ca_btn = QPushButton("Browse CA File")
        self.mqtt_ca_btn.clicked.connect(self.browse_ca_file)
        self.ca_status_label = QLabel("未加载 CA")
        self.ca_status_label.setStyleSheet("color: gray;")
        auth_layout.addWidget(self.mqtt_ca_btn)
        auth_layout.addWidget(self.ca_status_label)

        # Username
        auth_layout.addSpacing(30)                    # 增加一些间距
        auth_layout.addWidget(QLabel("Username:"))
        self.mqtt_username_input = QLineEdit()
        self.mqtt_username_input.setMinimumWidth(120)
        auth_layout.addWidget(self.mqtt_username_input)

        # Password
        auth_layout.addWidget(QLabel("Password:"))
        self.mqtt_password_input = QLineEdit()
        self.mqtt_password_input.setEchoMode(QLineEdit.Password)   # 密码隐藏
        self.mqtt_password_input.setMinimumWidth(120)
        auth_layout.addWidget(self.mqtt_password_input)

        # 连接按钮
        btn_layout = QHBoxLayout()
        self.mqtt_connect_btn = QPushButton("Connect MQTT")
        self.mqtt_connect_btn.clicked.connect(self.connect_mqtt)
        self.mqtt_disconnect_btn = QPushButton("Disconnect MQTT")
        self.mqtt_disconnect_btn.clicked.connect(self.disconnect_mqtt)
        self.pause_mqtt_publish_btn = QPushButton("Pause MQTT Publish")
        self.pause_mqtt_publish_btn.clicked.connect(self.toggle_mqtt_publish)
        self.mannal_publish_btn = QPushButton("Manual Publish")
        self.mannal_publish_btn.clicked.connect(self.manual_publish)
        self.mqtt_disconnect_btn.setEnabled(False)

        self.mqtt_controls = [
            self.mqtt_broker_input,
            self.mqtt_port_input,
            self.mqtt_tenant_id_input,
            self.freq_input,
            self.actuator_freq_input,
            self.mqtt_ca_btn,
            self.mqtt_username_input,
            self.mqtt_password_input,
            self.mqtt_connect_btn,
            self.mqtt_disconnect_btn,
            self.pause_mqtt_publish_btn,
            self.mannal_publish_btn,
        ]
        
        btn_layout.addWidget(self.mqtt_connect_btn)
        btn_layout.addWidget(self.mqtt_disconnect_btn)
        btn_layout.addWidget(self.pause_mqtt_publish_btn)
        btn_layout.addWidget(self.mannal_publish_btn)
        
        layout.addWidget(title)
        layout.addLayout(broker_layout)
        layout.addLayout(config_layout) 
        layout.addLayout(auth_layout)
        layout.addLayout(btn_layout)

        self.main_layout.addWidget(group, stretch=2)
        
        self.mqtt.device_sn_generated.connect(self.on_device_sn_generated) 

    def create_log_panel(self):
        """新增 Modbus 通信日志面板"""
        group = QFrame()
        self.log_group = group
        group.setFrameShape(QFrame.StyledPanel)
        group.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #cccccc;
                border-radius: 6px;
            }
        """)

        layout = QVBoxLayout(group)
        
        # 折叠/展开按钮
        self.log_visible = True
        self.log_toggle_btn = QPushButton("▼ Modbus Communication Log")
        self.log_toggle_btn.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                font-size: 24px;
                color: #0066cc;
                text-align: left;
                padding: 5px;
                border: none;
                background-color: transparent;
            }
        """)
        self.log_toggle_btn.clicked.connect(self.toggle_log_panel)
        layout.addWidget(self.log_toggle_btn)

        # 日志显示区域
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(180)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #00ff88;
                font-family: Consolas, Courier New, monospace;
                font-size: 22px;
                border: 1px solid #444;
            }
        """)
        
        layout.addWidget(self.log_text)
        
        # 清除日志按钮
        self.clear_log_btn = QPushButton("Clear Log")
        self.clear_log_btn.clicked.connect(self.clear_log)
        layout.addWidget(self.clear_log_btn)

        self.main_layout.addWidget(group)

    def toggle_log_panel(self):
        self.log_visible = not self.log_visible

        self.log_text.setVisible(self.log_visible)
        self.clear_log_btn.setVisible(self.log_visible)

        if self.log_visible:
            self.log_toggle_btn.setText("▼ Modbus Communication Log")
            self.log_text.setMinimumHeight(180)
            self.log_text.setMaximumHeight(16777215)

            if self.client:
                self.client.set_log_enabled(True)

            # MQTT区域恢复正常布局
            self.mqtt_layout.setSpacing(6)
            self.mqtt_layout.setContentsMargins(9, 9, 9, 9)
            self.mqtt_btn_layout.setSpacing(6)

            for control in self.mqtt_controls:
                control.setMinimumHeight(0)
        else:
            self.log_toggle_btn.setText("▶ Modbus Communication Log")
            self.log_text.setMinimumHeight(0)
            self.log_text.setMaximumHeight(0)

            if self.client:
                self.client.set_log_enabled(False)

            # MQTT区域利用释放出来的空间
            self.mqtt_layout.setSpacing(18)
            self.mqtt_layout.setContentsMargins(18, 18, 18, 18)
            self.mqtt_btn_layout.setSpacing(20)

            for control in self.mqtt_controls:
                control.setMinimumHeight(42)
    
    def save_mqtt_settings(self):
        """保存 MQTT 配置到本地文件"""
        self.settings.setValue("mqtt/broker", self.mqtt_broker_input.text().strip())
        self.settings.setValue("mqtt/port", self.mqtt_port_input.value())
        self.settings.setValue("mqtt/tenant_id", self.mqtt_tenant_id_input.text().strip())
        self.settings.setValue("mqtt/username", self.mqtt_username_input.text().strip())
        self.settings.setValue("mqtt/ca_file_path", getattr(self, 'ca_file_path', ""))
        
        # 注意：密码不要明文保存（这里仅做演示，实际项目建议加密或不保存）
        self.settings.setValue("mqtt/password", self.mqtt_password_input.text().strip())
        
        self.settings.sync()   # 立即写入磁盘

    def load_mqtt_settings(self):
        """从本地文件加载上次保存的 MQTT 配置"""
        broker = self.settings.value("mqtt/broker", "broker.emqx.io")
        port = self.settings.value("mqtt/port", 8883, type=int)
        tenant_id = self.settings.value("mqtt/tenant_id", "")
        username = self.settings.value("mqtt/username", "")
        password = self.settings.value("mqtt/password", "")
        ca_path = self.settings.value("mqtt/ca_file_path", "")

        self.mqtt_broker_input.setText(broker)
        self.mqtt_port_input.setValue(port)
        self.mqtt_tenant_id_input.setText(tenant_id)   
        self.mqtt_username_input.setText(username)
        self.mqtt_password_input.setText(password)

        if ca_path:
            self.ca_file_path = ca_path
            self.ca_status_label.setText(f"已加载: {ca_path.split('/')[-1]}")
            self.ca_status_label.setStyleSheet("color: green;")
            
            # 如果需要同时加载证书内容（推荐）
            try:
                with open(ca_path, 'r', encoding='utf-8') as f:
                    self.ca_cert_pem = f.read().strip()
                self.mqtt.set_ca_cert(self.ca_cert_pem)
            except:
                pass  # 文件可能已被删除，不崩溃 
    
    def save_current_cfg(self):
        """将当前 self.current_cfg 保存到本地 JSON 文件"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "cfg": self.current_cfg,
                    "freq": self.freq_seconds,
                    "actuator_cfg": self.actuator_cfg,
                    "actuator_freq": self.actuator_freq
                }, f, ensure_ascii=False, indent=2)
            print(f"Saved current cfg to {self.config_file}")
        except Exception as e:
            print(f"保存 cfg 失败: {e}")
            
    def load_current_cfg(self):
        """Load current cfg from local JSON file"""
        try:
            if not os.path.exists(self.config_file):
                return
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.current_cfg = data.get("cfg", {})
            self.freq_seconds = data.get("freq", 300)
            self.actuator_cfg = data.get("actuator_cfg", [])
            self.actuator_freq = data.get("actuator_freq", 300)
            
            try:
                if hasattr(self, 'actuator_freq_input'):
                    self.actuator_freq_input.setValue(self.actuator_freq)
                self.freq_input.valueChanged.disconnect(self.on_freq_changed)
                self.freq_input.setValue(self.freq_seconds)
                self.freq_input.valueChanged.connect(self.on_freq_changed)
            except:
                self.freq_input.setValue(self.freq_seconds)
            
            if self.current_cfg:
                self.status_message_label.setText(f"load cfg | {len(self.current_cfg)} tags | freq: {self.freq_seconds}s")
            print(f"Loaded current cfg from {self.config_file}")
        except Exception as e:
            print(f"加载 cfg 失败: {e}")
            self.current_cfg = []
            self.actuator_cfg = []
            self.freq_seconds = 300
            self.actuator_freq = 10

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
            self.client = None

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
                timeout=1,
                main_window=self)
            
            self.client.set_log_enabled(self.log_visible)

            if self.client.connect():
                self.confirm_btn.setText("Close Serial Port")
                self.status_message_label.setText(f"串口 {self.selected_port} 已打开")
                
                # 如果已经有配置，则启动定时读取
                # if self.current_cfg and self.freq_seconds > 0:
                #     self.read_timer.start(self.freq_seconds * 1000)
                #     self.status_message_label.setText(f"串口打开，开始周期读取（{self.freq_seconds}s）")
            else:
                QMessageBox.critical(self, "Error", f"无法连接串口 {self.selected_port}!")
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
        
        # --- 修改开始 ---
        # if result is not None:
        #     # 确保处理的是整数（对于光照等 32 位原始值）
        #     val_int = int(result)
            
        #     # 1. 十六进制显示 (根据大小自动选择 4 位或 8 位)
        #     hex_format = "0x{:08X}" if val_int > 0xFFFF else "0x{:04X}"
        #     hex_str = hex_format.format(val_int)
            
        #     # 2. 二进制显示并按 8bit 分割
        #     # bin(val_int)[2:] 去掉 '0b' 前缀
        #     # zfill 补齐位数，如果是 32 位值就补齐 32 位，否则 16 位
        #     total_bits = 32 if val_int > 0xFFFF else 16
        #     bin_raw = bin(val_int)[2:].zfill(total_bits)
            
        #     # 每 8 位加一个空格分割
        #     bin_str = " ".join([bin_raw[i:i+8] for i in range(0, len(bin_raw), 8)])
            
        #     # 3. 组合显示
        #     display_text = f"Hex: {hex_str}\nBin: {bin_str}\nDec: {result}"
        # else:
        #     display_text = "Read Failed"

        # self.result_label.setText(display_text)
        # --- 修改结束 ---

    def read_slave_id(self):
        """读取485设备的 Slave ID（使用广播指令）"""
        if not self.client or not self.client.connected:
            QMessageBox.warning(self, "Warning", "Please open the serial port first!")
            return

        self.status_message_label.setText("Broadcasting to read device ID...")

        try:
            slave_id = self.client.read_device_id_broadcast()   # 使用新方法
            
            if slave_id is not None:
                self.status_message_label.setText(f"✅ Read successful! Device Slave ID = {slave_id}")
                self.slave_id_spinbox.setValue(slave_id)   # 自动填充
                QMessageBox.information(self, "Success", 
                    f"Successfully read device address via broadcast \n\nSlave ID = {slave_id}")
            else:
                self.status_message_label.setText("❌ No device response received")
                QMessageBox.warning(self, "Read failed", 
                    "Broadcast read received no response.\n\nPossible reasons:\n"
                    "1. The 485 wiring is incorrect (A/B wires are reversed).\n"
                    "2. The device is not powered on.\n"
                    "3. Baud rate/parity setting error\n"
                    "4. The device does not support broadcasting (in rare cases).")
                
        except Exception as e:
            self.status_message_label.setText(f"Exception: {e}")
            QMessageBox.critical(self, "Error", f"Read failed:\n{str(e)}")
    
    def change_device_slave_id(self):
        """
        槽函数：响应界面按钮，调用底层广播修改 ID
        """
        if not self.client or not self.client.connected:
            QMessageBox.warning(self, "Warning", "Please open the serial port first!")
            return

        target_new_id = self.new_slave_id_input.value()

        # 强力安全弹窗提示
        confirm_msg = (
            f"⚠️ 行业铁律提示：您正在使用【广播模式】修改地址！\n\n"
            f"即将把总线上的设备地址强制变更为: {target_new_id}\n\n"
            f"请100%确保当前 485 总线上【只接了一个传感器】！\n"
            f"如果接了多个设备，它们会【全部】变成新地址 {target_new_id}。"
        )
        reply = QMessageBox.question(self, "广播修改设备地址确认", confirm_msg, 
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            return

        self.status_message_label.setText(f"正在广播写入新地址 {target_new_id} ...")

        # 🌟 核心优雅调用：一行代码搞定底层通信
        success = self.client.write_slave_id_broadcast(target_new_id)

        if success:
            self.status_message_label.setText(f"✅ 广播修改指令发送完毕！新地址：{target_new_id}")
            
            # 联动：自动把主界面的下拉框/输入框切到新 ID，方便用户直接点击“读取”测试
            self.slave_id_spinbox.setValue(target_new_id) 
            
            QMessageBox.information(
                self, "Broadcast Success", 
                f"广播改写指令已成功下发！\n\n"
                f"设备新地址已预设为: {target_new_id}\n"
                f"日常通信 [Slave ID] 已自动切换，您可以直接读取寄存器验证。"
            )
        else:
            self.status_message_label.setText("❌ 广播修改失败")
            QMessageBox.critical(self, "Error", "广播修改指令下发异常，请查看控制台日志。")

    def update_endian_enabled(self):
        """当 Count >= 2 时启用 Endian ComboBox，否则禁用"""
        count = self.reg_count_input.value()
        enabled = (count == 2)
        
        self.little_endian_combo.setEnabled(enabled)
        
        if not enabled:
            self.little_endian_combo.setStyleSheet("QComboBox { color: gray; }")
        else:
            self.little_endian_combo.setStyleSheet("")

    def update_coils_display(self):
        """动态更新线圈状态显示 - 修复显示不全问题"""
        # 清空旧的显示
        while self.coils_status_layout.count():
            child = self.coils_status_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        count = self.coil_count_spin.value()
        
        for i in range(count):
            container = QWidget()
            vbox = QVBoxLayout(container)
            vbox.setContentsMargins(8, 8, 8, 8)
            vbox.setSpacing(5)
            
            label = QLabel(f"CH{i}")
            label.setAlignment(Qt.AlignCenter)
            label.setFixedHeight(22)
            label.setStyleSheet("font-size: 20px; font-weight: bold;")
            
            toggle = ToggleToolButton()
            
            # ================= 🛠️ 核心修复：在这里加锁 =================
            toggle.blockSignals(True)  # 1. 临时屏蔽信号，防止 setChecked 触发 toggled 信号
            toggle.setChecked(self.relay_status[i] if i < len(self.relay_status) else False)
            toggle.blockSignals(False) # 2. 状态赋值完毕，重新放开信号
            # =========================================================
            
            toggle.setFixedSize(85, 48)
            toggle.toggled.connect(lambda checked, ch=i: self.on_coil_toggle(ch, checked))
            
            vbox.addWidget(label)
            vbox.addWidget(toggle)
            vbox.addStretch(1)
            
            container.setMinimumWidth(110)
            self.coils_status_layout.addWidget(container)
        
        self.coils_status_layout.addStretch(1)

    def on_coil_toggle(self, channel: int, checked: bool):
        """点击 Toggle 直接控制对应线圈"""
        if not self.client or not self.client.connected:
            QMessageBox.warning(self, "警告", "串口未打开")
            return
            
        success = self.client.write_single_coil(channel, checked)
        if success:
            self.relay_status[channel] = checked
            self.status_message_label.setText(f"CH{channel} 已设置为 {'ON' if checked else 'OFF'}")
        else:
            QMessageBox.warning(self, "失败", f"控制 CH{channel} 失败")

    def read_coils_status(self):
        """读取线圈输出状态 (功能码 01)"""
        if not self.client or not self.client.connected:
            QMessageBox.warning(self, "Warning", "Please open the serial port first!")
            return

        count = self.coil_count_spin.value()
        self.status_message_label.setText(f"Reading the states of the first {count} coils...")

        try:
            # 功能码 01：读取线圈状态
            response = self.client.read_coils(start_addr=0, count=count)
            
            if response is not None:
                self.relay_status = response[:count]  # 更新缓存
                self.update_coils_display()
                status_text = " | ".join([f"CH{i}:{'ON' if s else 'OFF'}" for i, s in enumerate(self.relay_status)])
                self.status_message_label.setText(f"Read successful: {status_text}")
            else:
                self.status_message_label.setText("Failed to read coil status")
                QMessageBox.warning(self, "Fail", "No device response received")
                
        except Exception as e:
            self.status_message_label.setText(f"读取异常: {e}")
            QMessageBox.critical(self, "错误", str(e))

    def browse_ca_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select CA Certificate", "", "Certificate Files (*.crt *.pem);;All Files (*)")
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    ca_content = f.read().strip()
                
                self.ca_cert_pem = ca_content
                self.mqtt.set_ca_cert(ca_content) 
                QMessageBox.information(self, "CA Certificate Loaded", f"Successfully loaded CA certificate from:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load CA certificate:\n{str(e)}") 


    def connect_mqtt(self):
        username = self.mqtt_username_input.text().strip()
        password = self.mqtt_password_input.text().strip()
        tenant_id = self.mqtt_tenant_id_input.text().strip()
        
        self.mqtt.username = username if username else None
        self.mqtt.password = password if password else None
        self.status_message_label.setText("Connecting MQTT Broker...")
        
        self.mqtt.broker = self.mqtt_broker_input.text().strip()
        self.mqtt.port = self.mqtt_port_input.value()
        self.mqtt.set_tenant_id(tenant_id)
        if self.ca_cert_pem:
            self.mqtt.set_ca_cert(self.ca_cert_pem)
        
        # 保存配置
        self.save_mqtt_settings()
        
        self.mqtt.connected.connect(self.on_mqtt_connected)
        self.mqtt.disconnected.connect(self.on_mqtt_disconnected)
        self.mqtt.message_received.connect(self.on_mqtt_message_received)
        self.mqtt.connection_error.connect(self.on_mqtt_error)
        
        self.mqtt.connect_to_broker()
        
    def check_acutator_status_equal_by_ch(self, device_id, ch, val):
        if not self.last_actuator_states:
            return False
        if device_id not in self.last_actuator_states:
            return False
        last_status_vals = self.last_actuator_states.get(device_id)
        return val == last_status_vals[ch]

    def disconnect_mqtt(self):
        self.mqtt.disconnect()
        self.mqtt_connect_btn.setEnabled(True)
        self.mqtt_disconnect_btn.setEnabled(False)
        
    def toggle_mqtt_publish(self):
        """切换 MQTT 发布的暂停/继续状态"""
        self.pause_mqtt_publish = not self.pause_mqtt_publish
        if self.pause_mqtt_publish:
            self.pause_mqtt_publish_btn.setText("Resume MQTT Publish")
            self.status_message_label.setText("MQTT 发布已暂停")
        else:
            self.pause_mqtt_publish_btn.setText("Pause MQTT Publish")
            self.status_message_label.setText("MQTT 发布已恢复")
    
    def manual_publish(self):
        """手动触发一次 MQTT 发布（如果有当前输出）"""
        if self.current_output and self.mqtt.connected:
            publish_topic = f"tenants/{self.mqtt_tenant_id_input.text().strip()}/devices/{self.mqtt.device_sn}/telemetry"
            self.mqtt.publish(publish_topic, json.dumps(self.current_output), qos=1)
            self.status_message_label.setText("Manual publish triggered")
        else:
            self.status_message_label.setText("No data to publish manually")
    
    def on_freq_changed(self, new_freq: int):
        """用户手动修改读取频率时实时生效"""
        self.freq_seconds = new_freq
        
        # 只有当串口已经打开时才启动定时器
        if self.client and self.client.connected:
            if self.read_timer.isActive():
                self.read_timer.stop()
            if new_freq > 0:
                self.read_timer.start(new_freq * 1000)
                self.status_message_label.setText(f"读取频率已修改为: {new_freq} 秒")
        else:
            self.status_message_label.setText(f"频率已设置为 {new_freq} 秒（串口未打开，暂不启动读取）")
        
        # 保存到配置文件
        self.save_current_cfg()
        
    def on_actuator_freq_changed(self, new_freq: int):
        """用户手动修改执行器频率时实时生效"""
        self.actuator_freq = new_freq

        if self.client and self.client.connected:
            if self.actuator_read_timer.isActive():
                self.actuator_read_timer.stop
            
            if new_freq > 0:
                self.actuator_read_timer.start(new_freq * 1000)
                self.status_message_label.setText(
                    f"执行器频率已修改为:{new_freq}秒"
                )
            else:
                self.status_message_label.setText(
                    f"执行器频率已修改为:{new_freq}秒（串口未打开，暂不启动读取）"
                )
        # 保存配置
        self.save_current_cfg()

    # 信号槽
    def on_mqtt_connected(self):
        self.mqtt_status_label.setText("MQTT: ✅ connected")
        self.mqtt_status_label.setStyleSheet("color: green; font-weight: bold;")
        self.mqtt_connect_btn.setEnabled(False)
        self.mqtt_disconnect_btn.setEnabled(True)
        # self.status_message_label.setText("")  
        # QMessageBox.information(self, "MQTT", "成功连接到 MQTT Broker！")
        # 只有当串口已打开 且 有配置 时，才启动定时读取
        if (self.client and self.client.connected and 
            self.current_cfg and len(self.current_cfg) > 0 and 
            self.freq_seconds > 0):
            
            self.read_timer.start(self.freq_seconds * 1000)
            self.status_message_label.setText(f"MQTT 已连接，开始周期读取（每 {self.freq_seconds} 秒）")
        else:
            self.status_message_label.setText("MQTT 已连接，等待串口打开或配置下发...")
        
        if (self.client and self.client.connected and 
            self.actuator_cfg and len(self.actuator_cfg) > 0 and 
            self.actuator_freq > 0):
            if not hasattr(self, 'actuator_read_timer'):
                self.actuator_read_timer = QTimer()
                self.actuator_read_timer.timeout.connect(self.read_actuators_by_cfg)
            self.actuator_read_timer.stop()
            if self.actuator_freq > 0:
                self.actuator_read_timer.start(self.actuator_freq * 1000)

    def on_mqtt_disconnected(self):
        self.mqtt_status_label.setText("MQTT: ❌ disconnected")
        self.mqtt_status_label.setStyleSheet("color: red; font-weight: bold;")
        self.mqtt_connect_btn.setEnabled(True)
        self.mqtt_disconnect_btn.setEnabled(False)
        self.status_message_label.setText("")
        if self.read_timer.isActive():
            self.read_timer.stop()
        if self.mqtt_tenant_id_input.text().strip():
            self.status_message_label.setText(f"已订阅设备配置主题 (Tenant: {self.mqtt_tenant_id_input.text().strip()})")

    def on_mqtt_message_received(self, topic, payload):
        # 这里可以把收到的消息显示在界面上（你目前没有输出面板，可以自行添加 QTextEdit）
        try:
            data = json.loads(payload)
            # topic_parts = topic.split('/')
            topic_postfix = data.get("action")
            
            if topic_postfix == "cfg":
                self.handle_config_message(data)

            elif topic_postfix == "action":
                self.handle_action_message(data)
                
        except json.JSONDecodeError:
            print(f"Received non-JSON MQTT message on topic {topic}: {payload}")
        except Exception as e:
            print(f"Error processing MQTT message: {e}")

    def handle_action_message(self, data):
        control_mode = data.get("control_mode", "BINARY")
        action_data = data.get("data")
        if control_mode == "BINARY":
            slave_id = action_data.get("slave_id", 100)
            address = action_data.get("coil_ch", 0)
            val = action_data.get("val", False)
            device_id = action_data.get("device_id")
            coil_address = action_data.get("coil_address")
            coil_count = action_data.get("coil_count")
                    
            if not self.check_acutator_status_equal_by_ch(device_id=device_id,ch=address,val=val):
                        # 发给继电器
                self.client.write_single_coil_with_slaveid(
                            slave_id=slave_id,
                            address=address,
                            value=val
                        )
                # 返回device的actuator的状态
                self.last_actuator_states[device_id] = self.client.read_coils(
                            start_addr=coil_address, count=coil_count, slave_id=slave_id)
                
                self.relay_status = self.last_actuator_states[device_id][:self.coil_count_spin.value()]
                self.update_coils_display()
                
                current_states = {}
                current_states[device_id] = self.last_actuator_states[device_id]
                output_json = {
                    "type": "action",
                    "device_sn": self.mqtt.device_sn,
                    "timestamp": int(time.time()),
                    "control_mode": control_mode,
                    "action": "actuator_status",
                    "data": current_states
                }
                publish_topic = f"tenants/{self.mqtt_tenant_id_input.text().strip()}/devices/{self.mqtt.device_sn}/telemetry"
                self.mqtt.publish(publish_topic, json.dumps(output_json), qos=0)
        elif control_mode == "ANALOG":
                # 这个是控制模拟信号的action
                # 首先检查这个有没有前置限制条件，如果有，看看前置条件是否满足
                # 满足前置条件或者没有前置条件则继续进行。
                if "prerequisite" in action_data:
                    # 检查到前置条件，那么去找前置条件是否满足
                    prerequisite = action_data.get("prerequisite")
                    # 找到
                    prerequsite_device_id = prerequisite.get("device_id")
                    # 使用这个prerequsite_device_id 去找紫铜中保存的该device的继电器状态
                    device_states = self.last_actuator_states[prerequsite_device_id]
                    # 获取通路蚕食
                    channel = prerequisite.get("coil_ch")
                    
                    current_state = device_states[channel]
                    required_state = prerequisite.get("required_state")
                    
                    if current_state != required_state:
                        # 不满足前置条件，直接退出
                        return
                    # 满足条件以后，写保持寄存器
                slave_id = action_data.get("slave_id", 100)
                address = action_data.get("reg_address")
                val = action_data.get("val", 0)
                if self.client.write_single_holding_register(address=address, value=val, slave_id=slave_id):
                    # 更新last_actuator_states
                    self.last_actuator_states[device_id] = val
                else:
                    return
                current_states = {}
                current_states[device_id] = self.last_actuator_states[device_id]
                output_json = {
                    "type": "action",
                    "device_sn": self.mqtt.device_sn,
                    "timestamp": int(time.time()),
                    "control_mode": control_mode,
                    "action": "actuator_status",
                    "data": current_states
                }
                publish_topic = f"tenants/{self.mqtt_tenant_id_input.text().strip()}/devices/{self.mqtt.device_sn}/telemetry"
                self.mqtt.publish(publish_topic, json.dumps(output_json), qos=0)
                

    def handle_config_message(self, data):
        updated = False
                
                # 原有 cfg 和 freq
        if "cfg" in data and isinstance(data.get("cfg"), list):
            self.current_cfg = data["cfg"]
            updated = True

        if "freq" in data:
            self.freq_seconds = int(data["freq"])
            updated = True
                    
        if "actuator_cfg" in data and isinstance(data.get("actuator_cfg"), list):
            self.actuator_cfg = data["actuator_cfg"]
            updated = True

        if "actuator_freq" in data:
            self.actuator_freq = int(data["actuator_freq"])
            updated = True

        if updated:
            self.status_message_label.setText(
                        f"收到配置更新 | 普通Tag: {len(self.current_cfg)} | 执行器: {len(self.actuator_cfg)} | "
                        f"Freq: {self.freq_seconds}s | Actuator Freq: {self.actuator_freq}s"
                    )
                    
                    # === 关键：同步更新界面上的频率输入框 ===
            try:
                self.freq_input.valueChanged.disconnect(self.on_freq_changed)
                self.freq_input.setValue(self.freq_seconds)
                self.actuator_freq_input.setValue(self.actuator_freq)
                self.freq_input.valueChanged.connect(self.on_freq_changed)
            except:
                self.freq_input.setValue(self.freq_seconds)
                    
                    
            self.save_current_cfg()
                    
            if self.read_timer.isActive():
                self.read_timer.stop()
            if self.freq_seconds > 0:
                self.read_timer.start(self.freq_seconds * 1000)
            
    def read_modbus_by_cfg(self):
        """ 根据当前 self.current_cfg 读取 Modbus 数据并通过 MQTT 发布结果 """
        if not self.current_cfg:
            return
        if not self.client or not self.client.connected:
            self.status_message_label.setText("warning: Modbus client not connected, cannot read data by cfg")
            return
        
        result_dict = {}
        
        for item in self.current_cfg:
            try:
                sensor_id = item.get('id')
                tag_code = item.get("tag_code")
                slave_id = item.get("slave_id", 1)
                reg_address = item.get("reg_address", 0)
                count = item.get("count", 1)
                data_type = item.get("data_type", "uint16")
                scale = item.get("scale", 1.0)
                
                # 调用 Modbus 读取（注意：你的 ModbusRTUClient 需要支持 slave_id 参数）
                read_timestamp = time.time_ns() 
                value = self.client.read_data_with_slave(
                    add=reg_address,
                    count=count,
                    converter=None,           # 我们自己处理转换
                    little_endian=False,      # 可根据需要调整
                    slave_id=slave_id         # 关键：指定 slave_id
                )
                # 根据 data_type 进行转换
                converted = self.convert_modbus_value(value, data_type)
                final_value = converted * scale if isinstance(converted, (int, float)) else converted
                
                result_dict[tag_code] = {
                    "sensor_id": sensor_id,
                    "value": final_value,
                    "timestamp": read_timestamp
                }
            except Exception as e:
                print(f"Reading {tag_code} failed: {e}")
                result_dict[tag_code] = None
        
        # update LED display
        self.update_realtime_display(result_dict)
                
        # 构建最终 JSON 并发布
        output_json = {
            "type": "data",
            "device_sn": self.mqtt.device_sn,
            "timestamp": int(time.time()),
            "data": result_dict
        }
        
        # 发布结果（推荐发布到数据上报主题）
        publish_topic = f"tenants/{self.mqtt_tenant_id_input.text().strip()}/devices/{self.mqtt.device_sn}/telemetry"
        if not self.pause_mqtt_publish:
            self.mqtt.publish(publish_topic, json.dumps(output_json), qos=1)
        else:
            self.current_output = output_json  # 暂存当前输出，等恢复发布时一起发布
        self.status_message_label.setText(f"Read and published {len(result_dict)} tags")
        print(f"Published to MQTT: {output_json}")

    def read_actuators_by_cfg(self):
        """Read the discrete input states (function code 02) from 
        actuator_cfg, and report MQTT only when changes occur."""
        if not self.actuator_cfg:
            return
        if not self.client or not self.client.connected:
            return
        
        current_states = {}
        changed = False
        
        for item in self.actuator_cfg:
            try:
                if "actuator_type" in item and item["actuator_type"] == "ANALOG_MODULE":
                    continue  # 跳过模拟量模块的状态读取
                else:
                    device_id = item.get('id')
                    slave_id = item.get("slave_id", 1)
                    reg_address = item.get("reg_address", 0)
                    coil_count = item.get("coil_count", 8)
                    # 这里调用client读取 离散状态 02功能码
                    states = self.client.read_coils(
                        start_addr=reg_address,
                        count=coil_count,
                        slave_id=slave_id
                    )
                    if states is not None:
                        current_states[device_id] = states
                        
                        last_states = self.last_actuator_states.get(device_id)
                        if last_states != states:
                            changed = True
                            print(f"Actuator {device_id} 状态变化: {last_states} -> {states}")
                    else:
                        print(f"读取离散输入失败: {device_id}")
                    
            except Exception as e:
                print(f"读取 actuator {device_id} 失败: {e}")

        # 更新缓存
        self.last_actuator_states = current_states.copy()
        self.update_realtime_display(None)
        
        if changed and  current_states:
            print("实现发出actuator states 变化数据")
            output_json = {
                "type": "action",
                "device_sn": self.mqtt.device_sn,
                "timestamp": int(time.time()),
                "action": "actuator_status",
                "data": current_states
            }

            publish_topic = f"tenants/{self.mqtt_tenant_id_input.text().strip()}/devices/{self.mqtt.device_sn}/telemetry"
            
            if not self.pause_mqtt_publish:
                self.mqtt.publish(publish_topic, json.dumps(output_json), qos=1)
                self.status_message_label.setText(f"Actuator 状态变化已上报 | {len(current_states)} 个")
            else:
                self.current_output = output_json
            

    def on_mqtt_error(self, error_msg):
        self.status_message_label.setText(f"MQTT 错误: {error_msg}")
        self.mqtt_status_label.setText("MQTT: 连接失败")
        self.mqtt_status_label.setStyleSheet("color: red;")

        QMessageBox.warning(
            self,
            "MQTT Connection Failed",
            error_msg
    )
        
    def on_device_sn_generated(self, sn: str):
        """接收生成的设备 SN"""
        self.sn_label.setText(f"SN: {sn}")
        
    def show_sn_context_menu(self, pos):
        """右键 SN Label 时弹出菜单"""
        if not hasattr(self.mqtt, 'device_sn') or not self.mqtt.device_sn:
            return

        menu = QMenu(self)

        copy_action = QAction("复制 SN", self)
        copy_action.triggered.connect(self.copy_sn_to_clipboard)
        menu.addAction(copy_action)
        menu.exec_(self.sn_label.mapToGlobal(pos))

    def copy_sn_to_clipboard(self):
        """将当前 SN 复制到剪贴板"""
        if hasattr(self.mqtt, 'device_sn') and self.mqtt.device_sn:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.mqtt.device_sn)
            
            # 提示用户已复制
            self.status_message_label.setText(f"已复制 SN: {self.mqtt.device_sn}")
            
            # 可选：短暂显示提示后恢复
            QTimer.singleShot(3000, lambda: self.status_message_label.setText(""))
            
            QMessageBox.information(self, "复制成功", f"设备 SN 已复制到剪贴板：\n{self.mqtt.device_sn}")
        else:
            QMessageBox.warning(self, "提示", "当前没有可用的设备 SN")

    def convert_modbus_value(self, value, data_type: str):
        """根据 data_type 转换 Modbus 返回值"""
        if not value:
            return None
            
        try:
            if data_type == "uint16":
                return int(value[0]) if isinstance(value, list) else int(value)
            elif data_type == "int16":
                raw = int(value[0]) if isinstance(value, list) else int(value)
                return raw if raw < 32768 else raw - 65536
            elif data_type == "uint32":
                # 假设返回的是两个寄存器
                if isinstance(value, list) and len(value) >= 2:
                    return (value[0] << 16) | value[1]
                return int(value)
            elif data_type == "float":
                # 需要根据你的 Modbus 客户端实际返回格式调整
                return float(value[0]) if isinstance(value, list) else float(value)
            else:
                return value
        except:
            return value
        
    # def update_realtime_display(self, sensor_dict: dict = None):
    #     """更新实时数据 LED 显示"""
    #     # 清空旧的显示
    #     while self.realtime_display.count():
    #         child = self.realtime_display.takeAt(0)
    #         if child.widget():
    #             child.widget().deleteLater()

    #     if not sensor_dict and not hasattr(self, 'last_actuator_states'):
    #         no_data = QLabel("暂无数据")
    #         no_data.setStyleSheet("color: #888; font-size: 14px;")
    #         self.realtime_display.addWidget(no_data)
    #         return
        
    #     # ==================== 1. 显示普通 Sensor 数据 ====================
    #     if sensor_dict:
    #         title_sensor = QLabel("Sensor Data")
    #         title_sensor.setStyleSheet("font-weight: bold; color: #00ffcc; font-size: 16px;")
    #         self.realtime_display.addWidget(title_sensor)

    #         for tag, value in sensor_dict.items():
    #             h_layout = QHBoxLayout()
                
    #             tag_label = QLabel(f"{tag}:")
    #             tag_label.setStyleSheet("color: #aaaaaa; font-size: 14px; min-width: 180px;")
                
    #             value_str = str(value['value'])
    #             value_label = QLabel(value_str)
    #             value_label.setStyleSheet("""
    #                 QLabel {
    #                     background-color: #003300;
    #                     color: #00ff88;
    #                     font-size: 16px;
    #                     font-weight: bold;
    #                     padding: 6px 12px;
    #                     border: 2px solid #00cc66;
    #                     border-radius: 6px;
    #                     min-width: 120px;
    #                 }
    #             """)
                
    #             h_layout.addWidget(tag_label)
    #             h_layout.addWidget(value_label)
    #             h_layout.addStretch()
                
    #             container = QWidget()
    #             container.setLayout(h_layout)
    #             self.realtime_display.addWidget(container)
                
    #     # ==================== 2. 显示 Actuator 状态（使用自定义控件） ====================
    #     if hasattr(self, 'last_actuator_states') and self.last_actuator_states:
    #         title_act = QLabel("Actuator Status (Discrete Inputs)")
    #         title_act.setStyleSheet("font-weight: bold; color: #00ccff; font-size: 16px; margin-top: 10px;")
    #         self.realtime_display.addWidget(title_act)

    #         for device_id, states in self.last_actuator_states.items():
    #             actuator_widget = ActuatorStatusWidget(device_id, states)
    #             self.realtime_display.addWidget(actuator_widget)

    def update_realtime_display(self, sensor_dict: dict = None):
        """
        更新实时数据 LED 显示（支持左右分栏局部增量刷新，互不干涉）
        """
        # ==================== 1. 定向更新左侧 Sensor 区域 ====================
        # 只有在传入了有效的传感器字典时，才刷新左边
        if sensor_dict is not None:
            # 🌟 精准清空：只铲除左侧传感器容器里的旧组件，右侧安然无恙
            while self.sensor_data_container.count():
                child = self.sensor_data_container.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

            if sensor_dict:
                title_sensor = QLabel("Sensor Data")
                title_sensor.setStyleSheet("font-weight: bold; color: #00ffcc; font-size: 16px;")
                self.sensor_data_container.addWidget(title_sensor)

                for tag, value in sensor_dict.items():
                    h_layout = QHBoxLayout()
                    
                    tag_label = QLabel(f"{tag}:")
                    tag_label.setStyleSheet("color: #aaaaaa; font-size: 14px; min-width: 180px;")
                    
                    value_str = str(value['value'])
                    value_label = QLabel(value_str)
                    value_label.setStyleSheet("""
                        QLabel {
                            background-color: #003300;
                            color: #00ff88;
                            font-size: 16px;
                            font-weight: bold;
                            padding: 6px 12px;
                            border: 2px solid #00cc66;
                            border-radius: 6px;
                            min-width: 120px;
                        }
                    """)
                    
                    h_layout.addWidget(tag_label)
                    h_layout.addWidget(value_label)
                    h_layout.addStretch()
                    
                    container = QWidget()
                    container.setLayout(h_layout)
                    self.sensor_data_container.addWidget(container)
            else:
                # 传入的是空字典 {}
                no_data = QLabel("暂无传感器数据")
                no_data.setStyleSheet("color: #888; font-size: 14px;")
                self.sensor_data_container.addWidget(no_data)
            
            # 垫个弹簧保持左侧紧凑
            self.sensor_data_container.addStretch(1)

        # ==================== 2. 定向更新右侧 Actuator 区域 ====================
        # 无论传感器带不带数据，只要内存里有执行器数据，或者显式触发了更新，就只刷新右边
        # 如果你不希望每次更新传感器都重绘右边，可以加个控制。这里我们让它在有状态、或者显式更新时起作用。
        # 优雅策略：如果是常规传感器轮询，右边可以不重复绘制；但为了保险，我们让它在有变动时才单独重绘
        
        # 🌟 完美的解耦刷新逻辑：
        # 如果传感器数据为 None（说明是执行器任务单独触发），或者日常传感器更新时顺便检查右侧是否为空
        if sensor_dict is None or self.actuator_data_container.count() == 0:
            
            # 🌟 精准清空：只铲除右侧执行器容器里的旧组件，左侧传感器由于没有被铲除，数字绝不会跳动或闪烁
            while self.actuator_data_container.count():
                child = self.actuator_data_container.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

            if hasattr(self, 'last_actuator_states') and self.last_actuator_states:
                title_act = QLabel("Actuator Status (Discrete Inputs)")
                title_act.setStyleSheet("font-weight: bold; color: #00ccff; font-size: 16px;")
                self.actuator_data_container.addWidget(title_act)

                for device_id, states in self.last_actuator_states.items():
                    actuator_widget = ActuatorStatusWidget(device_id, states)
                    self.actuator_data_container.addWidget(actuator_widget)
            else:
                no_act_data = QLabel("暂无执行器状态")
                no_act_data.setStyleSheet("color: #888; font-size: 14px;")
                self.actuator_data_container.addWidget(no_act_data)
                
            # 垫个弹簧保持右侧紧凑
            self.actuator_data_container.addStretch(1)
            
    def closeEvent(self, event):
        """窗口关闭时保存配置"""
        self.save_mqtt_settings()
        self.save_current_cfg()
        event.accept()

    def relay_turn_on(self):
        """打开指定继电器通道"""
        if not self._check_client_ready():
            return
        ch = self.relay_channel_spin.value()
        success = self.client.write_single_coil(ch, True)
        if success:
            self.relay_status[ch] = True
            self.status_message_label.setText(f"继电器 CH{ch} 已打开 (ON)")
            self.update_coils_display()   # 刷新显示
        else:
            QMessageBox.warning(self, "失败", f"打开继电器 CH{ch} 失败")

    def relay_turn_off(self):
        """关闭指定继电器通道"""
        if not self._check_client_ready():
            return
        ch = self.relay_channel_spin.value()
        success = self.client.write_single_coil(ch, False)
        if success:
            self.relay_status[ch] = False
            self.status_message_label.setText(f"继电器 CH{ch} 已关闭 (OFF)")
            self.update_coils_display()
        else:
            QMessageBox.warning(self, "失败", f"关闭继电器 CH{ch} 失败")

    def relay_toggle(self):
        """翻转指定继电器通道"""
        if not self._check_client_ready():
            return
        ch = self.relay_channel_spin.value()
        # 当前状态取反
        new_state = not self.relay_status[ch] if ch < len(self.relay_status) else True
        success = self.client.write_single_coil(ch, new_state)
        if success:
            self.relay_status[ch] = new_state
            self.status_message_label.setText(f"继电器 CH{ch} 已翻转 → {'ON' if new_state else 'OFF'}")
            self.update_coils_display()
        else:
            QMessageBox.warning(self, "失败", f"翻转继电器 CH{ch} 失败")

    def relay_flash(self):
        """闪开（延时断开）"""
        if not self._check_client_ready():
            return
            
        ch = self.relay_channel_spin.value()
        delay_ms = self.flash_delay_spin.value()
        
        print(f"【调试】准备调用 flash_coil, CH={ch}, delay={delay_ms}ms")   # ← 加这行
        
        success = self.client.flash_coil(ch, delay_ms=delay_ms)
        
        if success:
            self.status_message_label.setText(f"CH{ch} 已触发闪开 {delay_ms}ms")
            QTimer.singleShot(delay_ms + 600, self.read_coils_status)
        else:
            QMessageBox.warning(self, "失败", f"闪开命令发送失败 (CH{ch} {delay_ms}ms)")


    def append_log(self, direction: str, data: bytes):
        """向日志区域添加收发报文"""
        if not self.log_text or not self.log_visible:
            return
            
        timestamp = time.strftime("%H:%M:%S")
        hex_data = data.hex().upper()
        
        if direction == "TX":
            color = "#00ccff"   # 发送用蓝色
            text = f"[{timestamp}] TX → {hex_data}"
        else:
            color = "#00ff88"   # 接收用绿色
            text = f"[{timestamp}] RX ← {hex_data}"
        
        self.log_text.append(f'<span style="color:{color}">{text}</span>')
        
        # 自动滚动到底部
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
        
    def append_log_raw(self, text: str):
        """添加原始串口报文或普通文本到日志"""
        if not self.log_text or not self.log_visible:
            return
        
        # if self.is_controlling_now and "01 01" in text:
        #     return

        # 1. 安全防护：限制最大行数（例如 500 行），防止密集串口数据导致界面卡死
        if self.log_text.document().blockCount() > 500:
            cursor = self.log_text.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.select(cursor.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()  # 删除换行符

        # 2. 插入文本
        self.log_text.append(text)
        
        # 3. 自动滚动到底部
        scrollbar = self.log_text.verticalScrollBar()
        if scrollbar:
            scrollbar.setValue(scrollbar.maximum())

    def clear_log(self):
        """清除日志"""
        if self.log_text:
            self.log_text.clear()

    def _check_client_ready(self):
        """检查串口是否准备好"""
        if not self.client or not self.client.connected:
            QMessageBox.warning(self, "警告", "请先打开串口！")
            return False
        return True
