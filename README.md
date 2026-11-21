# castagnet

Basic REST service receiving remote control commands (mostly from [irpost](https://github.com/lbovet/irpost)) and 
controlling a [ChromeCast](https://en.wikipedia.org/wiki/Chromecast).

<img height="160" src="https://user-images.githubusercontent.com/692124/35284215-81e1d8b6-005a-11e8-9655-e2e369a65f4a.png"/>

This is highly customized for my own needs:

- Tune to my favorite radio channels
- Playback control: pause, play, stop. rewind, fast-forward, next, prev)
- Query media playing status
- Replay recorded streams

## Configuration

The Chromecast is discovered over mDNS. By default castagnet looks for the
friendly name `Beamer`; override it with `CASTAGNET_CHROMECAST` (a friendly name
or an IP address). `PORT` defaults to `8088`.

```bash
CASTAGNET_CHROMECAST=Beamer PORT=8088 python castagnet.py
```

The connection is established lazily, so the service starts even when the
Chromecast is off and reconnects when it comes back.

## Deployment on kitch

Pushes to `master` (and manual `workflow_dispatch` runs) deploy the code to the
kitch Raspberry Pi over SSH. The workflow rsyncs the tree to `/srv/castagnet`,
installs `requirements.txt` into `/srv/castagnet/.venv` and restarts the
`castagnet.service` systemd unit.

Required repository secrets:

| Secret | Used for |
|---|---|
| `KITCH_SSH_KEY` | logs in as `shaman@kitch` through `172.18.0.1:17202` |
| `CLOUDBOX_SSH_KEY` | logs in as `system@cloudbox.chee.li`, the SSH jump host |

The systemd unit, the `/srv/castagnet` directory and its virtualenv are owned by
the [kitch repository](https://github.com/lbovet/kitch). Pull requests only run
the compile/import check; they never touch the Pi.

On the LAN the service is reachable at `http://raspberrypi.local:8088` (or the
Pi's current IP). Point `irpost` and `switch.sh` there instead of the legacy NAS
address. The `ent` channel still points at the NAS for recorded streams; that is
unchanged.

## Local development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python castagnet.py
```

The `ffp/` scripts are specific to the legacy DNS-323 NAS and are not used by
the kitch deployment.
