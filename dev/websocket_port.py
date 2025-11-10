import asyncio
from dataclasses import dataclass
from realtime_agent import WebSocketPort

@dataclass
class WebsocketTestDataPackage:
    timestamp: float
    event: dict | str

class MyTestWebSocketPort(WebSocketPort):
    def __init__(self):
        self.accepted = False
        self.sent: list[WebsocketTestDataPackage] = []
        self.to_receive = asyncio.Queue()

    async def accept(self):
        pass

    async def send(self, message: dict | str):
        loop = asyncio.get_running_loop()
        self.sent.append(
            WebsocketTestDataPackage(
                timestamp=loop.time(),
                event=message,
            )
        )

    async def receive(self):
        return await self.to_receive.get()

    async def close(self):
        self.closed = True