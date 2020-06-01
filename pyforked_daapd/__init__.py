"""This library wraps the forked-daapd API for use with Home Assistant."""
__version__ = "0.1.10"
import asyncio
import concurrent
import logging
from urllib.parse import urljoin

import aiohttp

_LOGGER = logging.getLogger(__name__)


class ForkedDaapdAPI:
    """Class for interfacing with forked-daapd API."""

    def __init__(self, websession, ip_address, api_port, api_password):
        """Initialize the ForkedDaapdAPI object."""
        self._ip_address = ip_address
        self._api_port = api_port
        self._websession = websession
        self._auth = (
            aiohttp.BasicAuth(login="admin", password=api_password)
            if api_password
            else None
        )
        self._api_password = api_password

    @staticmethod
    async def test_connection(websession, host, port, password):
        """Validate the user input."""

        try:
            url = f"http://{host}:{port}/api/config"
            auth = (
                aiohttp.BasicAuth(login="admin", password=password)
                if password
                else None
            )
            # _LOGGER.debug("Trying to connect to %s with auth %s", url, auth)
            async with websession.get(
                url=url, auth=auth, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                json = await resp.json()
                # _LOGGER.debug("JSON %s", json)
                if json["websocket_port"] == 0:
                    return ["websocket_not_enabled"]
                return ["ok", json["library_name"]]
        except (
            aiohttp.ClientConnectionError,
            asyncio.TimeoutError,
            # pylint: disable=protected-access
            concurrent.futures._base.TimeoutError,
            # maybe related to https://github.com/aio-libs/aiohttp/issues/1207
            aiohttp.InvalidURL,
        ):
            return ["wrong_host_or_port"]
        except (aiohttp.ClientResponseError, KeyError):
            if resp.status == 401:
                return ["wrong_password"]
            return ["wrong_server_type"]
        finally:
            pass
        return ["unknown_error"]

    async def get_request(self, endpoint) -> dict:
        """Get request from endpoint."""
        url = f"http://{self._ip_address}:{self._api_port}/api/{endpoint}"
        try:
            async with self._websession.get(url=url, auth=self._auth) as resp:
                json = await resp.json()
        except (asyncio.TimeoutError, aiohttp.ClientError):
            _LOGGER.error("Can not get %s", url)
            return None
        return json

    async def put_request(self, endpoint, params=None, json=None) -> int:
        """Put request to endpoint."""
        url = f"http://{self._ip_address}:{self._api_port}/api/{endpoint}"
        _LOGGER.debug(
            "PUT request to %s with params %s, json payload %s.", url, params, json
        )
        if params:  # convert bool to text
            params = {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in params.items()
            }
        response = await self._websession.put(
            url=url, params=params, json=json, auth=self._auth
        )
        return response.status

    async def post_request(self, endpoint, params=None, json=None) -> int:
        """Post request to endpoint."""
        url = f"http://{self._ip_address}:{self._api_port}/api/{endpoint}"
        _LOGGER.debug(
            "POST request to %s with params %s, data payload %s.", url, params, json
        )
        if params:  # convert bool to text
            params = {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in params.items()
            }
        response = await self._websession.post(
            url=url, params=params, json=json, auth=self._auth
        )
        return response.status

    async def start_websocket_handler(
        self,
        ws_port,
        event_types,
        update_callback,
        websocket_reconnect_time,
        disconnected_callback=None,
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
                _LOGGER.warning(
                    "Can not connect to WebSocket at %s, will retry in %s seconds.",
                    url,
                    websocket_reconnect_time,
                )
                _LOGGER.warning("Error %s", repr(exception))
                if disconnected_callback:
                    disconnected_callback()
                await asyncio.sleep(websocket_reconnect_time)
                continue

    async def start_playback(self) -> int:
        """Start playback."""
        status = await self.put_request(endpoint="player/play")
        if status != 204:
            _LOGGER.debug("Unable to start playback.")
        return status

    async def pause_playback(self) -> int:
        """Pause playback."""
        status = await self.put_request(endpoint="player/pause")
        if status != 204:
            _LOGGER.debug("Unable to pause playback.")
        return status

    async def stop_playback(self) -> int:
        """Stop playback."""
        status = await self.put_request(endpoint="player/stop")
        if status != 204:
            _LOGGER.debug("Unable to stop playback.")
        return status

    async def previous_track(self) -> int:
        """Previous track."""
        status = await self.put_request(endpoint="player/previous")
        if status != 204:
            _LOGGER.debug("Unable to skip to previous track.")
        return status

    async def next_track(self) -> int:
        """Next track."""
        status = await self.put_request(endpoint="player/next")
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
        status = await self.put_request(endpoint="player/seek", params=params)
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
            endpoint="player/shuffle", params={"state": shuffle},
        )
        if status != 204:
            _LOGGER.debug("Unable to set shuffle to %s.", shuffle)
        return status

    async def set_enabled_outputs(self, output_ids) -> int:
        """Set enabled outputs."""
        status = await self.put_request(
            endpoint="outputs/set", json={"outputs": output_ids}
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
        status = await self.put_request(endpoint="player/volume", params=params)
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
        ]:
            if field in kwargs:
                params[field] = kwargs[field]
        if "position" in kwargs:
            params["position"] = int(kwargs["position"])
        status = await self.post_request(endpoint="queue/items/add", params=params)
        if status != 200:
            _LOGGER.debug("%s: Unable to add items to queue.", status)
        return status

    async def clear_queue(self) -> int:
        """Clear queue."""
        status = await self.put_request(endpoint="queue/clear")
        if status != 204:
            _LOGGER.debug("%s: Unable to clear queue.", status)
        return status

    def full_url(self, url):
        """Get full url (including basic auth) of urls such as artwork_url."""
        creds = f"admin:{self._api_password}@" if self._api_password else ""
        return urljoin(f"http://{creds}{self._ip_address}:{self._api_port}", url)

    async def get_pipes(self) -> []:
        """Get list of pipes."""
        pipes = await self.get_request(
            "search?type=tracks&expression=data_kind+is+pipe"
        )
        if pipes:
            return pipes["tracks"]["items"]
        return None

    async def get_playlists(self) -> []:
        """Get list of playlists."""
        playlists = await self.get_request("library/playlists")
        if playlists:
            return playlists["items"]
        return None

    # not used by HA

    async def consume(self, consume) -> int:
        """Consume."""
        status = await self.put_request(
            endpoint="player/consume", params={"state": consume},
        )
        if status != 204:
            _LOGGER.debug("Unable to set consume to %s.", consume)
        return status

    async def repeat(self, repeat) -> int:
        """Repeat. Takes string argument of 'off','all', or 'single'."""
        status = await self.put_request(
            endpoint="player/repeat", params={"state": repeat}
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
