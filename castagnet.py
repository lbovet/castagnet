import datetime
import logging
import os
import re
import threading
import time
import urllib.parse
import uuid

import pychromecast
import requests
import waitress
import wakeonlan
from flask import Flask, Response, jsonify, request
from flask.json.provider import DefaultJSONProvider

app = Flask(__name__)

if app.debug:
    logging.getLogger("werkzeug").setLevel(logging.INFO)

# Chromecast discovery. The default is the friendly name configured on the
# device; set CASTAGNET_CHROMECAST to another name or to an IP address to
# override it.
CHROMECAST = os.environ.get("CASTAGNET_CHROMECAST", "Beamer").strip()
DISCOVERY_TIMEOUT = float(os.environ.get("CASTAGNET_DISCOVERY_TIMEOUT", "8"))
DISCOVERY_BACKOFF = float(os.environ.get("CASTAGNET_DISCOVERY_BACKOFF", "10"))
IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

stats = dict()
window = datetime.timedelta(minutes=5)
retain = datetime.timedelta(days=2)
volume = 1.0

# The Chromecast connection is established lazily, so the service starts even
# when the Chromecast is off and can reconnect when it comes back.
cast = None
cast_browser = None
cast_lock = threading.RLock()
last_discovery_attempt = 0.0
last_discovery_error = None


def discover():
    """Discover the configured Chromecast and return it with its browser."""
    if IPV4_RE.match(CHROMECAST):
        return (
            pychromecast.get_chromecast_from_host(
                (CHROMECAST, 8009, uuid.uuid4(), None, None)
            ),
            None,
        )
    casts, browser = pychromecast.get_listed_chromecasts(
        friendly_names=[CHROMECAST],
        discovery_timeout=DISCOVERY_TIMEOUT,
    )
    if not casts:
        browser.stop_discovery()
        raise RuntimeError("Chromecast %r not found" % CHROMECAST)
    return casts[0], browser


def get_cast():
    """Return a connected Chromecast, discovering it if necessary."""
    global cast, cast_browser, last_discovery_attempt, last_discovery_error
    with cast_lock:
        if cast is not None:
            return cast
        now = time.monotonic()
        if (
            last_discovery_error is not None
            and now - last_discovery_attempt < DISCOVERY_BACKOFF
        ):
            raise last_discovery_error
        last_discovery_attempt = now
        try:
            found, browser = discover()
            try:
                found.wait(timeout=10)
            except Exception:
                if browser is not None:
                    try:
                        browser.stop_discovery()
                    except Exception:
                        pass
                try:
                    found.disconnect(timeout=0)
                except Exception:
                    pass
                raise
        except Exception as exc:
            last_discovery_error = exc
            raise
        last_discovery_error = None
        cast = found
        cast_browser = browser
        return cast


def reset():
    """Drop the current connection and discover the Chromecast again."""
    global cast, cast_browser, last_discovery_error
    with cast_lock:
        if cast is not None:
            try:
                cast.disconnect(timeout=2)
            except Exception:
                pass
        if cast_browser is not None:
            try:
                cast_browser.stop_discovery()
            except Exception:
                pass
        cast = None
        cast_browser = None
        last_discovery_error = None
    return get_cast()


@app.after_request
def after_request(response):
    if not response.status.startswith("404") and request.path.startswith(
        "/castagnet/control"
    ):
        counts = stats.setdefault(request.path, [])
        count = counts[-1:]
        now = datetime.datetime.now()
        if len(count) == 0 or count[0][0] < now - window:
            counts.append([now, 1])
        else:
            count[0][1] += 1
        limit = now - retain
        for _, bucket in stats.items():
            while len(bucket) > 0 and bucket[0][0] < limit:
                bucket.pop(0)
    return response


@app.route("/castagnet/stats")
def statistics():
    if request_wants_html():
        return '''
        <head>
            <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        </head>
        <body>
        <div id="stats"></div>
        <script>
            var xmlhttp = new XMLHttpRequest();
            xmlhttp.onreadystatechange = function() {
                if (this.readyState == 4 && this.status == 200) {
                    stats = JSON.parse(this.responseText);
                    data = [];
                    for(var key in stats) {
                        var trace = {
                            x: [],
                            y: [],
                            type: 'scatter',
                            mode: 'markers',
                            marker: { size: 12 },
                            name: key.split("/").pop()
                        };
                        stats[key].forEach( (count)=> {
                            trace.x.push(count[0]);
                            trace.y.push(count[1]);
                        });
                        data.push(trace);
                    }
                    Plotly.newPlot('stats', data,  {
                        title: 'Requests',
                        xaxis: {
                            autorange: true,
                            type: 'date'
                        },
                        yaxis: {
                            type: 'log'
                        }
                    });
                }
            };
            xmlhttp.open("GET", "/castagnet/stats", true);
            xmlhttp.send();
        </script>
        </body>
        '''
    else:
        return jsonify(stats)


@app.route("/castagnet/control/stop", methods=['POST'])
def control():
    get_cast().media_controller.stop()
    return "Ok"


@app.route("/castagnet/control/pause", methods=['POST'])
def pause():
    get_cast().media_controller.pause()
    return "Ok"


@app.route("/castagnet/control/play", methods=['POST'])
def play():
    get_cast().media_controller.play()
    return "Ok"


@app.route("/castagnet/control/back", methods=['POST'])
def back():
    return seek(-30)


@app.route("/castagnet/control/forward", methods=['POST'])
def forward():
    return seek(+30)


def seek(offset):
    event = threading.Event()
    try:
        chromecast = get_cast()
        chromecast.media_controller.update_status(
            callback_function=lambda *_: event.set()
        )
        event.wait(1)
        media_status = chromecast.media_controller.status
        if media_status is None:
            raise RuntimeError("no media status")
        position = (media_status.current_time or 0) + offset
        duration = media_status.duration
        if duration:
            position = min(duration - 5, position)
        position = max(0, position)
        chromecast.media_controller.seek(position)
        return "Ok"
    except Exception as e:
        return jsonify(player_status="UNAVAILABLE", reason=str(e))


@app.route("/castagnet/control/0", methods=['POST'])
def channel0():
    wakeonlan.send_magic_packet("00:23:54:23:3C:C2")
    return "Ok"


@app.route("/castagnet/control/1", methods=['POST'])
def channel1():
    return listen("http://stream.srg-ssr.ch/m/la-1ere/mp3_128", "La 1ere")


@app.route("/castagnet/control/2", methods=['POST'])
def channel2():
    return listen("http://grrif.ice.infomaniak.ch/grrif-64.aac", "GRRIF")


@app.route("/castagnet/control/3", methods=['POST'])
def channel3():
    return listen("http://stream.srg-ssr.ch/m/couleur3/mp3_128", "Couleur 3")


@app.route("/castagnet/control/4", methods=['POST'])
def channel4():
    return listen("http://167.114.64.181:8352/stream", "HD Radio - Classic Rock")


@app.route("/castagnet/control/5", methods=['POST'])
def channel5():
    return listen("http://ice2.somafm.com/beatblender-64-aac", "Beat Blender")


@app.route("/castagnet/control/6", methods=['POST'])
def channel6():
    return listen("http://178.33.251.97:8080/stream", "Art & Fashion")


@app.route("/castagnet/control/7", methods=['POST'])
def channel7():
    return listen("http://lynx.prostreaming.net:8109/rockvaultradiouhd", "Rock Vault Radio")


@app.route("/castagnet/control/8", methods=['POST'])
def channel8():
    return listen(
        "http://hd.lagrosseradio.info:8000/lagrosseradio-metal-192.mp3",
        "La Grosse Radio",
    )


@app.route("/castagnet/control/9", methods=['POST'])
def channel9():
    return listen("http://stream.srg-ssr.ch/m/rsc_fr/aacp_96", "Swiss Classic")


@app.route("/castagnet/control/ent", methods=['POST'])
def special():
    return listen("http://192.168.1.52:8088/castagnet/recorded/1", "Recorded")


@app.route("/castagnet/control/up", methods=['POST'])
def up():
    chromecast = get_cast()
    level = min(1, chromecast.status.volume_level + 0.05)
    chromecast.set_volume(level)
    return jsonify(volume_level=level)


@app.route("/castagnet/control/down", methods=['POST'])
def down():
    chromecast = get_cast()
    level = max(0, chromecast.status.volume_level - 0.05)
    chromecast.set_volume(level)
    return jsonify(volume_level=level)


def listen(url, title, tries=3):
    global volume
    try:
        chromecast = get_cast()
        chromecast.media_controller.play_media(url, "audio/mpeg", title=title)
        time.sleep(1)
        event = threading.Event()
        chromecast.media_controller.update_status(
            callback_function=lambda *_: event.set()
        )
        event.wait(10)
        if volume < 1.0:
            chromecast.set_volume(volume)
        chromecast.media_controller.play()
        if volume < 1.0:
            chromecast.set_volume(volume)
    except Exception:
        app.logger.exception("Failed to play %s", title)
        if tries > 0:
            try:
                reset()
            except Exception:
                pass
            return listen(url, title, tries - 1)
    return "Playing " + title


@app.route("/castagnet/recorded/<int:id>")
def recorded(id):
    def generate():
        f = open("/tmp/castagnet/" + str(id) + ".mp3", "rb")
        idle = 0
        while idle < 5:  # Timeout
            where = f.tell()
            buffer = f.read(16384)
            if len(buffer) > 0:
                idle = 0
                yield buffer
            else:
                idle += 1
                time.sleep(1)
                f.seek(where)

    return Response(generate(), mimetype='audio/mpeg')


stream_metadata = {}
cache_timestamp = 0
errors = 0


@app.route("/castagnet/media/play", methods=['GET', 'POST'])
def playMedia():
    url = request.args.get('url')
    if not url:
        return jsonify(player_status="UNAVAILABLE", reason="missing url"), 400
    title = urllib.parse.unquote(url).split('/')[-1]
    title = title.replace(".avi", "").replace(".mkv", "").replace(".", " ")
    mime = request.args.get('mime') or "video/mp4"
    get_cast().media_controller.play_media(url, mime, title=title)
    return "Playing " + title


@app.route("/castagnet/media/status")
def status():
    global stream_metadata
    global cache_timestamp
    global errors
    global volume
    event = threading.Event()
    try:
        chromecast = get_cast()
        if chromecast.status is None:
            raise RuntimeError("no cast status")
        chromecast.media_controller.update_status(
            callback_function=lambda *_: event.set()
        )
        media_status = chromecast.media_controller.status
        if media_status and media_status.content_id:
            now = time.time()
            if now > cache_timestamp + 4:
                cache_timestamp = now
                stream_metadata = icy_title(media_status.content_id)
        event.wait(1)
        media_status = chromecast.media_controller.status
        if media_status is None:
            raise RuntimeError("no media status")
        result = media_status.__dict__.copy()
        result.pop('supported_media_commands', None)
        result['supports_pause'] = media_status.supports_pause
        result['supports_seek'] = media_status.supports_seek
        result['supports_stream_volume'] = media_status.supports_stream_volume
        result['supports_stream_mute'] = media_status.supports_stream_mute
        result['supports_skip_forward'] = media_status.supports_skip_forward
        result['supports_skip_backward'] = media_status.supports_skip_backward
        result['volume_level'] = chromecast.status.volume_level
        result['volume_muted'] = chromecast.status.volume_muted
        metadata = dict(stream_metadata)
        metadata.update(media_status.media_metadata or {})
        original_name = metadata.get('title')
        if 'title' in stream_metadata:
            metadata['title'] = stream_metadata['title']
        else:
            metadata.pop('title', None)
        if 'name' not in metadata and original_name is not None:
            metadata['name'] = original_name
        if (
            'title' not in metadata
            and metadata.get('name') is not None
            and chromecast.status.display_name != "Default Media Receiver"
        ):
            metadata['title'] = metadata.get('name')
            metadata['name'] = chromecast.status.display_name
        name = metadata.get('name') or ""
        if name.startswith("/RTS") and len(name) > 4:
            if name[4] == "1":
                metadata['name'] = "La Première"
            if name[4] == "3":
                metadata['name'] = "Couleur 3"
        result['media_metadata'] = metadata
        result['app'] = chromecast.status.display_name
        errors = 0
        if chromecast.status.volume_level < 1.0:
            volume = chromecast.status.volume_level
        return jsonify(result)
    except Exception as e:
        errors += 1
        if errors > 50:
            errors = 0
            try:
                reset()
            except Exception:
                pass
        return jsonify(player_status="UNAVAILABLE", reason=str(e))


def icy_title(stream_url):
    result = dict()
    if stream_url.startswith("http://10.") or stream_url.startswith("http://192.168"):
        return result
    try:
        r = requests.get(
            stream_url, headers={'Icy-MetaData': '1'}, stream=True, timeout=1.0
        )
        try:
            if "icy-name" in r.headers:
                result["name"] = r.headers['icy-name']
            if "icy-metaint" in r.headers:
                r.raw.read(int(r.headers['icy-metaint']))
                meta = r.raw.read(255).rstrip(b'\0')
                m = re.search(br"StreamTitle='(.*?)( - (.*?))?';", bytes(meta))
                if m:
                    result["artist"] = m.group(1).decode("latin1", errors='replace')
                    subtitle = (
                        m.group(3).decode("latin1", errors='replace')
                        if m.group(3)
                        else None
                    )
                    if subtitle.strip() != result["artist"].strip():
                        result["title"] = subtitle
        finally:
            r.close()
    except Exception:
        pass
    return result


def request_wants_html():
    best = request.accept_mimetypes \
        .best_match(['text/html', 'application/json', ])
    return best == 'text/html' and \
        request.accept_mimetypes[best] > \
        request.accept_mimetypes['application/json']


class CustomJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        try:
            return list(iter(obj))
        except TypeError:
            return super().default(obj)


app.json = CustomJSONProvider(app)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.logger.info("Castagnet is there.")
    waitress.serve(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8088")),
        threads=8,
    )