# domestic180

domestic180 is a self-contained 180 nm CMOS PDK for PCellAutoVerify. Select this directory in **PDK Manager → Import PDK...** and activate **domestic180**. It uses the Python KLayout package already required by the application.

The three PCells are single-finger NMOS, single-finger PMOS, and a CMOS inverter. The default channel length is 0.18 µm and the default width is 0.60 µm. Transistor parameters are rounded to 0.005 µm increments. The inverter has four ports, A, Y, VDD and VSS. The standalone MOS devices have D, G, S and B ports.

| GDS layer | Purpose |
| --- | --- |
| 1/0 and 2/0 | NMOS and PMOS active regions |
| 3/0 | Gate |
| 4/0 | Contact |
| 5/0 and 5/16 | Metal1 and named pin labels |
| 6/0 and 7/0 | NMOS and PMOS body contacts |

Automatic generation creates a default layout and a narrow-metal variant. Manual generation appends a layout using the values returned by the parameter callback.

- **DRC** checks channel length, active width, and Metal1 width, spacing and area. Thresholds are in [pdk.json](pdk.json).
- **LVS** measures device W/L from gate and active overlap and derives terminal connectivity from contacts, merged Metal1 and port labels in the GDS. It compares that circuit with an independent reference generated from the generation parameters.
- **RCX** writes a SPICE netlist with one lumped lead resistance and area capacitance per named net. The resistance estimate uses the Metal1 perimeter and area, and the capacitance estimate uses Metal1 area. The coefficients are configurable in the manifest.

The layer stack is abstract and the RC coefficients are estimates. Fabrication rules, transistor simulation models and signoff-quality parasitics require a foundry PDK.
