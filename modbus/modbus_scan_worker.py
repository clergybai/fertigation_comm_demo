import time
import json
import threading
from PyQt5.QtCore import QObject, pyqtSignal, QTimer, pyqtSlot
import threading


class ModbusScanWorker(QObject):
    sensor_data_ready = pyqtSignal(dict)
    actuator_status_ready = pyqtSignal(dict, bool)  # states, changed
    action_result_ready = pyqtSignal(dict)
    relay_command_finished = pyqtSignal(dict)
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
        self.modbus_lock = threading.Lock()

    @pyqtSlot()
    def start_loop(self):
        """在 worker thread 中启动扫描定时器"""
        self.running = True

        self.sensor_timer = QTimer(self)
        self.sensor_timer.timeout.connect(self._on_sensor_timer_timeout)

        self.actuator_timer = QTimer(self)
        self.actuator_timer.timeout.connect(self._on_actuator_timer_timeout)

        if self.current_cfg and self.freq_seconds > 0:
            self.sensor_timer.start(self.freq_seconds * 1000)

        if self.actuator_cfg and self.actuator_freq > 0:
            self.actuator_timer.start(self.actuator_freq * 1000)

    @pyqtSlot()
    def _on_sensor_timer_timeout(self):
        if not self.running or self.paused:
            return

        with self.config_lock:
            current_cfg = list(self.current_cfg)

        if not current_cfg:
            return

        self._scan_sensor_once(current_cfg)


    @pyqtSlot()
    def _on_actuator_timer_timeout(self):
        if not self.running or self.paused:
            return

        with self.config_lock:
            actuator_cfg = list(self.actuator_cfg)

        if not actuator_cfg:
            return

        self._scan_actuator_once(actuator_cfg)

    @pyqtSlot()
    def stop_loop(self):
        self.running = False

        if hasattr(self, "sensor_timer"):
            self.sensor_timer.stop()

        if hasattr(self, "actuator_timer"):
            self.actuator_timer.stop()

    @pyqtSlot(dict)
    def update_config(self, cfg_data: dict):
        """更新扫描配置，并重启 worker 内部 timer"""
        with self.config_lock:
            self.current_cfg = cfg_data.get("cfg", [])
            self.freq_seconds = cfg_data.get("freq", 300)
            self.actuator_cfg = cfg_data.get("actuator_cfg", [])
            self.actuator_freq = cfg_data.get("actuator_freq", 300)

            current_cfg = list(self.current_cfg)
            actuator_cfg = list(self.actuator_cfg)
            freq_seconds = self.freq_seconds
            actuator_freq = self.actuator_freq

        if hasattr(self, "sensor_timer"):
            self.sensor_timer.stop()
            if current_cfg and freq_seconds > 0:
                self.sensor_timer.start(freq_seconds * 1000)

        if hasattr(self, "actuator_timer"):
            self.actuator_timer.stop()
            if actuator_cfg and actuator_freq > 0:
                self.actuator_timer.start(actuator_freq * 1000)

    @pyqtSlot(dict)
    def enqueue_action(self, action_data: dict):
        """MQTT action：在 worker thread 中执行一次 Modbus action"""
        breakpoint()
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
            
                with self.modbus_lock:
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

                with self.modbus_lock:
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
            control_mode = action_data.get("control_mode", "BINARY")
            device_id = action_data.get("device_id")

            if control_mode == "BINARY":
                slave_id = action_data.get("slave_id", 100)
                address = action_data.get("coil_ch", 0)
                val = action_data.get("val", False)
                coil_address = action_data.get("coil_address", 0)
                coil_count = action_data.get("coil_count", 8)

                last_status_vals = self.last_actuator_states.get(device_id)
                if last_status_vals and len(last_status_vals) > address:
                    if last_status_vals[address] == val:
                        self.action_result_ready.emit({
                            "device_id": device_id,
                            "states": last_status_vals,
                            "changed": False,
                            "control_mode": control_mode,
                            "message": "Action skipped because state is already equal",
                        })
                        return

                with self.modbus_lock:
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
                    "control_mode": control_mode,
                    "message": "Action executed",
                })
                return

            if control_mode == "ANALOG":
                breakpoint()
                prerequisite = action_data.get("prerequisite")
                if prerequisite:
                    prerequisite_device_id = prerequisite.get("device_id")
                    device_states = self.last_actuator_states.get(prerequisite_device_id)
                    channel = prerequisite.get(
                        "coil_ch",
                        prerequisite.get("coil_address", prerequisite.get("reg_address", 0))
                    )
                    required_state = prerequisite.get("required_state")

                    if (
                        not isinstance(device_states, list)
                        or channel >= len(device_states)
                        or device_states[channel] != required_state
                    ):
                        self.action_result_ready.emit({
                            "device_id": device_id,
                            "value": action_data.get("val", 0),
                            "changed": False,
                            "control_mode": control_mode,
                            "message": "Action skipped because prerequisite is not satisfied",
                        })
                        return

                slave_id = action_data.get("slave_id", 100)
                address = action_data.get("reg_address")
                val = action_data.get("val", 0)

                with self.modbus_lock:
                    success = self.client.write_single_holding_register(
                        address=address,
                        value=val,
                        slave_id=slave_id,
                    )

                if not success:
                    self.action_result_ready.emit({
                        "device_id": device_id,
                        "value": val,
                        "changed": False,
                        "control_mode": control_mode,
                        "message": "Analog action failed",
                    })
                    return

                self.last_actuator_states[device_id] = val
                self.action_result_ready.emit({
                    "device_id": device_id,
                    "value": val,
                    "changed": True,
                    "control_mode": control_mode,
                    "message": "Analog action executed",
                })
                return

            self.error_occurred.emit(f"Unsupported control mode: {control_mode}")

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
        
    @pyqtSlot(dict)
    def execute_relay_command(self, command: dict):
        """GUI Relay Control: 在 worker thread 中执行手动继电器控制"""
        channel = command.get("channel", 0)
        checked = command.get("checked", False)
        old_state = command.get("old_state", False)

        try:
            with self.modbus_lock:
                success = self.client.write_single_coil(channel, checked)

            self.relay_command_finished.emit({
                "channel": channel,
                "checked": checked,
                "old_state": old_state,
                "success": success,
            })

        except Exception as e:
            self.relay_command_finished.emit({
                "channel": channel,
                "checked": checked,
                "old_state": old_state,
                "success": False,
                "error": str(e),
            })
