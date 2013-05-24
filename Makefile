SHELL=/bin/bash
SHELLOPTS=errexit:pipefail

VENV=env
ACTIVATE:=$(VENV)/bin/activate

.PHONY: clean

requirements = requirements*.txt
virtualenv: $(ACTIVATE)
$(ACTIVATE): $(requirements)
	test -d $(VENV) || virtualenv --no-site-packages $(VENV)
	for f in $?; do \
		. $(ACTIVATE); pip install -r $$f; \
	done
	touch $(ACTIVATE)

clean:
	rm -rf $(VENV)
