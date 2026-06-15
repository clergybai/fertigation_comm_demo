import time
import json
import queue
import threading
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot


class ModbusScanWorker(QObject):
    sensor_data_ready = pyqtSignal(dict)
    actuator_status_ready = pyqtSignal(dict, bool)  # states, changed
    action_result_ready = pyqtSignal(dict)
    status_message = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, client, mqtt_device_sn_getter=None, parent=None):
        super().__init__(parent)

        self.client = client
        self.mqtt_device_sn_getter = mqtt_device_sn_getter

        self.running = False
        self.paused = False

        self.current_cfg = []
        self.actuator_cfg = []
        self.freq_seconds = 300
        self.actuator_freq = 10

        self.last_sensor_scan_time = 0
        self.last_actuator_scan_time = 0
        self.last_actuator_states = {}

        self.config_lock = threading.Lock()
        self.command_queue = queue.Queue()

    @pyqtSlot()
    def start_loop(self):
        self.running = True
        self.status_message.emit("Modbus scan worker started")

        while self.running:
            try:
                if not self.paused:
                    self._process_command_queue()

                    now = time.time()

                    with self.config_lock:
                        freq_seconds = self.freq_seconds
                        actuator_freq = self.actuator_freq
                        current_cfg = list(self.current_cfg)
                        actuator_cfg = list(self.actuator_cfg)

                    if (
                        current_cfg
                        and freq_seconds > 0
                        and now - self.last_sensor_scan_time >= freq_seconds
                    ):
                        self._scan_sensor_once(current_cfg)
                        self.last_sensor_scan_time = time.time()

                    if (
                        actuator_cfg
                        and actuator_freq > 0
                        and now - self.last_actuator_scan_time >= actuator_freq
                    ):
                        #self._scan_actuator_once(actuator_cfg)
                        self.last_actuator_scan_time = time.time()

                time.sleep(0.05)

            except Exception as e:
                self.error_occurred.emit(f"Scan worker error: {e}")
                time.sleep(0.5)

        self.status_message.emit("Modbus scan worker stopped")

    @pyqtSlot()
    def stop_loop(self):
        self.running = False

    @pyqtSlot(dict)
    def update_config(self, cfg_data: dict):
        with self.config_lock:
            if "cfg" in cfg_data and isinstance(cfg_data.get("cfg"), list):
                self.current_cfg = cfg_data["cfg"]

            if "freq" in cfg_data:
                self.freq_seconds = int(cfg_data["freq"])

            if "actuator_cfg" in cfg_data and isinstance(cfg_data.get("actuator_cfg"), list):
                self.actuator_cfg = cfg_data["actuator_cfg"]

            if "actuator_freq" in cfg_data:
                self.actuator_freq = int(cfg_data["actuator_freq"])

            self.last_sensor_scan_time = time.time()
            self.last_actuator_scan_time = time.time()

    @pyqtSlot(dict)
    def enqueue_action(self, action_data: dict):
        self.command_queue.put(action_data)

    def _process_command_queue(self):
        # 每轮最多处理几个，防止用户疯狂点击导致自动扫描完全饿死
        max_commands_per_loop = 3

        for _ in range(max_commands_per_loop):
            try:
                action_data = self.command_queue.get_nowait()
            except queue.Empty:
                return

            self._execute_action(action_data)

    def _scan_sensor_once(self, cfg_list):
        if not self.client:
            self.status_message.emit("Warning: Modbus client not connected, skip sensor scan")
            return

        result_dict = {}

        for item in cfg_list:
            tag_code = item.get("tag_code")

            try:
                sensor_id = item.get("id")
                slave_id = item.get("slave_id", 1)
                reg_address = item.get("reg_address", 0)
                count = item.get("count", 1)
                data_type = item.get("data_type", "uint16")
                scale = item.get("scale", 1.0)

                read_timestamp = time.time_ns()

                value = self.client.read_data_with_slave(
                    add=reg_address,
                    count=count,
                    converter=None,
                    little_endian=False,
                    slave_id=slave_id,
                )

                time.sleep(0.05)

                converted = self._convert_modbus_value(value, data_type)
                final_value = converted * scale if isinstance(converted, (int, float)) else converted

                result_dict[tag_code] = {
                    "sensor_id": sensor_id,
                    "value": final_value,
                    "timestamp": read_timestamp,
                }

            except Exception as e:
                self.error_occurred.emit(f"Reading {tag_code} failed: {e}")
                result_dict[tag_code] = None

        self.sensor_data_ready.emit(result_dict)

    def _scan_actuator_once(self, actuator_cfg):
        if not self.client:
            return

        current_states = {}
        changed = False

        for item in actuator_cfg:
            try:
                device_id = item.get("id")
                slave_id = item.get("slave_id", 1)
                reg_address = item.get("reg_address", 0)
                coil_count = item.get("coil_count", 8)

                time.sleep(0.05)

                states = self.client.read_coils(
                    start_addr=0,
                    count=coil_count,
                )

                if states is not None:
                    current_states[device_id] = states

                    last_states = self.last_actuator_states.get(device_id)
                    if last_states != states:
                        changed = True
                else:
                    self.error_occurred.emit(f"读取离散输入失败: {device_id}")

            except Exception as e:
                self.error_occurred.emit(f"读取 actuator 失败: {e}")

        self.last_actuator_states = current_states.copy()
        self.actuator_status_ready.emit(current_states, changed)

    def _execute_action(self, action_data):
        if not self.client or not self.client.connected:
            self.error_occurred.emit("Modbus client not connected, action skipped")
            return

        try:
            slave_id = action_data.get("slave_id", 100)
            address = action_data.get("coil_ch", 0)
            val = action_data.get("val", False)
            device_id = action_data.get("device_id")
            coil_address = action_data.get("coil_address", 0)
            coil_count = action_data.get("coil_count", 8)

            last_status_vals = self.last_actuator_states.get(device_id)
            if last_status_vals and len(last_status_vals) > address:
                if last_status_vals[address] == val:
                    self.action_result_ready.emit({
                        "device_id": device_id,
                        "states": last_status_vals,
                        "changed": False,
                        "message": "Action skipped because state is already equal",
                    })
                    return

            self.client.write_single_coil_with_slaveid(
                slave_id=slave_id,
                address=address,
                value=val,
            )

            states = self.client.read_coils(
                start_addr=coil_address,
                count=coil_count,
                slave_id=slave_id,
            )

            if states is not None:
                self.last_actuator_states[device_id] = states

            self.action_result_ready.emit({
                "device_id": device_id,
                "states": states,
                "changed": True,
                "message": "Action executed",
            })

        except Exception as e:
            self.error_occurred.emit(f"Action failed: {e}")

    def _convert_modbus_value(self, value, data_type: str):
        if not value:
            return None

        try:
            if data_type == "uint16":
                return int(value[0]) if isinstance(value, list) else int(value)

            if data_type == "int16":
                raw = int(value[0]) if isinstance(value, list) else int(value)
                return raw if raw < 32768 else raw - 65536

            if data_type == "uint32":
                if isinstance(value, list) and len(value) >= 2:
                    return (value[0] << 16) | value[1]
                return int(value)

            if data_type == "float":
                return float(value[0]) if isinstance(value, list) else float(value)

            return value

        except Exception:
            return value