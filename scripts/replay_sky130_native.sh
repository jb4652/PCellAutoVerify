#!/usr/bin/env sh
# Run the installed Magic and Netgen commands against one existing GDS.
set -eu

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
    printf 'Usage: %s SKY130A_ROOT GDS_FILE REFERENCE_SPICE [TOP_CELL]\n' "$0" >&2
    exit 2
fi

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_directory=$(dirname -- "$script_directory")
pdk=$(realpath -- "$1")
gds=$(realpath -- "$2")
reference=$(realpath -- "$3")
top=${4:-VERIFY_TOP}
if [ "$(basename -- "$pdk")" != sky130A ] || [ ! -f "$gds" ] || [ ! -f "$reference" ]; then
    printf '%s\n' 'Provide a sky130A installation directory, GDS file and reference SPICE file.' >&2
    exit 2
fi
setup="$pdk/libs.tech/netgen/sky130A_setup.tcl"
if [ ! -f "$setup" ]; then
    printf 'Netgen setup not found: %s\n' "$setup" >&2
    exit 2
fi

export PDK_ROOT="$(dirname -- "$pdk")"
export PCELL_MAGIC_GDS="$gds"
export PCELL_MAGIC_TOP="$top"
rcfile="$pdk/libs.tech/magic/sky130A.magicrc"
[ -f "$rcfile" ] || rcfile="$project_directory/config/sky130A.magicrc"
base="$project_directory/output/cli"
mkdir -p "$base"
run_directory=$(mktemp -d "$base/native-XXXXXX")
printf 'Native reports: %s\n' "$run_directory"
cd "$run_directory"

PCELL_MAGIC_OUTPUT="$PWD/drc.txt" magic -dnull -noconsole -rcfile "$rcfile" "$script_directory/run_nmos_drc.tcl" > magic-drc.log 2>&1
PCELL_MAGIC_OUTPUT="$PWD/extracted.spice" magic -dnull -noconsole -rcfile "$rcfile" "$script_directory/extract_nmos_lvs.tcl" > magic-lvs.log 2>&1
cp -- "$reference" reference.spice
netgen-lvs -batch lvs "extracted.spice $top" "reference.spice $top" "$setup" lvs.log > netgen.log 2>&1
test -s lvs.log
PCELL_MAGIC_OUTPUT="$PWD/rcx.spice" magic -dnull -noconsole -rcfile "$rcfile" "$script_directory/extract_nmos_rcx.tcl" > magic-rcx.log 2>&1
