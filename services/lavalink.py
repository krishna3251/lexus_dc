"""Own Lavalink resources, including nodes rejected before Pool registration."""

import asyncio
import logging

import aiohttp

logger = logging.getLogger(__name__)


class LavalinkConnection:
    def __init__(self, sdk):
        self.sdk = sdk
        self.node = None
        self.session = None
        self.lock = asyncio.Lock()
        self.closed = False

    async def connect(self, client, uri, password):
        async with self.lock:
            if self.closed:
                return
            if self.node is not None and self.node.status != self.sdk.NodeStatus.DISCONNECTED:
                return
            await self._close()
            self.session = aiohttp.ClientSession()
            try:
                self.node = self.sdk.Node(
                    identifier="lexus-primary", uri=uri, password=password,
                    session=self.session, retries=1,
                )
                nodes = await asyncio.wait_for(
                    self.sdk.Pool.connect(nodes=[self.node], client=client, cache_capacity=100),
                    timeout=30,
                )
                if nodes.get(self.node.identifier) is not self.node or self.node.status == self.sdk.NodeStatus.DISCONNECTED:
                    logger.warning("Lavalink unavailable; music remains offline. Check the node's v4 endpoint and credentials.")
                    await self._close()
                    return
                logger.info("Lavalink websocket connected; awaiting node-ready confirmation")
            except asyncio.CancelledError:
                await self._close()
                raise
            except Exception as error:
                # Avoid credentials/URLs embedded in third-party exception messages.
                logger.warning("Lavalink connection failed (%s); music remains offline", type(error).__name__)
                await self._close()

    async def close(self):
        async with self.lock:
            self.closed = True
            await self._close()

    async def _close(self):
        node, session = self.node, self.session
        self.node = self.session = None
        try:
            if node is not None:
                await node.close(eject=True)
        finally:
            if session is not None and not session.closed:
                await session.close()
