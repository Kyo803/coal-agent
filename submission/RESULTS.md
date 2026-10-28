# ROX N — 50 unique chips (designed by ROX N)

- catalogue      : 50 unique designs
- attempted      : 50
- passed         : 44
- failed         : 6
- pending        : 0
- failure kinds  : {'behaviour mismatch': 3, 'lint/parse': 3}
- functional TB  : 44
- clocked        : 31
- total area     : 2422 cells / 395 FFs

| # | chip | what it is | use | result | cells/FF | Fmax |
|---|---|---|---|---|---|---|
| 1 | `bcd2seg` | 4-bit binary to 7-segment decoder, active-low segments, valid for 0-9 and A-F | digital clocks, meters, instrument panels | PASS | 31/- | - |
| 2 | `bin2bcd` | 8-bit binary to 3-digit BCD converter using the double-dabble algorithm, combinational, outputs hundreds/tens/ones | 7-segment displays, frequency counters | PASS | 118/- | - |
| 3 | `graycounter` | 4-bit Gray-code counter with synchronous reset and enable | rotary encoders, asynchronous FIFO pointers | PASS | 12/4 | 448 MHz |
| 4 | `johnson` | 4-bit Johnson counter with synchronous reset and an output enable | one-hot state generation, low-EMI clock division | PASS | 5/4 | 627 MHz |
| 5 | `ringcounter` | 8-bit one-hot ring counter with rotate enable and synchronous reset | LED chasers, sequencer state machines | PASS | 8/8 | 627 MHz |
| 6 | `lfsr8` | 8-bit maximal-length LFSR, polynomial x^8+x^6+x^5+x^4+1, enable and seed load, never all-zero | PRBS test patterns, data scrambling, built-in self-test | PASS | 35/8 | 390 MHz |
| 7 | `crc8` | CRC-8 generator, polynomial 0x07, serial data input with valid, 8-bit CRC output with a done strobe | packet integrity, serial protocols, storage | PASS | 21/12 | 474 MHz |
| 8 | `parity` | 8-bit parity generator/checker with even/odd mode and an error output | memory ECC front-ends, UART parity, buses | PASS | 8/- | - |
| 9 | `hamming_enc` | Hamming(7,4) encoder: 4 data bits to a 7-bit codeword | single-error-correcting memory, telemetry | PASS | 7/- | - |
| 10 | `manchester_enc` | Manchester encoder: serial bit with valid input, Manchester line output with a bit-clock output | Ethernet PHYs, RFID, IR links | PASS | 12/5 | 316 MHz |
| 11 | `quadrature` | quadrature decoder for a rotary encoder with 4x decoding, direction output and a 16-bit position counter | motor feedback, knobs, CNC axes | PASS | 129/19 | 173 MHz |
| 12 | `edge_detect` | edge detector with rising, falling and both-edge one-cycle pulses | event capture, interrupt generation | PASS | 7/4 | 655 MHz |
| 13 | `debounce` | parameterised button debouncer with synchronous sampling and a clean registered output | push buttons, mechanical switches | PASS | 36/10 | 234 MHz |
| 14 | `oneshot` | retriggerable one-shot pulse generator with a programmable width | pulse stretching, timing control | PASS | 17/4 | 223 MHz |
| 15 | `watchdog` | watchdog timer with a kick input, configurable period, and a timeout pulse that stays until reset | embedded systems, lock-up recovery | PASS | 17/6 | 234 MHz |
| 16 | `interval_timer` | 16-bit programmable down counter with load, enable, and a one-cycle timeout pulse | OS tick timers, PWM periods, delays | PASS | 126/17 | 100 MHz |
| 17 | `stopwatch` | stopwatch with start/stop/clear and BCD centisecond + second outputs | sports timers, bench instruments | PASS | 53/13 | 256 MHz |
| 18 | `updown` | 8-bit up/down counter with parallel load, enable, and terminal count | position control, general counting | PASS | 56/8 | 211 MHz |
| 19 | `satadd` | 8-bit unsigned saturating adder with a saturation flag | audio/image processing, control loops | PASS | 57/- | - |
| 20 | `absval` | 8-bit two's complement absolute value with sign and overflow flags | DSP magnitude, distance metrics | PASS | 25/- | - |
| 21 | `prio16` | 16-to-4 priority encoder with valid output, highest index wins | interrupt controllers, arbiters | PASS | 84/- | - |
| 22 | `barrelshift` | 8-bit barrel shifter: left/right, 0-7 positions, arithmetic or logical mode | ALU datapaths, floating point | PASS | 58/- | - |
| 23 | `lzc` | 8-bit leading-zero counter with an all-zero flag | floating-point normalisation, compression | PASS | 34/- | - |
| 24 | `popcount` | 4-bit population count (number of ones) with a 3-bit result | bit manipulation, Hamming weight, neural nets | PASS | 10/- | - |
| 25 | `bitrev` | 8-bit bit-reversal, combinational | FFT butterflies, bit-serial protocols | PASS | 8/8 | - |
| 26 | `mac4` | 4-bit multiply-accumulate with clear and valid, 8-bit accumulator | FIR filters, neural accelerators | PASS | 115/8 | 169 MHz |
| 27 | `reset_sync` | asynchronous-assert, synchronous-deassert reset synchroniser | safe reset distribution | PASS | 2/2 | 627 MHz |
| 28 | `cdc_sync` | two-flop synchroniser for a single-bit signal with a pulse output | clock-domain crossing of flags | PASS | 4/3 | 627 MHz |
| 29 | `clkdiv3` | clock divider by 3 with 50% duty cycle and synchronous reset | clock generation, baud rates | PASS | 7/3 | 366 MHz |
| 30 | `pwm_deadtime` | PWM generator with complementary outputs and programmable dead-time | H-bridge motor drivers, inverters | PASS | 25/7 | 319 MHz |
| 31 | `servo` | servo PWM controller: 50 Hz frame, 1-2 ms pulse proportional to an 8-bit position input | hobby servos, robotics | PASS | 414/32 | 125 MHz |
| 32 | `stepper` | stepper motor full-step sequencer for 4 coils with direction and enable inputs | 3D printers, CNC, robotics | PASS | 8/4 | 646 MHz |
| 33 | `traffic` | traffic light FSM with red/yellow/green, a pedestrian request, and timed transitions | intersection controllers, teaching FSMs | PASS | 82/12 | 189 MHz |
| 34 | `vend` | vending machine FSM accepting 5/10/25 coins, dispensing at 30, with change and cancel | automata, payment state machines | PASS | 63/8 | 139 MHz |
| 35 | `elevator` | 3-floor elevator controller with call buttons, door open/close, and direction output | building control, FSM examples | FAIL | 23/5 | 336 MHz |
| 36 | `seqdet` | sequence detector for the pattern 1011 with overlapping detection | protocol framing, pattern search | PASS | 7/4 | 627 MHz |
| 37 | `keypad` | 4x4 keypad scanner with row drive, column read, debounce, and a key-valid output with the key code | embedded user input | FAIL | -/- | - |
| 38 | `segmux` | 4-digit 7-segment multiplexer with digit enables and a refresh divider | multi-digit displays | PASS | 63/2 | 655 MHz |
| 39 | `ledchase` | 8-LED chaser with adjustable speed and direction | indicators, decorative lighting | PASS | 64/16 | 146 MHz |
| 40 | `melody` | buzzer melody player with a note ROM, tempo divider, and start input | alarms, toys, simple music | FAIL | 83/17 | 248 MHz |
| 41 | `spi_slave` | SPI slave, mode 0, 8-bit, with chip select, sclk, mosi, miso, and a received-byte valid strobe | sensors, memories, MCU peripherals | FAIL | -/- | - |
| 42 | `spi_master` | SPI master, mode 0, 8-bit, with start/busy, sclk, mosi, miso and a received byte | flash, displays, ADCs | FAIL | 5/2 | 350 MHz |
| 43 | `uart_parity` | UART transmitter with an even parity bit, 8 data bits, 1 stop bit, start/busy handshake | serial links with error detection | PASS | 69/18 | 236 MHz |
| 44 | `pulse_width` | pulse-width measurement: measure the high time of an input in clock cycles with a 16-bit result and a valid strobe | sensors, RC decoding | PASS | 81/35 | 216 MHz |
| 45 | `freq_counter` | frequency counter: count input edges over a gate period with a 16-bit result and an overflow flag | bench instruments, tachometers | PASS | 95/35 | 176 MHz |
| 46 | `stack8` | 8-entry LIFO stack with push/pop, full and empty flags | CPU call stacks, expression evaluation | PASS | 187/68 | 194 MHz |
| 47 | `pc_branch` | 8-bit program counter with load, increment enable, and branch | CPU fetch units | PASS | 33/8 | 278 MHz |
| 48 | `idecode` | simple instruction decoder: 8-bit opcode to ALU op, register write enable, memory read/write, and immediate flag | CPU control units | PASS | 9/- | - |
| 49 | `booth` | 4x4 Booth multiplier producing a signed 8-bit product | low-power multipliers, DSP | PASS | 120/- | - |
| 50 | `sar_adc` | SAR ADC controller: 8-bit successive approximation with sample, compare input, done, and result | analog sensing, MCU ADCs | FAIL | 117/21 | 163 MHz |

## Per-chip detail

### 1. `bcd2seg` — PASS
- **does:** 4-bit binary to 7-segment decoder, active-low segments, valid for 0-9 and A-F
- **use:** digital clocks, meters, instrument panels
- **cost:** 31 cells / 0 FF · Fmax n/a (combinational) · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 2. `bin2bcd` — PASS
- **does:** 8-bit binary to 3-digit BCD converter using the double-dabble algorithm, combinational, outputs hundreds/tens/ones
- **use:** 7-segment displays, frequency counters
- **cost:** 118 cells / 0 FF · Fmax n/a (combinational) · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 3. `graycounter` — PASS
- **does:** 4-bit Gray-code counter with synchronous reset and enable
- **use:** rotary encoders, asynchronous FIFO pointers
- **cost:** 12 cells / 4 FF · Fmax 447.6 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 4. `johnson` — PASS
- **does:** 4-bit Johnson counter with synchronous reset and an output enable
- **use:** one-hot state generation, low-EMI clock division
- **cost:** 5 cells / 4 FF · Fmax 626.6 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 5. `ringcounter` — PASS
- **does:** 8-bit one-hot ring counter with rotate enable and synchronous reset
- **use:** LED chasers, sequencer state machines
- **cost:** 8 cells / 8 FF · Fmax 626.6 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 6. `lfsr8` — PASS
- **does:** 8-bit maximal-length LFSR, polynomial x^8+x^6+x^5+x^4+1, enable and seed load, never all-zero
- **use:** PRBS test patterns, data scrambling, built-in self-test
- **cost:** 35 cells / 8 FF · Fmax 390.3 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 7. `crc8` — PASS
- **does:** CRC-8 generator, polynomial 0x07, serial data input with valid, 8-bit CRC output with a done strobe
- **use:** packet integrity, serial protocols, storage
- **cost:** 21 cells / 12 FF · Fmax 474.4 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 8. `parity` — PASS
- **does:** 8-bit parity generator/checker with even/odd mode and an error output
- **use:** memory ECC front-ends, UART parity, buses
- **cost:** 8 cells / 0 FF · Fmax n/a (combinational) · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 9. `hamming_enc` — PASS
- **does:** Hamming(7,4) encoder: 4 data bits to a 7-bit codeword
- **use:** single-error-correcting memory, telemetry
- **cost:** 7 cells / 0 FF · Fmax n/a (combinational) · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 10. `manchester_enc` — PASS
- **does:** Manchester encoder: serial bit with valid input, Manchester line output with a bit-clock output
- **use:** Ethernet PHYs, RFID, IR links
- **cost:** 12 cells / 5 FF · Fmax 316.4 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 11. `quadrature` — PASS
- **does:** quadrature decoder for a rotary encoder with 4x decoding, direction output and a 16-bit position counter
- **use:** motor feedback, knobs, CNC axes
- **cost:** 129 cells / 19 FF · Fmax 173.2 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 12. `edge_detect` — PASS
- **does:** edge detector with rising, falling and both-edge one-cycle pulses
- **use:** event capture, interrupt generation
- **cost:** 7 cells / 4 FF · Fmax 655.3 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 13. `debounce` — PASS
- **does:** parameterised button debouncer with synchronous sampling and a clean registered output
- **use:** push buttons, mechanical switches
- **cost:** 36 cells / 10 FF · Fmax 233.6 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 14. `oneshot` — PASS
- **does:** retriggerable one-shot pulse generator with a programmable width
- **use:** pulse stretching, timing control
- **cost:** 17 cells / 4 FF · Fmax 223.4 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 15. `watchdog` — PASS
- **does:** watchdog timer with a kick input, configurable period, and a timeout pulse that stays until reset
- **use:** embedded systems, lock-up recovery
- **cost:** 17 cells / 6 FF · Fmax 233.6 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 16. `interval_timer` — PASS
- **does:** 16-bit programmable down counter with load, enable, and a one-cycle timeout pulse
- **use:** OS tick timers, PWM periods, delays
- **cost:** 126 cells / 17 FF · Fmax 99.9 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 17. `stopwatch` — PASS
- **does:** stopwatch with start/stop/clear and BCD centisecond + second outputs
- **use:** sports timers, bench instruments
- **cost:** 53 cells / 13 FF · Fmax 255.8 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 18. `updown` — PASS
- **does:** 8-bit up/down counter with parallel load, enable, and terminal count
- **use:** position control, general counting
- **cost:** 56 cells / 8 FF · Fmax 211.0 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 19. `satadd` — PASS
- **does:** 8-bit unsigned saturating adder with a saturation flag
- **use:** audio/image processing, control loops
- **cost:** 57 cells / 0 FF · Fmax n/a (combinational) · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 20. `absval` — PASS
- **does:** 8-bit two's complement absolute value with sign and overflow flags
- **use:** DSP magnitude, distance metrics
- **cost:** 25 cells / 0 FF · Fmax n/a (combinational) · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 21. `prio16` — PASS
- **does:** 16-to-4 priority encoder with valid output, highest index wins
- **use:** interrupt controllers, arbiters
- **cost:** 84 cells / 0 FF · Fmax n/a (combinational) · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 22. `barrelshift` — PASS
- **does:** 8-bit barrel shifter: left/right, 0-7 positions, arithmetic or logical mode
- **use:** ALU datapaths, floating point
- **cost:** 58 cells / 0 FF · Fmax n/a (combinational) · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 23. `lzc` — PASS
- **does:** 8-bit leading-zero counter with an all-zero flag
- **use:** floating-point normalisation, compression
- **cost:** 34 cells / 0 FF · Fmax n/a (combinational) · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 24. `popcount` — PASS
- **does:** 4-bit population count (number of ones) with a 3-bit result
- **use:** bit manipulation, Hamming weight, neural nets
- **cost:** 10 cells / 0 FF · Fmax n/a (combinational) · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 25. `bitrev` — PASS
- **does:** 8-bit bit-reversal, combinational
- **use:** FFT butterflies, bit-serial protocols
- **cost:** 8 cells / 8 FF · Fmax n/a (combinational) · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 26. `mac4` — PASS
- **does:** 4-bit multiply-accumulate with clear and valid, 8-bit accumulator
- **use:** FIR filters, neural accelerators
- **cost:** 115 cells / 8 FF · Fmax 169.2 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 27. `reset_sync` — PASS
- **does:** asynchronous-assert, synchronous-deassert reset synchroniser
- **use:** safe reset distribution
- **cost:** 2 cells / 2 FF · Fmax 626.6 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 28. `cdc_sync` — PASS
- **does:** two-flop synchroniser for a single-bit signal with a pulse output
- **use:** clock-domain crossing of flags
- **cost:** 4 cells / 3 FF · Fmax 626.6 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 29. `clkdiv3` — PASS
- **does:** clock divider by 3 with 50% duty cycle and synchronous reset
- **use:** clock generation, baud rates
- **cost:** 7 cells / 3 FF · Fmax 365.9 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 30. `pwm_deadtime` — PASS
- **does:** PWM generator with complementary outputs and programmable dead-time
- **use:** H-bridge motor drivers, inverters
- **cost:** 25 cells / 7 FF · Fmax 318.9 MHz · qwen2.5-coder:7b · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 31. `servo` — PASS
- **does:** servo PWM controller: 50 Hz frame, 1-2 ms pulse proportional to an 8-bit position input
- **use:** hobby servos, robotics
- **cost:** 414 cells / 32 FF · Fmax 125.1 MHz · qwen2.5-coder:7b · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 32. `stepper` — PASS
- **does:** stepper motor full-step sequencer for 4 coils with direction and enable inputs
- **use:** 3D printers, CNC, robotics
- **cost:** 8 cells / 4 FF · Fmax 646.4 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 33. `traffic` — PASS
- **does:** traffic light FSM with red/yellow/green, a pedestrian request, and timed transitions
- **use:** intersection controllers, teaching FSMs
- **cost:** 82 cells / 12 FF · Fmax 188.8 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 34. `vend` — PASS
- **does:** vending machine FSM accepting 5/10/25 coins, dispensing at 30, with change and cancel
- **use:** automata, payment state machines
- **cost:** 63 cells / 8 FF · Fmax 138.6 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 35. `elevator` — FAIL
- **does:** 3-floor elevator controller with call buttons, door open/close, and direction output
- **use:** building control, FSM examples
- **why it failed:** behaviour mismatch — FATAL: tb_elevator.v:67: ...

### 36. `seqdet` — PASS
- **does:** sequence detector for the pattern 1011 with overlapping detection
- **use:** protocol framing, pattern search
- **cost:** 7 cells / 4 FF · Fmax 626.6 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 37. `keypad` — FAIL
- **does:** 4x4 keypad scanner with row drive, column read, debounce, and a key-valid output with the key code
- **use:** embedded user input
- **why it failed:** lint/parse — 15 error(s) during elaboration.

### 38. `segmux` — PASS
- **does:** 4-digit 7-segment multiplexer with digit enables and a refresh divider
- **use:** multi-digit displays
- **cost:** 63 cells / 2 FF · Fmax 655.3 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 39. `ledchase` — PASS
- **does:** 8-LED chaser with adjustable speed and direction
- **use:** indicators, decorative lighting
- **cost:** 64 cells / 16 FF · Fmax 146.3 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 40. `melody` — FAIL
- **does:** buzzer melody player with a note ROM, tempo divider, and start input
- **use:** alarms, toys, simple music
- **why it failed:** behaviour mismatch — tb_melody.v:129: syntax error

### 41. `spi_slave` — FAIL
- **does:** SPI slave, mode 0, 8-bit, with chip select, sclk, mosi, miso, and a received-byte valid strobe
- **use:** sensors, memories, MCU peripherals
- **why it failed:** lint/parse — %Error: Exiting due to 2 error(s)

### 42. `spi_master` — FAIL
- **does:** SPI master, mode 0, 8-bit, with start/busy, sclk, mosi, miso and a received byte
- **use:** flash, displays, ADCs
- **why it failed:** lint/parse — ERROR: Found 8 problems in 'check -assert'.

### 43. `uart_parity` — PASS
- **does:** UART transmitter with an even parity bit, 8 data bits, 1 stop bit, start/busy handshake
- **use:** serial links with error detection
- **cost:** 69 cells / 18 FF · Fmax 236.3 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 44. `pulse_width` — PASS
- **does:** pulse-width measurement: measure the high time of an input in clock cycles with a 16-bit result and a valid strobe
- **use:** sensors, RC decoding
- **cost:** 81 cells / 35 FF · Fmax 215.6 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 45. `freq_counter` — PASS
- **does:** frequency counter: count input edges over a gate period with a 16-bit result and an overflow flag
- **use:** bench instruments, tachometers
- **cost:** 95 cells / 35 FF · Fmax 176.1 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 46. `stack8` — PASS
- **does:** 8-entry LIFO stack with push/pop, full and empty flags
- **use:** CPU call stacks, expression evaluation
- **cost:** 187 cells / 68 FF · Fmax 193.7 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 47. `pc_branch` — PASS
- **does:** 8-bit program counter with load, increment enable, and branch
- **use:** CPU fetch units
- **cost:** 33 cells / 8 FF · Fmax 277.9 MHz · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 48. `idecode` — PASS
- **does:** simple instruction decoder: 8-bit opcode to ALU op, register write enable, memory read/write, and immediate flag
- **use:** CPU control units
- **cost:** 9 cells / 0 FF · Fmax n/a (combinational) · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 49. `booth` — PASS
- **does:** 4x4 Booth multiplier producing a signed 8-bit product
- **use:** low-power multipliers, DSP
- **cost:** 120 cells / 0 FF · Fmax n/a (combinational) · generator · 0 repair(s)
- **proof:** lint=ok, sim=ok, synth=ok, formal=ok, pnr=ok

### 50. `sar_adc` — FAIL
- **does:** SAR ADC controller: 8-bit successive approximation with sample, compare input, done, and result
- **use:** analog sensing, MCU ADCs
- **why it failed:** behaviour mismatch — tb_sar_adc.v:154: syntax error

