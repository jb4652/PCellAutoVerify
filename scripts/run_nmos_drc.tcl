# The application supplies absolute paths and the GDS top cell.
set gds_path output/nmos.gds
set top_cell NMOS_TOP
set report_path output/nmos_drc.txt
foreach {key variable} {
    PCELL_DRC_GDS gds_path
    PCELL_DRC_TOP top_cell
    PCELL_DRC_REPORT report_path
    PCELL_MAGIC_GDS gds_path
    PCELL_MAGIC_TOP top_cell
    PCELL_MAGIC_OUTPUT report_path
} {
    if {[info exists env($key)]} {set $variable $env($key)}
}

if {[catch {
    if {[tech name] ni {sky130A sky130A-F}} {
        error "Sky130A technology is not loaded (found [tech name])"
    }
    if {![file isfile $gds_path]} {error "GDS file not found: $gds_path"}
    drc off
    gds read $gds_path
    if {$top_cell ni [cellname list allcells]} {
        error "GDS top cell not found: $top_cell"
    }
    load $top_cell
    select top cell
    box select
    drc on
    drc check
    drc catchup
    set count [drc listall count total]
    if {![string is integer -strict $count] || $count < 0} {
        error "Magic did not return a valid DRC count: $count"
    }
    set details [drc listall why]
    file mkdir [file dirname $report_path]
    set fp [open $report_path w]
    puts $fp "DRC_TOTAL_ERRORS=$count"
    puts $fp "DRC_DETAILS=$details"
    close $fp
    puts "DRC_TOTAL_ERRORS=$count"
} message]} {
    puts stderr "Sky130A DRC failed: $message"
    exit 1
}
quit -noprompt
