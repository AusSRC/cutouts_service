TEMPLATES_MAKEFILE := python-templates/Makefile

ifeq ($(wildcard $(TEMPLATES_MAKEFILE)),)
$(error $(TEMPLATES_MAKEFILE) not found. Run 'git submodule update --init --recursive')
endif

include $(TEMPLATES_MAKEFILE)
