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
  SED        := gsed
  BREW_DEPS  := autoconf automake libtool bison gnu-sed
else
  TOOL_PATH  := $(PATH)
  SED        := sed
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
	@echo "toolchain ready"

deps:
ifneq ($(BREW_DEPS),)
	brew install $(BREW_DEPS)
else
	@echo "install autoconf, automake, libtool, bison (>=3) and flex via your package manager"
endif

$(TOOLCHAIN):
	@mkdir -p $(dir $(TOOLCHAIN))
	git clone --depth 1 $(UGBASIC_REPO) $(TOOLCHAIN)
	cd $(TOOLCHAIN) && git submodule update --init --depth 1
	@# Darwin's unistd.h already declares encrypt(); ugbc declares its own with
	@# a different signature. Rename ugbc's so the two stop colliding.
	cd $(TOOLCHAIN)/ugbc && $(SED) -i 's/\bencrypt(/ugbc_encrypt(/g' \
	    src/ugbc.h src/ugbc.y src/targets/common/encrypt.c \
	    src/targets/common/serialize.c \
	    src/hw/6809.c src/hw/6309.c src/hw/6502.c src/hw/z80.c \
	    src/hw/8086.c src/hw/sm83.c

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
