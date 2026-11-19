set extraction_mode lvs
set spice_file output/lvs/nmos_extracted.spice
source [file join [file dirname [info script]] extract_nmos_common.tcl]
