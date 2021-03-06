# coding: latin-1
from __future__ import unicode_literals
from flask import Flask, Response, request, jsonify
import pychromecast
from pychromecast.error import NotConnected
import threading
import json
import time
import re
import requests
import wakeonlan
import datetime
import urllib
from flask.json import JSONEncoder

app = Flask(__name__)

if app.debug:
    import logging
    logging.getLogger("werkzeug").setLevel(logging.INFO)

ip = "192.168.1.104"
cast = pychromecast.Chromecast(ip)

stats = dict()
window = datetime.timedelta(minutes=5)
retain = datetime.timedelta(days=2)
volume = 1.0

@app.after_request
def after_request(response):
    if not response.status.startswith("404") and request.path.startswith("/castagnet/control"):
        counts = stats.setdefault(request.path, [])
        count = counts[-1:]
        now = datetime.datetime.now()
        if len(count) == 0 or count[0][0] < now - window:
            counts.append([now, 1])
        else:
            count[0][1]+=1
        limit = now - retain
        for _, counts in stats.iteritems():
            while len(counts) > 0 and counts[0][0] < limit:
                counts.pop(0)
                print count[0][0]
                print limit
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
    return listen("http://hd.lagrosseradio.info:8000/lagrosseradio-metal-192.mp3", "La Grosse Radio")

@app.route("/castagnet/control/9", methods=['POST'])
def channel9():
    return listen("http://stream.srg-ssr.ch/m/rsc_fr/aacp_96", "Swiss Classic")

@app.route("/castagnet/control/ent", methods=['POST'])
def special():
    return listen("http://192.168.1.52:8088/castagnet/recorded/1", "Recorded")

@app.route("/castagnet/control/up", methods=['POST'])
def up():
    level = min(1, cast.status.volume_level+0.05)
    cast.set_volume(level)
    return jsonify(volume_level=level)

@app.route("/castagnet/control/down", methods=['POST'])
def down():
    level = max(0, cast.status.volume_level-0.05)
    cast.set_volume(level)
    return jsonify(volume_level=level)

def listen(url, title, tries=3):
    global cast
    global volume
    err = False
    try:
        cast.media_controller.play_media(url, "audio/mpeg", title)
        time.sleep(1)
        event = threading.Event()
        cast.media_controller.update_status(
            lambda x: event.set())
        event.wait(10)
        if volume < 1.0:
            cast.set_volume(volume)
        cast.media_controller.play()
        if volume < 1.0:
            cast.set_volume(volume)
    except Exception:
        err = True
        print("Not Connected")
    if err:
        if tries > 0:
            reset()
            listen(url, title, tries-1)
    return "Playing "+title

def reset():
    global cast
    cast.disconnect(1, True)
    cast = pychromecast.Chromecast(ip)
    time.sleep(1)
    status()

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
errors = 0


@app.route("/castagnet/media/play", methods=['GET', 'POST'])
def playMedia():
    global cast
    url = request.args.get('url')
    title = urllib.unquote(url.encode("utf-8")).decode("utf-8").split('/')[-1]
    title = title.replace(".avi", "").replace(".mkv", "").replace(".", " ")
    mime = request.args.get('mime') or "video/mp4"
    cast.media_controller.play_media(url, mime, title)
    return "Playing "+title

@app.route("/castagnet/media/status")
def status():
    global stream_metadata
    global cache_timestamp
    global errors
    global volume
    event = threading.Event()
    try:
        cast.media_controller.update_status(lambda x: event.set())
        if cast.media_controller.status and cast.media_controller.status.content_id:
            now = time.time()
            if now > cache_timestamp + 4:
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
        if result['media_metadata']['name'].startswith("/RTS"):
            if result['media_metadata']['name'][4] == "1":
                result['media_metadata']['name'] = "La Premi�re"
            if result['media_metadata']['name'][4] == "3":
                result['media_metadata']['name'] = "Couleur 3"

        result['app'] = cast.status.display_name
        errors = 0
        if cast.status.volume_level < 1.0:
            volume = cast.status.volume_level
        return jsonify(result)
    except Exception as e:
        errors += 1
        if errors > 50:
            errors = 0
            reset()
        return jsonify(player_status="UNAVAILABLE", reason=str(e))

def icy_title(stream_url):
    result = dict()
    if stream_url.startswith("http://10.") or stream_url.startswith("http://192.168"):
        return result
    try:
        r = requests.get(stream_url, headers={'Icy-MetaData': '1'}, stream=True, timeout=1.0)
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
    except Exception:
        pass
    return result

def request_wants_html():
    best = request.accept_mimetypes \
        .best_match(['text/html', 'application/json', ])
    return best == 'text/html' and \
        request.accept_mimetypes[best] > \
        request.accept_mimetypes['application/json']


class CustomJSONEncoder(JSONEncoder):
    def default(self, obj):  # pylint: disable=E0202
        try:
            if isinstance(obj, datetime.datetime):
                return obj.isoformat()
            iterable = iter(obj)
        except TypeError:
            pass
        else:
            return list(iterable)
        return JSONEncoder.default(self, obj)

app.json_encoder = CustomJSONEncoder

print "Castagnet is there."
