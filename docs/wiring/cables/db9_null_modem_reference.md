# DB9 Null Modem Reference (Starter)

## Important
Always confirm **view orientation** before wiring:
- Front view (mating face)
- Rear/solder-cup view (mirrored)

Most field mistakes come from mixing these views.

---

## 1) 3-wire null modem (basic)
Use for simple TX/RX/GND links.

- A pin 2 (RXD) ↔ B pin 3 (TXD)
- A pin 3 (TXD) ↔ B pin 2 (RXD)
- A pin 5 (GND) ↔ B pin 5 (GND)

No hardware flow control lines.

---

## 2) Full-handshake null modem (common)
Use when endpoints expect RTS/CTS and DTR/DSR semantics.

- RX/TX crossover:
  - A2 ↔ B3
  - A3 ↔ B2
- Ground:
  - A5 ↔ B5
- Flow control crossover:
  - A7 (RTS) ↔ B8 (CTS)
  - A8 (CTS) ↔ B7 (RTS)
- Ready/carrier cross-coupling (common variant):
  - A4 (DTR) ↔ B6 (DSR)
  - A6 (DSR) ↔ B4 (DTR)
  - A1 (DCD) tied to local DTR/DSR as required by device behavior

Because vendors vary here, validate with loopback tests and actual device docs.

---

## 3) Bench Test Checklist
- Continuity check each mapped pin end-to-end.
- Confirm no shorts between adjacent pins.
- Verify orientation labels on printed diagram.
- Run terminal loopback sanity check before field deployment.

---

## Planned Next
- Add DB9 straight-through cable reference.
- Add RS232↔TTL adapter caveats (voltage level warning).
- Add printable pin map cards.
