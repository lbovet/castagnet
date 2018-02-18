from __future__ import unicode_literals
from flask import Flask, Response, request, jsonify
import pychromecast
import threading
import json
import time
import re
import requests

app = Flask(__name__)

cast = pychromecast.Chromecast("10.0.1.22")

@app.route("/castagnet/control/stop", methods=['POST'])
def control():
    cast.media_controller.stop()
    return "Ok"

@app.route("/castagnet/control/pause", methods=['POST'])
def pause():
    cast.media_controller.pause()
    return "Ok"

@app.route("/castagnet/control/play", methods=['POST'])
def play():
    cast.media_controller.play()
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
        cast.media_controller.update_status(lambda x: event.set())
        event.wait(1)
        position = cast.media_controller.status.current_time + offset
        duration = cast.media_controller.status.duration
        if duration:
            position = min(duration -5, position)
        position = max(0, position)
        cast.media_controller.seek(position)
        return "Ok"
    except Exception as e:
        return jsonify(player_status="UNAVAILABLE", reason=str(e))

@app.route("/castagnet/control/1", methods=['POST'])
def channel1():
    return listen("http://stream.srg-ssr.ch/m/la-1ere/mp3_128", "La 1ere")

@app.route("/castagnet/control/3", methods=['POST'])
def channel3():
    return listen("http://stream.srg-ssr.ch/m/couleur3/mp3_128", "Couleur 3")

@app.route("/castagnet/control/ent", methods=['POST'])
def special():
    return listen("http://10.0.1.52:8088/castagnet/recorded/1", "Recorded")

@app.route("/castagnet/control/up", methods=['POST'])
def up():
    level = min(1, cast.status.volume_level+0.1)
    cast.volume_up()
    return jsonify(volume_level=level)

@app.route("/castagnet/control/down", methods=['POST'])
def down():
    level = max(0, cast.status.volume_level-0.1)
    cast.volume_down()
    return jsonify(volume_level=level)

def listen(url, title):
    cast.media_controller.play_media(url, "audio/mpeg", title)
    return "Playing "+title

@app.route("/castagnet/recorded/<int:id>")
def recorded(id):
    def generate():
        f = open("/tmp/castagnet/"+str(id)+".mp3", "rb")
        idle=0
        while idle < 5: # Timeout
            where = f.tell()
            buffer = f.read(16384)
            if len(buffer) > 0:
                idle=0
                yield buffer
            else:
                idle+=1
                time.sleep(1)
                f.seek(where)
    return Response(generate(), mimetype='audio/mpeg')

stream_metadata = {}
cache_timestamp = 0

@app.route("/castagnet/media/status")
def status():
    global stream_metadata
    global cache_timestamp
    event = threading.Event()
    try:
        cast.media_controller.update_status(lambda x: event.set())
        if cast.media_controller.status and cast.media_controller.status.content_id:
            now = time.time()
            if now > cache_timestamp + 4:
                print(now - cache_timestamp)
                cache_timestamp = now
                stream_metadata = icy_title(cast.media_controller.status.content_id)
        event.wait(1)
        status = cast.media_controller.status
        result = status.__dict__.copy()
        result.pop('supported_media_commands')
        result['supports_pause'] = status.supports_pause
        result['supports_seek'] = status.supports_seek
        result['supports_stream_volume'] = status.supports_stream_volume
        result['supports_stream_mute'] = status.supports_stream_mute
        result['supports_skip_forward'] = status.supports_skip_forward
        result['supports_skip_backward'] = status.supports_skip_backward
        result['volume_level'] = cast.status.volume_level
        result['volume_muted'] = cast.status.volume_muted
        result['media_metadata'] = dict(stream_metadata.items() + result['media_metadata'].items())
        originalName = result['media_metadata']['title']
        if 'title' in stream_metadata :
            result['media_metadata']['title'] = stream_metadata['title']
        else:
            del result['media_metadata']['title']
        if 'name' not in result['media_metadata']:
            result['media_metadata']['name'] = originalName
        if 'title' not in result['media_metadata'] and not cast.status.display_name == "Default Media Receiver":
            result['media_metadata']['title'] = result['media_metadata']['name']
            result['media_metadata']['name'] = cast.status.display_name
        result['app'] = cast.status.display_name
        return jsonify(result)
    except Exception as e:
        return jsonify(player_status="UNAVAILABLE", reason=str(e))

def icy_title(stream_url):
    result = dict()
    if stream_url.startswith("http://10.") or stream_url.startswith("http://192.168"):
        return result
    try:
        r = requests.get(stream_url, headers={'Icy-MetaData': '1'}, stream=True, timeout=12.0)
        if "icy-name" in r.headers:
            result["name"] = r.headers['icy-name']
        if "icy-metaint" in r.headers:
            r.raw.read(int(r.headers['icy-metaint']))
            meta = r.raw.read(255).rstrip(b'\0')
            m = re.search(br"StreamTitle='(.*?)( - (.*?))?';", bytes(meta))
            if m:
                result["artist"] = m.group(1).decode("latin1", errors='replace')
                subtitle = m.group(3).decode("latin1", errors='replace') if m.group(3) else None
                if subtitle.strip() != result["artist"].strip():
                    result["title"] = subtitle
    except Exception as e:
        pass
    return result

print "Castagnet is there."
