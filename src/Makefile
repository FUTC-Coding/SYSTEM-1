PREFIX  ?= $(HOME)/.config/system1
CFLAGS  ?= -O2 -Wall -Wno-unused-parameter
PROTO    = wlr-layer-shell-unstable-v1 xdg-shell
GEN      = $(PROTO:%=%-client-protocol.h) $(PROTO:%=%-protocol.c)
LIBS     = $(shell pkg-config --libs wayland-client wayland-egl egl glesv2) -lm

system1-bg: system1-bg.c $(GEN)
	$(CC) $(CFLAGS) -o $@ system1-bg.c $(PROTO:%=%-protocol.c) $(LIBS)

%-client-protocol.h: %.xml
	wayland-scanner client-header $< $@

%-protocol.c: %.xml
	wayland-scanner private-code $< $@

install: system1-bg
	install -Dm755 system1-bg $(PREFIX)/bin/system1-bg

clean:
	rm -f system1-bg $(GEN)

.PHONY: install clean
