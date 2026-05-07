# DB9 Straight-Through Cable Reference

Use when connecting DTE↔DCE devices that expect standard RS-232 pin continuity.

## Pin Map (1:1)
- 1 ↔ 1 (DCD)
- 2 ↔ 2 (RXD)
- 3 ↔ 3 (TXD)
- 4 ↔ 4 (DTR)
- 5 ↔ 5 (GND)
- 6 ↔ 6 (DSR)
- 7 ↔ 7 (RTS)
- 8 ↔ 8 (CTS)
- 9 ↔ 9 (RI)

## Notes
- Straight-through is not null-modem; TX/RX are not crossed.
- If two DTE endpoints are connected directly, use null-modem instead.
- Confirm connector orientation (front vs solder/rear view) before crimp/solder.
