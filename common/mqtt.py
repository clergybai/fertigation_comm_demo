import sys
import uuid
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QTextEdit, QLineEdit, QLabel
from PyQt5.QtCore import pyqtSignal, QObject
import paho.mqtt.client as mqtt
import time
import ssl

class MqttClient(QObject):
    # 定义 Qt Signal，用于把 MQTT 回调转到主线程更新 UI
    message_received = pyqtSignal(str, str)   # topic, payload
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    connection_error = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    device_sn_generated = pyqtSignal(str)   # 新增信号：设备SN生成后通知界面
    subscribed = pyqtSignal(str) 

    def __init__(self, broker="", port=8883, username=None, password=None, ca_cert_pem=None, parent=None):
        super().__init__(parent)
        self._client = None
        
        # 绑定回调
        # self._client.on_connect = self.on_connect
        # self._client.on_message = self.on_message
        # self._client.on_disconnect = self.on_disconnect
        
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.ca_cert_pem = ca_cert_pem
        self.device_sn = ""
        self.tenant_id = ""
        
    def _create_new_client(self):
        """每次连接前创建一个全新的 Client 对象"""
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except:
                pass
        
        self._client = mqtt.Client(clean_session=True)
        self._client.on_connect = self.on_connect
        self._client.on_message = self.on_message
        self._client.on_disconnect = self.on_disconnect

    def _generate_device_sn(self):
        """使用当前网卡 MAC 地址生成设备 SN（无横杠，12位十六进制）"""
        try:
            # uuid.getnode() 返回当前主要网卡的 MAC 地址（作为整数）
            mac_int = uuid.getnode()
            
            # 转为 12 位十六进制字符串，并转为大写（推荐）
            sn = f"{mac_int:012x}".upper()
            
            self.device_sn = sn
            self.device_sn_generated.emit(sn)   # 发送信号给界面
            
            print(f"设备 SN 已生成: {sn}")
            
        except Exception as e:
            print(f"生成设备 SN 失败: {e}")
            self.device_sn = "UNKNOWN_SN"
            self.device_sn_generated.emit("UNKNOWN_SN")

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected.emit()
            self._generate_device_sn()
            self.subscribe_config_topic()
            self.subscribe_action_topic()
            print("Connected to MQTT Broker!")
        else:
            self.connection_error.emit(f"连接失败，错误码: {rc}")

    def set_tenant_id(self, tenant_id: str):
        """设置 Tenant ID"""
        self.tenant_id = tenant_id.strip()

    def on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode('utf-8')
        except:
            payload = msg.payload.decode('utf-8', errors='replace')
        self.message_received.emit(msg.topic, payload)

    def on_disconnect(self, client, userdata, rc):
        self.disconnected.emit()

    def connect_to_broker(self):
        if not self.broker.strip():
            self.connection_error.emit("Broker 地址不能为空！")
            return

        try:
            self._create_new_client()          # ← 关键：每次都新建 client

            # ==================== TLS 配置（从内存 CA 加载） ====================
            if self.ca_cert_pem:
                context = ssl.create_default_context()
                context.load_verify_locations(cadata=self.ca_cert_pem)
                self._client.tls_set_context(context=context)
            else:
                # 无 CA 时不验证（测试用，生产环境建议提供 CA）
                self._client.tls_set(cert_reqs=ssl.CERT_NONE)

            # 用户名密码
            if self.username and self.password:
                self._client.username_pw_set(self.username, self.password)

            self._client.connect(self.broker, self.port, keepalive=60)
            self._client.loop_start()

        except Exception as e:
            self.connection_error.emit(f"TLS/连接错误: {str(e)}")
            print(f"TLS Error: {e}")


    def disconnect(self):
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except:
                pass
        self.disconnected.emit()

    def subscribe(self, topic: str, qos=0):
        if self._client and self._client.is_connected():
            self._client.subscribe(topic, qos)

    def publish(self, topic: str, payload, qos=0, retain=False):
        if self._client and self._client.is_connected():
            self._client.publish(topic, payload, qos=qos, retain=retain)
        
    def set_ca_cert(self, ca_pem: str):
        """设置 CA 证书内容（字符串）"""
        self.ca_cert_pem = ca_pem.strip() if ca_pem else ""
        
    def subscribe_config_topic(self):
        """订阅 tenants/{tenant_id}/devices/{sn}/cfg 主题"""
        if not self.tenant_id:
            print("Warning: Tenant ID 为空，跳过订阅")
            return
        if not self.device_sn:
            print("Warning: Device SN 还未生成，跳过订阅")
            return

        topic = f"tenants/{self.tenant_id}/devices/{self.device_sn}/cfg"
        
        try:
            if self._client and self._client.is_connected():
                self._client.subscribe(topic, qos=1)   # 使用 QoS 1 更可靠
                self.subscribed.emit(topic)
                print(f"已订阅配置主题: {topic}")
            else:
                print("MQTT Client 未连接，无法订阅")
        except Exception as e:
            print(f"订阅失败: {e}")
            
    def subscribe_action_topic(self):
        """订阅 tenants/{tenant_id}/devices/{sn}/action 主题"""
        if not self.tenant_id:
            print("Warning: Tenant ID 为空，跳过订阅")
            return
        if not self.device_sn:
            print("Warning: Device SN 还未生成，跳过订阅")
            return
        topic = f"tenants/{self.tenant_id}/devices/{self.device_sn}/action"
        try:
            if self._client and self._client.is_connected():
                self._client.subscribe(topic, qos=1)   # 使用 QoS 1 更可靠
                self.subscribed.emit(topic)
                print(f"已订阅配置主题: {topic}")
            else:
                print("MQTT Client 未连接，无法订阅")
        except Exception as e:
            print(f"订阅失败: {e}")


# ==================== PyQt5 界面示例 ====================
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyQt5 MQTT Client")
        layout = QVBoxLayout()

        self.log = QTextEdit()
        self.log.setReadOnly(True)

        self.btn_connect = QPushButton("连接 Broker")
        self.btn_disconnect = QPushButton("断开连接")
        self.btn_publish = QPushButton("发布消息")

        self.topic_input = QLineEdit("test/topic")
        self.payload_input = QLineEdit("Hello from PyQt5!")

        layout.addWidget(QLabel("Topic:"))
        layout.addWidget(self.topic_input)
        layout.addWidget(QLabel("Payload:"))
        layout.addWidget(self.payload_input)
        layout.addWidget(self.btn_connect)
        layout.addWidget(self.btn_disconnect)
        layout.addWidget(self.btn_publish)
        layout.addWidget(self.log)

        self.setLayout(layout)

        self.mqtt = MqttClient()
        self.mqtt.connected.connect(lambda: self.log.append("✅ 已连接到 MQTT Broker"))
        self.mqtt.disconnected.connect(lambda: self.log.append("❌ 已断开连接"))
        self.mqtt.message_received.connect(self.on_message_received)

        self.btn_connect.clicked.connect(self.mqtt.connect_to_broker)
        self.btn_disconnect.clicked.connect(self.mqtt.disconnect)
        self.btn_publish.clicked.connect(self.do_publish)

    def on_message_received(self, topic, payload):
        self.log.append(f"[{topic}] {payload}")

    def do_publish(self):
        topic = self.topic_input.text()
        payload = self.payload_input.text()
        self.mqtt.publish(topic, payload)
        self.log.append(f"已发布 → {topic} : {payload}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())