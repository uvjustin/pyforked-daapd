"""This library wraps the forked-daapd API for use with Home Assistant."""
__version__ = "0.1.3"
import asyncio
import logging
import aiohttp

_LOGGER = logging.getLogger(__name__)


class ForkedDaapdAPI:
    """Class for interfacing with forked-daapd API."""

    def __init__(self, websession, ip_address, api_port):
        self._ip_address = ip_address
        self._api_port = api_port
        self._websession = websession

    async def get_request(self, endpoint) -> dict:
        """Helper function to get endpoint."""
        url = f"http://{self._ip_address}:{self._api_port}/api/{endpoint}"
        try:
            async with self._websession.get(url=url) as resp:
                json = await (resp.json())
        except (asyncio.TimeoutError, aiohttp.ClientError):
            _LOGGER.error("Can not get %s", url)
            return False
        return json

    async def put_request(self, endpoint, params=None, json=None) -> int:
        """Helper function to put to endpoint."""
        url = f"http://{self._ip_address}:{self._api_port}/api/{endpoint}"
        _LOGGER.debug("PUT request to %s with params %s, json payload %s.", url, params, json)
        response = await self._websession.put(url=url, params=params, json=json)
        return response.status

    async def start_websocket_handler(
        self, ws_port, event_types, update_callback, websocket_reconnect_time,
    ) -> None:
        """Websocket handler daemon."""
        _LOGGER.debug("Starting websocket handler")
        if ws_port == 0:
            _LOGGER.error(
                "This library requires a forked-daapd instance with websocket enabled."
            )
            raise
        url = f"http://{self._ip_address}:{ws_port}/"
        try:
            while True:
                async with self._websession.ws_connect(
                    url, protocols=("notify",)
                ) as ws:
                    await ws.send_json(data={"notify": event_types})
                    _LOGGER.debug("Sent notify to %s", url)
                    async for msg in ws:
                        updates = msg.json()["notify"]
                        _LOGGER.debug("Message received: %s", msg.json())
                        await update_callback(updates)
                _LOGGER.debug(
                    "WebSocket disconnected, will retry in %s seconds.",
                    websocket_reconnect_time,
                )
                await asyncio.sleep(websocket_reconnect_time)
        except (asyncio.TimeoutError, aiohttp.ClientError):
            _LOGGER.error(
                "Can not connect to WebSocket at %s, will retry in %s seconds.",
                url,
                websocket_reconnect_time,
            )
            await asyncio.sleep(websocket_reconnect_time)
            await self.start_websocket_handler(
                ws_port, event_types, update_callback, websocket_reconnect_time
            )

    async def start_playback(self) -> int:
        """Start playback."""
        status = await self.put_request(endpoint=f"player/play")
        if status != 204:
            _LOGGER.debug("Unable to start playback.")
        return status

    async def pause_playback(self) -> int:
        """Pause playback."""
        status = await self.put_request(endpoint=f"player/pause")
        if status != 204:
            _LOGGER.debug("Unable to pause playback.")
        return status

    async def stop_playback(self) -> int:
        """Stop playback."""
        status = await self.put_request(endpoint=f"player/stop")
        if status != 204:
            _LOGGER.debug("Unable to stop playback.")
        return status

    async def previous_track(self) -> int:
        """Previous track."""
        status = await self.put_request(endpoint=f"player/previous")
        if status != 204:
            _LOGGER.debug("Unable to skip to previous track.")
        return status

    async def next_track(self) -> int:
        """Next track."""
        status = await self.put_request(endpoint=f"player/next")
        if status != 204:
            _LOGGER.debug("Unable to skip to next track.")
        return status

    async def seek(self, **kwargs) -> int:
        """Seek."""
        if "position_ms" in kwargs:
            params = {"position_ms": kwargs["position_ms"]}
        elif "seek_ms" in kwargs:
            params = {"seek_ms": kwargs["seek_ms"]}
        else:
            _LOGGER.error("seek needs either position_ms or seek_ms")
            return -1
        status = await self.put_request(endpoint=f"player/seek", params=params)
        if status != 204:
            _LOGGER.debug(
                "Unable to seek to %s of %s.", params.keys()[0], params.values()[0]
            )
        return status

    async def clear_playlist(self) -> int:
        """Clear playlist."""
        status = await self.put_request(endpoint=f"queue/clear")
        if status != 204:
            _LOGGER.debug("Unable to clear playlist.")
        return status

    async def shuffle(self, shuffle) -> int:
        """Shuffle."""
        status = await self.put_request(
            endpoint=f"player/shuffle", params={"state": shuffle}
        )
        if status != 204:
            _LOGGER.debug("Unable to set shuffle to %s.", shuffle)
        return status

    async def set_enabled_outputs(self, output_ids) -> int:
        """Set enabled outputs."""
        status = await self.put_request(
            endpoint=f"outputs/set", json={"outputs": output_ids}
        )
        if status != 204:
            _LOGGER.debug("Unable to set enabled outputs for %s.", output_ids)
        return status

    async def set_volume(self, **kwargs) -> int:
        """Set volume."""
        if "volume" in kwargs:
            params = {"volume": kwargs["volume"]}
        elif "step" in kwargs:
            params = {"step": kwargs["step"]}
        else:
            _LOGGER.error("set_volume needs either volume or step")
            return
        if "output_id" in kwargs:
            params = {**params, **{"output_id": kwargs["output_id"]}}
        status = await self.put_request(endpoint=f"player/volume", params=params)
        if status != 204:
            _LOGGER.debug("Unable to set volume.")
        return status

    async def get_track_info(self, track_id) -> dict:
        """Get track info."""
        return await self.get_request(endpoint=f"library/tracks/{track_id}")

    async def change_output(self, output_id, selected=None, volume=None) -> int:
        """Change output."""
        json = {} if selected is None else {"selected": selected}
        json = json if volume is None else {**json, **{"volume": volume}}
        status = await self.put_request(endpoint=f"outputs/{output_id}", json=json)
        if status != 204:
            _LOGGER.debug(
                "%s: Unable to change output %s to %s.", status, output_id, json
            )
        return status

    # not used by HA
    async def toggle_playback(self) -> int:
        """Toggle playback."""
        status = await self.put_request(endpoint="player/toggle")
        if status != 204:
            _LOGGER.debug("Unable to toggle playback.")
        return status


class ForkedDaapdData:
    """Represent a forked-daapd server."""

    def __init__(self):
        """Initialize the ForkedDaapd class."""
        self._player_status = None
        self._server_config = None
        self._outputs = None
        self._queue = None
        self._last_outputs = None
        self._last_updated = None
        self._track_info = None

    @property
    def name(self):
        return "forked-daapd"

    @property
    def player_status(self):
        return self._player_status

    @player_status.setter
    def player_status(self, value):
        self._player_status = value

    @property
    def server_config(self):
        return self._server_config

    @server_config.setter
    def server_config(self, value):
        self._server_config = value

    @property
    def outputs(self):
        return self._outputs

    @outputs.setter
    def outputs(self, value):
        self._outputs = value

    @property
    def queue(self):
        return self._queue

    @queue.setter
    def queue(self, value):
        self._queue = value

    @property
    def last_outputs(self):
        return self._last_outputs

    @last_outputs.setter
    def last_outputs(self, value):
        self._last_outputs = value

    @property
    def track_info(self):
        return self._track_info

    @track_info.setter
    def track_info(self, value):
        self._track_info = value
