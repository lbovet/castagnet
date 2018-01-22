#!/ffp/bin/sh

# PROVIDE: castagnet
# REQUIRE: LOGIN

. /ffp/etc/ffp.subr

name="castagnet"
command="/ffp/home/root/castagnet"
start_cmd=castagnet_start

castagnet_start()
{
	proc_start_bg $command
}

run_rc_command "$1"
