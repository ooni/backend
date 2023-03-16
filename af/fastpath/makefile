
local_quickdeploy:
	sudo cp fastpath/*.py /usr/lib/python3.7/dist-packages/fastpath/
	sudo systemctl restart fastpath

local_functests:
	PYTHONPATH=. pytest-3 -s --log-cli-level info $(args)

local_functests_coverage:
	PYTHONPATH=. pytest-3 -s --cov=fastpath

local_functests_profile:
	austin -o austin.log pytest-3 -s  --log-cli-level info fastpath/tests/test_functional.py::test_windowing_on_real_data
	/usr/share/perl5/Devel/NYTProf/flamegraph.pl austin.log > profile.svg

local_run_devel:
	nice python3 -c'from fastpath.fastpath import main; main()' --devel \
		--start-day=2019-7-20 --end-day=2019-7-21 $(args)

local_monitor_metrics:
	sudo tcpdump -npqi lo udp port 8125 -A -lU | grep --line-buffered fastpat | sed 's/.*fastpath\.//'

builddeb:
	dpkg-buildpackage -us -uc -b

ver := $(shell dpkg-parsechangelog --show-field Version)

beta_deploydeb:
	echo deploying $(ver)
	rsync -avp ../fastpath_$(ver)_all.deb  $(shell cat .betahost):/tmp/
	ssh $(shell cat .betahost) sudo dpkg -i /tmp/fastpath_$(ver)_all.deb

beta_quickdeploy:
	rsync -ap fastpath/*.py $(shell cat .betahost):/usr/lib/python3.7/dist-packages/fastpath/
	rsync -ap fastpath/tests/*.py $(shell cat .betahost):/usr/lib/python3.7/dist-packages/fastpath/tests/

beta_shell:
	ssh $(shell cat .betahost) $(args)

beta_run_devel:
	ssh $(shell cat .betahost) killall fastpath >/dev/null || true
	ssh $(shell cat .betahost) -t fastpath --devel \
		--start-day=2019-7-20 --end-day=2019-7-21 $(args)

beta_run_devel_profile:
	ssh $(shell cat .betahost) killall fastpath || true
	ssh $(shell cat .betahost) -t python3 -m cProfile -o profile \
		/usr/bin/fastpath --devel \
		--start-day=2019-7-20 --end-day=2019-7-21 $(args)
	rsync -ap $(shell cat .betahost):~/profile .

beta_functests:
	# e.g. make beta_quickdeploy beta_functests args='-k foo'
	ssh $(shell cat .betahost) killall fastpath || true
	ssh $(shell cat .betahost) -t PYTHONPATH=. pytest-3 -s  --log-cli-level info \
		/usr/lib/python3.7/dist-packages/fastpath/tests $(args)

beta_monitor_metrics:
	ssh $(shell cat .betahost) \
		"tcpdump -npqi lo udp port 8125 -A -l | grep --line-buffered fastpat | sed 's/.*fastpath\.//'"
