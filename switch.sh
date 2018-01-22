#!/bin/sh
# Change to specified channel only when already playing
wget -qO - http://localhost:8088/castagnet/media/status | grep -q PLAYING && \
wget -qO - --post-data= http://localhost:8088/castagnet/control/$1 12> /dev/null
