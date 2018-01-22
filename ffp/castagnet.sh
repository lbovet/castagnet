#!/ffp/bin/sh

# PROVIDE: castagnet
# REQUIRE: LOGIN

# Start script to run castagnet in Fonz Fun-Plug (http://dns323.kood.org/howto:ffp)

. /ffp/etc/ffp.subr

name="castagnet"
export FLASK_APP="/ffp/home/root/castagnet.py"
command="/ffp/bin/flask"
start_cmd=castagnet_start
flask_flags="run --host=0.0.0.0 --port=8088"

castagnet_start()
{
	proc_start_bg $command
}

run_rc_command "$1"
