set gds_file output/nmos.gds
set cell_name NMOS_TOP
foreach {key variable} {
    PCELL_MAGIC_GDS gds_file
    PCELL_MAGIC_TOP cell_name
    PCELL_MAGIC_OUTPUT spice_file
} {
    if {[info exists env($key)]} {set $variable $env($key)}
}

if {[catch {
    if {[tech name] ni {sky130A sky130A-F}} {
        error "Sky130A technology is not loaded (found [tech name])"
    }
    if {![file isfile $gds_file]} {error "GDS file not found: $gds_file"}
    drc off
    gds read $gds_file
    if {$cell_name ni [cellname list allcells]} {error "GDS top cell not found: $cell_name"}
    load $cell_name
    select top cell
    extract do local
    if {$extraction_mode eq "rcx"} {
        extract do capacitance
        extract do coupling
    }
    extract all

    if {$extraction_mode eq "lvs"} {
        ext2spice lvs
        ext2spice subcircuits top on
        # Preserve internal well connections when Netgen compares a flat reference.
        ext2spice hierarchy off
    } else {
        extresist extout on
        extresist lumped on
        extresist threshold 0
        extresist minresist 0
        extresist simplify off
        extresist prune 0
        extresist mindelay 0
        extresist all
        extresist stats
        ext2spice lvs off
        ext2spice cthresh 0
        ext2spice rthresh 0
        ext2spice extresist on
        ext2spice hierarchy on
    }
    file mkdir [file dirname $spice_file]
    ext2spice -o $spice_file
    if {![file isfile $spice_file] || [file size $spice_file] == 0} {
        error "No SPICE output was written: $spice_file"
    }
    puts "SPICE_OUTPUT=$spice_file"
} message]} {
    puts stderr "Sky130A extraction failed: $message"
    exit 1
}
quit -noprompt
