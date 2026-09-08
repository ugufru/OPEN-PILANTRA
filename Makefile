# OPEN PILANTRA — build
#
#   make toolchain   one-time: fetch and build ugbc.coco, asm6809 and decb
#   make             compile to build/OPIL.dsk from story/ and art/
#   make run         compile, then boot it in XRoar
#   make run-en      boot the shipped OPIL-EN.dsk
#   make run-br      boot the shipped OPIL_BR.dsk
#   make compare     structural diff of build/OPIL.dsk against OPIL-EN.dsk
#   make clean       remove build/
#   make distclean   also remove the toolchain
#
# The default target never writes to the committed .dsk images.

# original/ holds the author's files, read-only to the build. story/dialogue.json
# and art/*.png are the sources of truth: the build strips the DATA blocks and DIM
# arrays out of the original source and re-supplies both from those.
SOURCE      := original/OPIL-source.bas
STORY       := story/dialogue.json
GENDIR      := generated
GENDLG      := $(GENDIR)/dialogue.bas
GENART      := $(GENDIR)/art.bas
BUILDSRC    := src/opil.bas
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

.PHONY: all run run-en run-br compare clean distclean toolchain deps \
        dialogue-extract dialogue-lint art-extract

all: $(DSK)

# --- dialogue as data -------------------------------------------------------

$(GENDLG): $(STORY) tools/dialogue.py
	python3 tools/dialogue.py emit $(STORY) $@

# The build source is OPIL-source.bas with both its DATA blocks and its DIM
# byte arrays lifted out, each replaced by an INCLUDE of a generated file.
$(BUILDSRC): $(SOURCE) tools/dialogue.py tools/art.py
	@mkdir -p $(dir $@)
	python3 tools/dialogue.py strip $(SOURCE) $@.tmp $(GENDLG)
	python3 tools/art.py strip $@.tmp $@ $(GENART)
	@rm -f $@.tmp

dialogue-lint:                          ## check the authoring constraints
	python3 tools/dialogue.py lint $(STORY)

dialogue-extract:                       ## re-derive the JSON from the .bas
	python3 tools/dialogue.py extract $(SOURCE) $(STORY)

# --- graphics as data -------------------------------------------------------
ART := art

$(GENART): $(wildcard art/*.png) art/manifest.json tools/art.py
	python3 tools/art.py emit $(ART) $@

art-extract:                            ## re-derive the PNGs from the .bas
	python3 tools/art.py extract $(SOURCE) $(ART)

$(DSK): $(BUILDSRC) $(GENDLG) $(GENART) | $(UGBC) $(ASM6809) $(DECB)
	@mkdir -p $(BUILD)
	$(UGBC) -C $(ASM6809) -b $(DECB) -o $@ -O dsk $(BUILDSRC)
	@# ugbc exits 0 even when its assembler or linker step failed, so check.
	@test -s $@ || { echo "ugbc produced no $@: see the errors above" >&2; exit 1; }
	@echo "built $@ ($$(wc -c < $@) bytes)"

run: $(DSK)
	$(XROAR) $(XROAR_FLAGS) -load-fd0 $(DSK) -timeout $(TIMEOUT) $(XROAR_RUN)

run-en:
	$(XROAR) $(XROAR_FLAGS) -load-fd0 original/OPIL-EN.dsk -timeout $(TIMEOUT) $(XROAR_RUN)

run-br:
	$(XROAR) $(XROAR_FLAGS) -load-fd0 original/OPIL_BR.dsk -timeout $(TIMEOUT) $(XROAR_RUN)

# A freshly built image will NOT be byte-identical to the shipped one - the
# originals were produced by an older ugbc. Structure is what should match:
# same size, and a directory of LOADER.BAS + P + P.00 + P.01.
compare: $(DSK)
	@echo "size:   shipped $$(wc -c < original/OPIL-EN.dsk)  built $$(wc -c < $(DSK))"
	@echo "differing bytes: $$(cmp -l original/OPIL-EN.dsk $(DSK) 2>/dev/null | wc -l)"
	@echo "--- shipped directory ---"; od -A d -c -j 78848 -N 160 original/OPIL-EN.dsk | grep -v '^\*'
	@echo "--- built directory ---";   od -A d -c -j 78848 -N 160 $(DSK)      | grep -v '^\*'

clean:
	rm -rf $(BUILD)

distclean: clean
	rm -rf .toolchain

# --- toolchain --------------------------------------------------------------
#
# ugBASIC ships prebuilt Linux x86-64 binaries and objects inside the ToolShed
# module, decb among them. Because decb is committed, it exists the moment the
# submodule is checked out, and make would then treat $(DECB) as already up to
# date and never run its rule at all. The clone recipe therefore deletes it, and
# the $(DECB) rule purges the stale objects before rebuilding. Without both, the
# ELF binary is handed to ugbc, which fails with the unhelpful message
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
	@# Drop ToolShed's committed Linux decb so the $(DECB) rule actually fires.
	rm -f $(DECB)

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
