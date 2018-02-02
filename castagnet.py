from flask import Flask, Response, request, jsonify
import pychromecast
import threading
import json
from time import sleep

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
                sleep(1)
                f.seek(where)
    return Response(generate(), mimetype='audio/mpeg')

@app.route("/castagnet/media/status")
def status():
    event = threading.Event()
    try:
        cast.media_controller.update_status(lambda x: event.set())
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
        result['app'] = cast.status.display_name
        return jsonify(result)
    except Exception as e:
        return jsonify(player_status="UNAVAILABLE", reason=str(e))
