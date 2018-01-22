# coding=utf-8

from flask import Flask
import pychromecast

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

@app.route("/castagnet/control/1", methods=['POST'])
def channel1():
    return listen("http://stream.srg-ssr.ch/m/la-1ere/mp3_128", "La 1ere")

@app.route("/castagnet/control/3", methods=['POST'])
def channel3():
    return listen("http://stream.srg-ssr.ch/m/couleur3/mp3_128", "Couleur 3")

def listen(url, title):
    cast.media_controller.play_media(url, "audio/mpeg", title)
    return "Playing "+title
