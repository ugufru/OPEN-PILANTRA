# OPEN PILANTRA — build
#
#   make toolchain   one-time: fetch and build ugbc.coco, asm6809 and decb
#   make             compile OPIL-source.bas to build/OPIL.dsk
#   make run         compile, then boot it in XRoar
#   make run-en      boot the shipped OPIL-EN.dsk
#   make run-br      boot the shipped OPIL_BR.dsk
#   make compare     structural diff of build/OPIL.dsk against OPIL-EN.dsk
#   make clean       remove build/
#   make distclean   also remove the toolchain
#
# The default target never writes to the committed .dsk images.

SOURCE      := OPIL-source.bas
BUILD       := build
DSK         := $(BUILD)/OPIL.dsk

TOOLCHAIN   := .toolchain/ugbasic
UGBC        := $(TOOLCHAIN)/ugbc/exe/ugbc.coco
ASM6809     := $(TOOLCHAIN)/modules/asm6809/src/asm6809
DECB        := $(TOOLCHAIN)/modules/toolshed/build/unix/decb/decb

UGBASIC_REPO := https://github.com/spotlessmind1975/ugbasic.git
# The ugBASIC commit the toolchain is built from. Pinned so a fresh clone gets
# the compiler this project was verified against, not whatever main is today.
# To move it: change this, then 'make distclean toolchain'.
UGBASIC_REF  := 3408443afaed163e0200e5a91b5212f8add18ee3

# XRoar. coco2bus is NTSC: the WAIT pacing in the source assumes 60 Hz, so a
# PAL profile (coco2b) runs everything ~17% slow. -cart rsdos is mandatory.
XROAR       := xroar
XROAR_FLAGS := -machine coco2bus -cart rsdos -ao null
XROAR_RUN   := -type 'RUN"LOADER"\r'
TIMEOUT     ?= 120

# --- macOS needs GNU bison >= 3 and GNU sed ahead of the system ones --------
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
  BREW       := $(shell brew --prefix 2>/dev/null)
  TOOL_PATH  := $(BREW)/opt/bison/bin:$(BREW)/opt/gnu-sed/libexec/gnubin:$(PATH)
  BREW_DEPS  := autoconf automake libtool bison gnu-sed
else
  TOOL_PATH  := $(PATH)
  BREW_DEPS  :=
endif

.PHONY: all run run-en run-br compare clean distclean toolchain deps

all: $(DSK)

$(DSK): $(SOURCE) | $(UGBC) $(ASM6809) $(DECB)
	@mkdir -p $(BUILD)
	$(UGBC) -C $(ASM6809) -b $(DECB) -o $@ -O dsk $<
	@echo "built $@ ($$(wc -c < $@) bytes)"

run: $(DSK)
	$(XROAR) $(XROAR_FLAGS) -load-fd0 $(DSK) -timeout $(TIMEOUT) $(XROAR_RUN)

run-en:
	$(XROAR) $(XROAR_FLAGS) -load-fd0 OPIL-EN.dsk -timeout $(TIMEOUT) $(XROAR_RUN)

run-br:
	$(XROAR) $(XROAR_FLAGS) -load-fd0 OPIL_BR.dsk -timeout $(TIMEOUT) $(XROAR_RUN)

# A freshly built image will NOT be byte-identical to the shipped one - the
# originals were produced by an older ugbc. Structure is what should match:
# same size, and a directory of LOADER.BAS + P + P.00 + P.01.
compare: $(DSK)
	@echo "size:   shipped $$(wc -c < OPIL-EN.dsk)  built $$(wc -c < $(DSK))"
	@echo "differing bytes: $$(cmp -l OPIL-EN.dsk $(DSK) 2>/dev/null | wc -l)"
	@echo "--- shipped directory ---"; od -A d -c -j 78848 -N 160 OPIL-EN.dsk | grep -v '^\*'
	@echo "--- built directory ---";   od -A d -c -j 78848 -N 160 $(DSK)      | grep -v '^\*'

clean:
	rm -rf $(BUILD)

distclean: clean
	rm -rf .toolchain

# --- toolchain --------------------------------------------------------------
#
# ugBASIC ships prebuilt Linux x86-64 binaries and objects inside the ToolShed
# module. They are purged below so the native compiler rebuilds them; without
# that, decb links as an ELF and ugbc fails with the unhelpful message
# "The compilation of assembly program failed. Please use option '-I'".

toolchain: $(UGBC) $(ASM6809) $(DECB)
	@have=$$(git -C $(TOOLCHAIN) rev-parse HEAD); \
	 if [ "$$have" != "$(UGBASIC_REF)" ]; then \
	   echo "warning: $(TOOLCHAIN) is at $$have, not the pinned $(UGBASIC_REF)." >&2; \
	   echo "         run 'make distclean toolchain' to rebuild it." >&2; \
	 fi
	@echo "toolchain ready"

deps:
ifneq ($(BREW_DEPS),)
	brew install $(BREW_DEPS)
else
	@echo "install autoconf, automake, libtool, bison (>=3) and flex via your package manager"
endif

# Fetched into a .tmp directory and renamed only once complete, so an
# interrupted fetch cannot leave a half-populated $(TOOLCHAIN) that make would
# then treat as done.
$(TOOLCHAIN):
	rm -rf $(TOOLCHAIN).tmp && mkdir -p $(TOOLCHAIN).tmp
	cd $(TOOLCHAIN).tmp && git init -q \
	    && git remote add origin $(UGBASIC_REPO) \
	    && git fetch --depth 1 origin $(UGBASIC_REF) \
	    && git checkout -q FETCH_HEAD \
	    && git submodule update --init --depth 1
	mv $(TOOLCHAIN).tmp $(TOOLCHAIN)

$(UGBC): | $(TOOLCHAIN)
	cd $(TOOLCHAIN)/ugbc && PATH="$(TOOL_PATH)" $(MAKE) compiler target=coco

$(ASM6809): | $(TOOLCHAIN)
	cd $(TOOLCHAIN)/modules/asm6809 && PATH="$(TOOL_PATH)" ./autogen.sh \
	    && ./configure && PATH="$(TOOL_PATH)" $(MAKE)

$(DECB): | $(TOOLCHAIN)
	cd $(TOOLCHAIN)/modules/toolshed/build/unix \
	    && find . -name '*.o' -delete && find . -name '*.a' -delete \
	    && rm -f decb/decb \
	    && $(MAKE) all
