set extraction_mode rcx
set spice_file output/rcx/nmos_rcx.spice
source [file join [file dirname [info script]] extract_nmos_common.tcl]
