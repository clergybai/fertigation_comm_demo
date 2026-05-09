from typing import Any, Optional, TypeVar, Callable

import asyncio
from pymodbus.client import AsyncModbusSerialClient, ModbusSerialClient
from pymodbus.exceptions import ModbusException
import logging

logging.basicConfig(level=logging.INFO)
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
    def __init__(self, port:str, baudrate: int, bytesize: int = 8, parity: str="N", stopbits: int=1, slave_id: int = 1, timeout: float = 1.0):
        self.slave_id = slave_id
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
                 timeout: float = 1.0):
        
        self.slave_id = slave_id
        self.port = port
        self.connected = False
        
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

    def connect(self) -> bool:
        """连接设备"""
        try:
            if not self.client.connect():
                logger.error("Failed to connect to Modbus device")
                self.connected = False
            else:
                self.connected = True
                logger.info(f"Modbus RTU connected successfully on {self.port}")
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

    def read_all_sensors(self) -> dict:
        """读取所有传感器数据（同步版本）"""
        try:
            comm_vals = self.read_data(0x0080, 5, bcd_to_decimal)
            if comm_vals is None:
                comm_vals = [None] * 5

            regs = self.read_data(0x0000, 8, int_to_float)
            analog_limit = self.read_data(0x00BF, 4, int_to_float)

            return {
                "slave_id": comm_vals[0],
                "baudrate": comm_vals[1],
                "parity": comm_vals[2],
                "data_bit": comm_vals[3],
                "stop_bit": comm_vals[4],
                "sensors": regs,
                "sensor_limits": analog_limit
            }
        except Exception as e:
            logger.error(f"read_all_sensors error: {e}")
            return {}        


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
            