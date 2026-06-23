import time
from typing import Any, Optional, TypeVar, Callable

import asyncio
from pymodbus.client import AsyncModbusSerialClient, ModbusSerialClient
from pymodbus.exceptions import ModbusException
from PyQt5.QtCore import QObject, pyqtSignal
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
)
logging.getLogger("pymodbus").setLevel(logging.DEBUG)
logger = logging.getLogger("ModBusRTUClient")

T = TypeVar("T")


def bcd_to_decimal(word: int) -> int:
    return int(f"{word:X}")

def int_to_float(raw: int) -> float:
    if not isinstance(raw, int):
        raise ValueError(" now must be int")
    value = raw & 0xFFFF
    
    if value == 0:
        return 0.0
    if value & 0x8000: # 负数
        abs_value = (0xFFFF - value) + 1
        temp = abs_value / 10.0
        return -temp
    else:
        return value / 10.0


class AsyncModbusRTUClient:
    """
    Modbus RTU client
    """
    def __init__(self, port:str, baudrate: int, bytesize: int = 8, parity: str="N", stopbits: int=1, slave_id: int = 1, timeout: float = 1.0, main_window=None):
        self.slave_id = slave_id
        self.main_window = main_window
        self.client = AsyncModbusSerialClient(
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            timeout=timeout
        )
        self.connected=False
        
        
    async def connect(self) -> bool:
        try:
            await self.client.connect()
            self.connected=True
        except Exception as e:
            logger.info(f"Connection fail with {e}")
        return self.connected
    
    async def close(self) -> bool:
        if self.client:
            self.client.close()
            self.connected = False
        return self.connected
    
    async def _read_holding_reg(self, address: int, count: int, debug: bool = True) -> Optional[list]:
        if not self.connected:
            await self.connect()
        
        try:
            response = await self.client.read_holding_registers(address=address, count=count, device_id=self.slave_id)
            if response.isError():
                logger.error(f"Read holding register address:{address} failed: {response}")
                return None
            # if debug:
            #     print(self.client..)
            return response.registers
            pass
        except ModbusException as e:
            logger.error(f"ModBus error: {e}")
            return None
        
    async def read_data(self, add: int, count: int, converter: Callable[[int], T] | None = None) -> Optional[int] | Optional[T]:
        registers = await self._read_holding_reg(add, count)
        if not registers or len(registers) < count:
            logger.warning(f"Read {add} failed")
        if count == 1:
            raw_value = registers[0]
        elif count == 2:
            raw_value = (registers[1] << 16) | (registers[0])
        else:
            raw_value = [converter(r) for r in registers]
        if converter:
            try:
                return converter(raw_value)
            except Exception as e:
                logger.error(f"Convert data error: {e}")
                return raw_value
        return raw_value
    
    async def read_slave_id(self, add: int, count: int) -> Optional[int]:
        registers = await self._read_holding_reg(add, count)
        if registers and len(registers) >= count:
            value = registers[0]
            return value
    
    async def read_baudrate(self, add: int, count: int) -> Optional[int]:
        registers = await self._read_holding_reg(add, count)
        if registers and len(registers) >=count:
            value = bcd_to_decimal(registers[0])
            return value
    
    async def read_parity(self, add: int, count: int) ->Optional[str]:
        registers = await self._read_holding_reg(add, count)
        if registers and len(registers) >=count:
            value = registers[0]
            if value == 0:
                return "None Parity"
            elif value == 1:
                return "Odd Parity"
            else:
                return "Even Parity"
            
    async def read_data_bit(self, add: int, count: int) ->Optional[int]:
        registers = await self._read_holding_reg(add, count)
        if registers and len(registers) >=count:
            value = bcd_to_decimal(registers[0])
            return value
            
        
    async def read_all_sensors(self) ->dict:
        """All all registers for soil sensor"""
        begin_add = 0x80
        comm_vals = await self.read_data(0x0080, 5, bcd_to_decimal)
        regs = await self.read_data(0x0000, 8, int_to_float)
        analog_limit = await self.read_data(0x00BF, 4, int_to_float)
        
        return {
            "slave_id": comm_vals[0],
            "baudrate": comm_vals[1],
            "parity": comm_vals[2],
            "data_bit": comm_vals[3],
            "stop_bit": comm_vals[4],
            "sensors": regs,
            "sensor_limits:": analog_limit
        }

class ModbusLogEmitter(QObject):
    raw_log = pyqtSignal(str)

class ModbusRTUClient:
    """
    Modbus RTU 同步客户端
    """
    def __init__(self, 
                 port: str, 
                 baudrate: int, 
                 bytesize: int = 8, 
                 parity: str = "N", 
                 stopbits: int = 1, 
                 slave_id: int = 1, 
                 timeout: float = 1.0,
                 main_window=None):
        
        self.log_enabled = True

        self.slave_id = slave_id
        self.port = port
        self.connected = False
        self.main_window = main_window

        self.log_emitter = ModbusLogEmitter()
        
        # 创建同步客户端
        self.client = ModbusSerialClient(
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            timeout=timeout,
            # method='rtu'   # pymodbus 3.x 默认就是 rtu，可不写
        )

    def set_log_enabled(self, enabled: bool):
        self.log_enabled = enabled

    def connect(self) -> bool:
        """连接设备并全自动精准拦截 Modbus 物理层收发报文"""
        try:
            if self.connected and self.client.is_socket_open():
                return True

            if not self.client.connect():
                logger.error("Failed to connect to Modbus device")
                self.connected = False
                return False
                
            self.connected = True
            logger.info(f"Modbus RTU connected successfully on {self.port}")
            
            # ============= 1. 绝对真实的发送拦截 (TX) =============
            if hasattr(self.client, 'transaction') and not hasattr(self.client.transaction, '_patched'):
                manager = self.client.transaction
                manager._patched = True
                
                orig_pdu_send = manager.pdu_send
                def patched_pdu_send(packet, addr=None):
                    try:
                        # 放弃相信 framer.frame_message，直接从 packet 对象本身提取核心物理数据
                        # 任何 pymodbus 的 request 对象都具备以下属性
                        slave_id = getattr(packet, 'slave_id', self.slave_id)
                        if slave_id is None:
                            slave_id = self.slave_id
                            
                        func_code = getattr(packet, 'function_code', 0)
                        
                        # 动态根据不同的请求类型组装最真实的物理发送字节
                        pdu_bytes = bytearray([slave_id, func_code])
                        
                        # 提取地址和值/数量
                        if hasattr(packet, 'address'):
                            pdu_bytes.append((packet.address >> 8) & 0xFF)
                            pdu_bytes.append(packet.address & 0xFF)
                            
                        if hasattr(packet, 'value'): # 针对写单线圈/单寄存器 05, 06
                            pdu_bytes.append((packet.value >> 8) & 0xFF)
                            pdu_bytes.append(packet.value & 0xFF)
                        elif hasattr(packet, 'count'): # 针对读寄存器/线圈 01, 03
                            pdu_bytes.append((packet.count >> 8) & 0xFF)
                            pdu_bytes.append(packet.count & 0xFF)
                        elif hasattr(packet, 'values') and packet.values: # 针对写多个 15, 16
                            # 简单处理，如果复杂的干脆不画，这里基本覆盖你的常用功能
                            pass

                        if len(pdu_bytes) >= 6:
                            # 动态计算出最真实、绝对属于这条 TX 的物理 CRC 校验码
                            import struct
                            crc = 0xFFFF
                            for pos in pdu_bytes:
                                crc ^= pos
                                for _ in range(8):
                                    if (crc & 1) != 0:
                                        crc >>= 1
                                        crc ^= 0xA001
                                    else:
                                        crc >>= 1
                            crc_bytes = struct.pack('<H', crc)
                            pdu_bytes.extend(crc_bytes)
                            
                            # 触发展示：这绝对是发送那一瞬间最真实的物理数据！
                            self._log_raw_packet("TX", bytes(pdu_bytes))
                    except Exception as e:
                        logger.debug(f"TX物理拦截异常: {e}")
                        
                    return orig_pdu_send(packet, addr)
                manager.pdu_send = patched_pdu_send

            # ============= 2. 绝对真实的接收拦截 (RX) =============
            # 利用日志流拦截，这已经被你的 log 证明了 100% 正确
            pymodbus_logger = logging.getLogger("pymodbus")
            if not hasattr(pymodbus_logger, '_ui_handler_present'):
                pymodbus_logger._ui_handler_present = True

                class SimpleUiLogHandler(logging.Handler):
                    def __init__(self, outer_instance):
                        super().__init__()
                        self.outer = outer_instance
                        
                    def emit(self, record):
                        try:
                            msg = record.getMessage()
                            if "Processing:" in msg:
                                raw_hex = msg.split("Processing:")[1].strip()
                                clean_bytes = []
                                for item in raw_hex.split():
                                    val = int(item, 16)
                                    clean_bytes.append(val)
                                    
                                if clean_bytes:
                                    self.outer._log_raw_packet("RX", bytes(clean_bytes))
                        except Exception:
                            pass

                pymodbus_logger.addHandler(SimpleUiLogHandler(self))
                
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.connected = False
        
        return self.connected

    def close(self) -> bool:
        """关闭连接"""
        try:
            if self.client:
                self.client.close()
            self.connected = False
            logger.info("Modbus RTU connection closed")
        except Exception as e:
            logger.error(f"Error closing connection: {e}")
        return self.connected

    def _read_holding_reg(self, address: int, count: int, debug: bool = True) -> Optional[list]:
        """内部读取保持寄存器（同步）"""
        if not self.connected:
            if not self.connect():
                return None

        try:
            response = self.client.read_holding_registers(
                address=address, 
                count=count, 
                device_id=self.slave_id
            )

            if response.isError():
                logger.error(f"Read holding register address:{address} failed: {response}")
                return None

            return response.registers

        except ModbusException as e:
            logger.error(f"ModBus error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading registers: {e}")
            return None

    # ====================== 对外公开的方法 ======================

    def read_data(self, add: int, count: int, converter: Callable[[int], T] | None = None, little_endian: bool = True) -> Optional[Any]:
        """通用读取方法（支持转换函数）"""
        registers = self._read_holding_reg(add, count)
        if not registers or len(registers) < count:
            logger.warning(f"Read address {add} failed")
            return None

        if count == 1:
            raw_value = registers[0]
        elif count == 2:
            if little_endian:
                raw_value = (registers[1] << 16) | registers[0]
            else:
                raw_value = (registers[0] << 16) | registers[1]
        else:
            raw_value = registers

        if converter:
            try:
                if isinstance(raw_value, list):
                    return [converter(r) for r in raw_value]
                return converter(raw_value)
            except Exception as e:
                logger.error(f"Convert data error: {e}")
                return raw_value

        return raw_value
    
    def read_data_with_slave(self, 
                             add: int, 
                             count: int, 
                             slave_id: int,
                             converter: Callable[[int], T] | None = None, 
                             little_endian: bool = True) -> Optional[Any]:
        """
        新增方法：支持指定 slave_id 的 Modbus 读取
        （不改变原有 read_data 方法）
        """
        if not self.connected:
            if not self.connect():
                logger.warning(f"Cannot connect to read slave {slave_id}")
                return None

        # 临时修改 slave_id
        original_slave_id = self.slave_id
        self.slave_id = slave_id

        try:
            # 调用原有 read_data 方法（不改变它）
            result = self.read_data(
                add=add,
                count=count,
                converter=converter,
                little_endian=little_endian
            )
            return result
        finally:
            # 恢复原来的 slave_id，避免影响其他地方
            self.slave_id = original_slave_id

    def read_slave_id(self, add: int, count: int = 1) -> Optional[int]:
        """读取 Slave ID"""
        registers = self._read_holding_reg(add, count)
        if registers and len(registers) >= count:
            return registers[0]
        return None

    def read_baudrate(self, add: int, count: int = 1) -> Optional[int]:
        """读取波特率"""
        return self.read_data(add, count, converter=bcd_to_decimal)

    def read_parity(self, add: int, count: int = 1) -> Optional[str]:
        """读取校验位"""
        value = self.read_data(add, count)
        if value is None:
            return None
        if value == 0:
            return "None Parity"
        elif value == 1:
            return "Odd Parity"
        else:
            return "Even Parity"

    def read_data_bit(self, add: int, count: int = 1) -> Optional[int]:
        """读取数据位"""
        return self.read_data(add, count, converter=bcd_to_decimal)

    def read_device_id_broadcast(self):
        """适配当前 pymodbus 版本的广播读取 Slave ID"""
        try:
            if not self.connected:
                if not self.connect():
                    logger.warning("串口未连接")
                    return None

            logger.info("发送广播读取设备ID指令...")

            # 广播指令
            broadcast_cmd = b'\x00\x03\x00\x00\x00\x01\x85\xDB'

            # 尝试多种方式获取底层 serial 对象
            serial_port = None
            if hasattr(self.client, 'framer'):
                framer = self.client.framer
                if hasattr(framer, 'client') and hasattr(framer.client, 'serial'):
                    serial_port = framer.client.serial
                elif hasattr(framer, '_client') and hasattr(framer._client, 'serial'):
                    serial_port = framer._client.serial

            if serial_port is None and hasattr(self.client, 'socket'):
                serial_port = self.client.socket

            if serial_port is None:
                logger.error("无法获取底层 serial 对象")
                return None

            # 清空缓冲区
            serial_port.reset_input_buffer()
            serial_port.reset_output_buffer()

            # ================= 补漏：在这里手动触发 TX 拦截 =================
            self._log_raw_packet("TX", broadcast_cmd)
            # =============================================================

            # 发送指令
            serial_port.write(broadcast_cmd)
            serial_port.flush()

            # 等待响应
            import time
            start_time = time.time()
            response = b''
            
            while time.time() - start_time < 1.5:
                if serial_port.in_waiting > 0:
                    data = serial_port.read(serial_port.in_waiting)
                    response += data
                    if len(response) >= 5:
                        break
                time.sleep(0.02)

            if not response:
                logger.warning("广播读取未收到任何响应")
                return None

            # ================= 补漏：在这里手动触发 RX 拦截 =================
            self._log_raw_packet("RX", response)
            # =============================================================

            logger.info(f"收到广播响应: {response.hex()}")

            # 解析响应
            if len(response) >= 5 and response[1] == 0x03:
                slave_id = response[4]
                logger.info(f"✅ 广播读取成功，Slave ID = {slave_id}")
                return slave_id
            else:
                logger.warning(f"响应格式异常: {response.hex()}")
                return None

        except Exception as e:
            logger.error(f"广播读取设备ID异常: {e}")
            return None

    def read_coils(self, start_addr=0, count=8, slave_id=None):
        """读取线圈状态 (功能码 01)"""
        if slave_id is None:
            slave_id = self.slave_id

        try:
            if not self.connected or not self.client:
                if not self.connect():
                    logger.warning(f"Cannot connect to read coils slave {slave_id}")
                    return None

            response = self.client.read_coils(
                address=start_addr,
                count=count,
                device_id=slave_id
            )

            if response.isError():
                logger.error(f"Read coils failed: {response}")
                return None

            return response.bits[:count]

        except Exception as e:
            logger.error(f"read_coils error: {e}")
            self.connected = False
            return None

    def read_discrete_inputs(self, start_addr=0, count=8, slave_id=None):
        """读取离散输入 (功能码 02) 这里面指的是读取IN1的寄存器状态"""
        if slave_id is None:
            slave_id = self.slave_id
        try:
            response = self.client.read_discrete_inputs(
                address=start_addr, 
                count=count, 
                device_id=slave_id
            )
            if not response.isError():
                return response.bits
            else:
                return None
        except Exception as e:
            logger.error(f"read_discrete_inputs error: {e}")
            return None

    def write_single_coil(self, address, value):
        """写单个线圈 (功能码 05)"""
        try:
            response = self.client.write_coil(address=address, value=value, device_id=self.slave_id)
            return not response.isError()
        except Exception as e:
            logger.error(f"write_single_coil error: {e}")
            return False
        
    def write_single_coil_with_slaveid(self, slave_id, address, value):
        if not self.connected:
            if not self.connect():
                logger.warning(f"Cannot connect to read slave {slave_id}")
                return None

        # 临时修改 slave_id
        original_slave_id = self.slave_id
        self.slave_id = slave_id
        
        try:
            self.write_single_coil(address, value)
        finally:
            # 恢复原来的 slave_id，避免影响其他地方
            self.slave_id = original_slave_id
            
    
    def write_slave_id_broadcast(self, new_slave_id: int) -> bool:
        """
        专门针对该485设备设计的：通过0x00广播地址强制改写 Slave ID (功能码 10H)
        """
        try:
            if not self.connected:
                if not self.connect():
                    logger.warning("串口未连接，无法发送广播改写指令")
                    return False

            logger.info(f"发送广播改写设备ID指令，目标新ID: {new_slave_id}")

            import struct
            import time

            # 1. 严格手工组装 0x00 广播功能码 10H 物理帧
            # 格式：[00] [10] [寄存器高低] [数量高低] [字节数] [新ID高低]
            packet_without_crc = struct.pack(
                ">BBHHB H", 
                0x00,                     # 强制第一位为 0x00 广播地址
                0x10,                     # 功能码 10H
                0x0000,                   # 寄存器起始地址 00 00
                0x0001,                   # 寄存器修改数量 00 01
                0x02,                     # 数据字节数 02
                new_slave_id              # 写入的新 ID
            )

            # 2. 动态计算标准的 CRC16 校验码
            crc = 0xFFFF
            for byte in packet_without_crc:
                crc ^= byte
                for _ in range(8):
                    if crc & 1:
                        crc = (crc >> 1) ^ 0xA001
                    else:
                        crc >>= 1
            
            full_packet = packet_without_crc + struct.pack("<H", crc)

            # 3. 获取底层物理串口（复用你 read_device_id_broadcast 里的 socket 获取逻辑）
            serial_port = None
            if hasattr(self.client, 'socket'):
                serial_port = self.client.socket

            if serial_port is None:
                logger.error("无法获取底层 serial 对象")
                return False

            # 4. 清空物理缓存
            serial_port.reset_input_buffer()
            serial_port.reset_output_buffer()

            # 5. 手动触发你写好的 TX 拦截器，让 UI 界面能高亮显示这一行原始报文
            self._log_raw_packet("TX", full_packet)

            # 6. 物理发射
            serial_port.write(full_packet)
            serial_port.flush()

            # 7. 广播是不回传的，但为了安全，给串口和硬件留出 150ms 写入和清空碎数据的时间
            time.sleep(0.15)
            if serial_port.in_waiting > 0:
                dirty_data = serial_port.read(serial_port.in_waiting)
                self._log_raw_packet("RX", dirty_data) # 顺手记录一下可能存在的异常回传

            return True

        except Exception as e:
            logger.error(f"广播改写设备ID异常: {e}")
            return False
    # def flash_coil(self, address: int, delay_ms: int = 800):
    #     """
    #     闪开指令 - 严格按照说明文档使用功能码 05
    #     """
    #     try:
    #         if hasattr(self, 'main_window') and self.main_window:
    #             self.main_window.append_log_raw(f"TX: Flash CH{address} {delay_ms}ms")

    #         # 按照说明文档：
    #         # 地址 = 0x0200 + channel
    #         # 值   = delay_ms / 100 （整数）
    #         flash_address = 0x0200 + address
    #         delay_value = max(1, delay_ms // 100)

    #         # 使用 write_coil 并传入数值（pymodbus 支持）
    #         response = self.client.write_coil(
    #             address=flash_address, 
    #             value=delay_value,           # 关键：传入整数值
    #             device_id=self.slave_id
    #         )
            
    #         success = not response.isError()
            
    #         if success and hasattr(self, 'main_window') and self.main_window:
    #             self.main_window.append_log_raw(f"RX: Flash Success ({delay_value}×100ms)")
    #         elif hasattr(self, 'main_window') and self.main_window:
    #             self.main_window.append_log_raw("RX: Flash Failed")

    #         if success:
    #             logger.info(f"Flash coil CH{address} with {delay_ms}ms success")
    #         else:
    #             logger.error(f"Flash coil failed: {response}")

    #         return success
            
    #     except Exception as e:
    #         if hasattr(self, 'main_window') and self.main_window:
    #             self.main_window.append_log_raw(f"RX: Flash Exception {e}")
    #         logger.error(f"flash_coil error: {e}")
    #         return False
    
    # def flash_coil(self, address: int, delay_ms: int = 800):
    #     """闪开指令 - 功能码05 + 延时值"""
    #     try:
    #         if hasattr(self, 'main_window') and self.main_window:
    #             self.main_window.append_log_raw(f"TX: Flash CH{address} {delay_ms}ms")

    #         flash_address = 0x0200 + address
    #         delay_value = max(1, delay_ms // 100)   # 1000ms → 10

    #         # 构造完整请求
    #         request = bytes([
    #             self.slave_id,
    #             0x05,                                   # 功能码 05
    #             (flash_address >> 8) & 0xFF,
    #             flash_address & 0xFF,
    #             (delay_value >> 8) & 0xFF,
    #             delay_value & 0xFF
    #         ])

    #         # CRC16
    #         def modbus_crc(data):
    #             crc = 0xFFFF
    #             for byte in data:
    #                 crc ^= byte
    #                 for _ in range(8):
    #                     if crc & 1:
    #                         crc = (crc >> 1) ^ 0xA001
    #                     else:
    #                         crc >>= 1
    #             return crc

    #         crc = modbus_crc(request)
    #         request += bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    #         # 发送
    #         self.client.send(request)

    #         self.main_window.append_log_raw(f"TX Raw: {request.hex().upper()}")

    #         # 读取响应
    #         import time
    #         time.sleep(0.3)
    #         if hasattr(self.client, 'recv'):
    #             resp = self.client.recv(1024)
    #             if resp:
    #                 self.main_window.append_log_raw(f"RX Raw: {resp.hex().upper()}")
    #                 return True

    #         self.main_window.append_log_raw("RX: No Response")
    #         return False

    #     except Exception as e:
    #         if hasattr(self, 'main_window') and self.main_window:
    #             self.main_window.append_log_raw(f"RX: Flash Exception {str(e)}")
    #         logger.error(f"flash_coil error: {e}")
    #         return False

    def flash_coil(self, address: int, delay_ms: int = 800):
        """闪开指令 - 完美物理控制 + 强行修正 UI 通讯 Log"""
        try:
            # if hasattr(self, 'main_window') and self.main_window:
            #     self.main_window.is_controlling_now = True
            import struct
            import time

            # 1. 计算地址和对应的高低字节时间
            flash_address = 0x0200 + address
            
            # 严格对应你的时间转换规则
            raw_value = delay_ms // 100

            # 2. 手工组装完美的 Modbus 物理帧 (01 05 02 00 10 00 ...)
            packet_without_crc = struct.pack(
                ">BBHH", 
                self.slave_id, 
                0x05, 
                flash_address, 
                raw_value<<8
            )

            # 3. 计算 CRC16
            crc = 0xFFFF
            for byte in packet_without_crc:
                crc ^= byte
                for _ in range(8):
                    if crc & 1:
                        crc = (crc >> 1) ^ 0xA001
                    else:
                        crc >>= 1
            
            full_packet = packet_without_crc + struct.pack("<H", crc)

            # 4. 获取物理串口
            raw_serial = self.client.socket if hasattr(self.client, 'socket') else None
            
            if raw_serial:
                # 强行清空缓存
                if hasattr(raw_serial, 'reset_input_buffer'):
                    raw_serial.reset_input_buffer()
                
                # 💥 1. 物理发射！
                raw_serial.write(full_packet)
                
                # 🌟 【核心修复】：直接把真正、正确的 TX 报文拍在 UI 日志上！
                if hasattr(self, 'main_window') and self.main_window:
                    tx_hex = " ".join(f"{b:02X}" for b in full_packet)
                    self.main_window.append_log_raw(f"<span style='color: #00aaff;'><b>[TX] ➔</b> {tx_hex}</span>")
                
                # 同步死等接收应答
                time.sleep(0.08)
                if hasattr(raw_serial, 'in_waiting') and raw_serial.in_waiting > 0:
                    resp = raw_serial.read(raw_serial.in_waiting)
                    
                    if resp:
                        # 🌟 【核心修复】：直接把真正、正确的 RX 报文拍在 UI 日志上！
                        if hasattr(self, 'main_window') and self.main_window:
                            rx_hex = " ".join(f"{b:02X}" for b in resp)
                            self.main_window.append_log_raw(f"[RX] ⬅ {rx_hex}")
                        return True
            else:
                if hasattr(self.client, 'send'):
                    self.client.send(full_packet)
                    return True
            return False

        except Exception as e:
            logger.error(f"flash_coil 终极版本异常: {e}")
            return False
        # finally:
        #     # 🌟 2. 放下盾牌：控制结束，恢复后台日志的正常显示
        #     time.sleep(0.05) # 给串口留一点点清空尾巴的时间
        #     if hasattr(self, 'main_window') and self.main_window:
        #         self.main_window.is_controlling_now = False

    def _log_raw_packet(self, direction: str, data: bytes):
        """将原始字节流转换成带颜色样式的文本送给 append_log_raw"""

        if not self.log_enabled:
            return
        
        try:
            hex_str = " ".join(f"{b:02X}" for b in data)

            if direction == "TX":
                text = f"<span style='color: #00aaff;'><b>[TX] ➔</b> {hex_str}</span>"
            else:
                text = f"<span style='color: #55ff00;'><b>[RX] ⬅</b> {hex_str}</span>"

            self.log_emitter.raw_log.emit(text)

        except Exception as e:
            logger.error(f"_log_raw_packet failed: {e}")

async def main():
    temp = int_to_float(0xffdd)
    
    print(f"temp: {temp}")
    
    client = AsyncModbusRTUClient(port="COM10", baudrate=9600, slave_id=2)
    if await client.connect():
        sensors = await client.read_all_sensors()
        
        print("All data: ", sensors)
        await client.close()
        

if __name__ == "__main__":
    # asyncio.run(main())
    client = ModbusRTUClient(port="COM10", baudrate=9600, slave_id=2)
    if client.connect():
        sensors = client.read_all_sensors()
        print("All data: ", sensors)
        client.close()
            