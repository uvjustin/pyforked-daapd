"""This library wraps the forked-daapd API for use with Home Assistant."""
__version__ = "0.1.3"
import asyncio
import logging
import aiohttp

_LOGGER = logging.getLogger(__name__)


class ForkedDaapdAPI:
    """Class for interfacing with forked-daapd API."""

    def __init__(self, websession, ip_address, api_port, api_password):
        self._ip_address = ip_address
        self._api_port = api_port
        self._websession = websession
        self._auth = (
            aiohttp.BasicAuth(login="admin", password=api_password)
            if api_password
            else None
        )

    async def get_request(self, endpoint) -> dict:
        """Helper function to get endpoint."""
        url = f"http://{self._ip_address}:{self._api_port}/api/{endpoint}"
        try:
            async with self._websession.get(url=url, auth=self._auth) as resp:
                json = await (resp.json())
        except (asyncio.TimeoutError, aiohttp.ClientError):
            _LOGGER.error("Can not get %s", url)
            return None
        return json

    async def put_request(self, endpoint, params=None, json=None) -> int:
        """Helper function to put to endpoint."""
        url = f"http://{self._ip_address}:{self._api_port}/api/{endpoint}"
        _LOGGER.debug(
            "PUT request to %s with params %s, json payload %s.", url, params, json
        )
        response = await self._websession.put(
            url=url, params=params, json=json, auth=self._auth
        )
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
            raise Exception("forked-daapd websocket not enabled.")
        url = f"http://{self._ip_address}:{ws_port}/"
        while True:
            try:
                async with self._websession.ws_connect(
                    url, protocols=("notify",), heartbeat=websocket_reconnect_time
                ) as websocket:
                    await update_callback(
                        event_types
                    )  # send all requested updates once
                    await websocket.send_json(data={"notify": event_types})
                    _LOGGER.debug("Sent notify to %s", url)
                    async for msg in websocket:
                        updates = msg.json()["notify"]
                        _LOGGER.debug("Message JSON: %s", msg.json())
                        await update_callback(updates)
                        _LOGGER.debug("Done with callbacks %s", updates)
            except (asyncio.TimeoutError, aiohttp.ClientError) as exception:
                _LOGGER.error(
                    "Can not connect to WebSocket at %s, will retry in %s seconds.",
                    url,
                    websocket_reconnect_time,
                )
                _LOGGER.error("Error %s", repr(exception))
                await asyncio.sleep(websocket_reconnect_time)
                continue

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
            params = {"position_ms": int(kwargs["position_ms"])}
        elif "seek_ms" in kwargs:
            params = {"seek_ms": int(kwargs["seek_ms"])}
        else:
            _LOGGER.error("seek needs either position_ms or seek_ms")
            return -1
        status = await self.put_request(endpoint=f"player/seek", params=params)
        if status != 204:
            _LOGGER.debug(
                "Unable to seek to %s of %s.",
                next(iter(params.keys())),
                next(iter(params.values())),
            )
        return status

    async def shuffle(self, shuffle) -> int:
        """Shuffle."""
        status = await self.put_request(
            endpoint=f"player/shuffle",
            params={"state": str(shuffle)},  # aiohttp bool params treated differently
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
            params = {"volume": int(kwargs["volume"])}
        elif "step" in kwargs:
            params = {"step": int(kwargs["step"])}
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
        json = json if volume is None else {**json, **{"volume": int(volume)}}
        status = await self.put_request(endpoint=f"outputs/{output_id}", json=json)
        if status != 204:
            _LOGGER.debug(
                "%s: Unable to change output %s to %s.", status, output_id, json
            )
        return status

    async def post_request(self, endpoint, params=None, json=None) -> int:
        """Helper function to put to endpoint."""
        url = f"http://{self._ip_address}:{self._api_port}/api/{endpoint}"
        _LOGGER.debug(
            "POST request to %s with params %s, data payload %s.", url, params, json
        )
        response = await self._websession.post(
            url=url, params=params, json=json, auth=self._auth
        )
        return response.status

    async def add_to_queue(self, uris=None, expression=None, **kwargs) -> int:
        """Add item to queue."""
        if not (uris or expression):
            _LOGGER.error("Either uris or expression must be set.")
            return
        if uris:
            params = {"uris": uris}
        else:
            params = {"expression": expression}
        for field in [
            "playback",
            "playback_from_position",
            "clear",
            "shuffle",
        ]:  # clear doesn't seem to work
            if field in kwargs:
                params[field] = (
                    kwargs[field]
                    if isinstance(kwargs[field], bool)
                    else str(kwargs[field])
                )  # aiohttp bool params treated differently
        if "position" in kwargs:
            params["position"] = int(kwargs["position"])
        status = await self.post_request(endpoint=f"queue/items/add", params=params)
        if status != 200:
            _LOGGER.debug("%s: Unable to add items to queue.", status)
        return status

    async def get_player_status(self) -> dict:
        """Get player status."""
        return await self.get_request(endpoint=f"player")

    async def get_queue(self) -> dict:
        """Get queue."""
        return await self.get_request(endpoint=f"queue")

    async def clear_queue(self) -> int:
        """Clear queue."""
        status = await self.put_request(endpoint=f"queue/clear")
        if status != 204:
            _LOGGER.debug("%s: Unable to clear queue.", status)
        return status

    # not used by HA

    async def consume(self, consume) -> int:
        """Consume."""
        status = await self.put_request(
            endpoint=f"player/consume",
            params={"state": str(consume)},  # aiohttp bool params treated differently
        )
        if status != 204:
            _LOGGER.debug("Unable to set consume to %s.", consume)
        return status

    async def repeat(self, repeat) -> int:
        """Repeat. Takes string argument of 'off','all', or 'single'."""
        status = await self.put_request(
            endpoint=f"player/repeat", params={"state": repeat}
        )
        if status != 204:
            _LOGGER.debug("Unable to set repeat to %s.", repeat)
        return status

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
        self._outputs = []
        self._queue = None
        self._last_outputs = None
        self._last_updated = None
        self._track_info = None

    @property
    def name(self):
        """Name."""
        return "forked-daapd"

    @property
    def player_status(self):
        """Player status getter."""
        return self._player_status

    @player_status.setter
    def player_status(self, value):
        """Player status setter."""
        self._player_status = value

    @property
    def server_config(self):
        """Server config getter."""
        return self._server_config

    @server_config.setter
    def server_config(self, value):
        """Server config setter."""
        self._server_config = value

    @property
    def outputs(self):
        """Outputs getter."""
        return self._outputs

    @outputs.setter
    def outputs(self, value):
        """Outputs setter."""
        self._outputs = value

    @property
    def queue(self):
        """Queue getter."""
        return self._queue

    @queue.setter
    def queue(self, value):
        """Queue setter."""
        self._queue = value

    @property
    def last_outputs(self):
        """Last outputs getter."""
        return self._last_outputs

    @last_outputs.setter
    def last_outputs(self, value):
        """Last outputs setter."""
        self._last_outputs = value

    @property
    def track_info(self):
        """Track info getter."""
        return self._track_info

    @track_info.setter
    def track_info(self, value):
        """Track info setter."""
        self._track_info = value
