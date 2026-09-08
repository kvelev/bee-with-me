# Bee Protocol — wire format reference

The authoritative description of what the RescuerBee devices and the USB gateway actually
send. Verified against `backend/hardware_reader/parser.py`; every claim here is pinned by a
test in `backend/tests/test_parser.py`.

> If frames are being rejected, read the **CRC** section first. Both of its details are
> easy to get wrong, and getting either wrong means *every* frame fails and is silently
> discarded with nothing on the map.

## Hardware topology

One USB gateway plugged into the server receives radio transmissions from all field devices
over LoRaWAN. The server reads that single device and demultiplexes by `DevSN`. There is no
direct connection per field device.

The active reader is `hardware_reader/hid_reader.py`, which polls the gateway as a USB HID
device at 50 Hz and reassembles frames across 64-byte packets. `hardware_reader/reader.py`
is the serial-port variant; its `run()` loop is deliberately commented out and only its
`_handle_bee` / `_handle_repeater` / `_dsn` helpers are live, imported by the HID reader.

## Frame envelope

```text
##<payload>@<CRC>\r\n
```

## CRC

**CRC-16/CCITT-FALSE** — polynomial `0x1021`, init `0xFFFF`, no input/output reflection, no
final XOR.

Two details that are easy to get wrong:

1. It is computed over **`##<payload>`** — the `##` marker is included.
2. It goes on the wire as a **decimal** integer, not hex.

```text
##1,24@44868          ← correct: decimal 44868
##1,24@AF44           ← rejected: hex
```

The algorithm identity is pinned by CCITT-FALSE's published check value:
`crc16(b'123456789') == 0x29B1`.

## Cmd=30 — RescuerBee location frame

25 comma-separated fields.

```text
##30,MsgId,DevSN,HWVer,SWVer,Hour,Min,Sec,Day,Mon,Year,GNSSStatus,Lat,Lng,Speed,Course,
    Satellites,Altitude,Flags,BattVol,CurrMothRxBeeRSSI,CurrMothRxBeeSNR,
    PrevBeeRxMothRSSI,PrevBeeRxMothSNR,EventID@<CRC>
```

| Idx | Field | Type | Notes |
| --- | --- | --- | --- |
| 0 | Cmd | int | `30` |
| 1 | MsgId | int | Rolling 0–255; echoed in the Cmd=1 ACK |
| 2 | DevSN | int | Must exist in the `devices` table or the frame is discarded |
| 3–4 | HWVer / SWVer | int | Parsed past, not stored |
| 5–10 | Hour, Min, Sec, Day, Mon, Year | int | UTC per the device's GNSS clock. 2-digit year accepted (`25` → 2025) |
| 11 | GNSSStatus | char | `A` = valid fix, `V` = no fix. See below |
| 12–13 | Lat / Lng | float | Decimal degrees |
| 14 | Speed | float | Knots |
| 15 | Course | int | Heading, degrees |
| 16 | Satellites | int | GNSS satellite count |
| 17 | Altitude | int | Metres |
| 18 | Flags | int | **Bit 0 (`0x01`) = repeater mode; Bit 1 (`0x02`) = SOS active** |
| 19 | BattVol | float | Volts, e.g. `3.85` |
| 20–23 | RSSI / SNR ×4 | int | Link quality both directions. **Parsed past and discarded — not captured yet** |
| 24 | EventID | int | Drives the HID reader's duplicate filter (15 s window) |

A frame with fewer than 25 fields is rejected whole.

Example:

```text
##30,2,1235,1,4,20,50,5,8,12,2024,A,42.14384090,24.74956150,5,137,12,200,0,3.7,-97,7,-101,5,884@<CRC>
```

→ device 1235, 2024-12-08 20:50:05 UTC, MGRS `35TLG1403968198`, 3.7 V, no SOS.

### GNSSStatus = V (no fix)

The frame **is** recorded, flagged `location_events.gnss_valid = FALSE` and anchored to the
device's last known fix — it still proves the device is powered and in radio contact, which
is very different information from silence. It deliberately does **not** extend the trail
(it proves contact, not movement). If there is no earlier fix to anchor to, it is dropped.

### Cyrillic `А` — known gap

`_parse_bee` accepts Cyrillic `А` (U+0410) as well as ASCII `A`, but **that branch is
currently unreachable**. Both readers do `.decode('ascii', errors='replace')` on the bytes
off the wire, which turns the Cyrillic byte(s) into U+FFFD before the parser is ever called.
A device emitting Cyrillic `А` therefore reads as "no fix" on every frame.

Fixing it means changing the decode in the readers *and* the matching encode in
`_strip_and_verify` to something byte-preserving such as latin-1 — a change on the hot path
that should be made against real hardware, not guessed at.

## Cmd=20 — RescuerRepeater heartbeat

11 comma-separated fields.

```text
##20,MsgId,DevSN,HWVer,SWVer,BattVol,CurrMRxDevRSSI,CurrMRxDevSNR,
    PrevDevRxMRSSI,PrevDevRxMSNR,EventID@<CRC>
```

| Idx | Field | Notes |
| --- | --- | --- |
| 0 | Cmd | `20` |
| 1 | MsgId | Rolling counter |
| 2 | DevSN | Must be registered |
| 3–4 | HWVer / SWVer | Parsed past |
| 5 | BattVol | Volts |
| 6–9 | RSSI / SNR ×4 | Parsed past and discarded |
| 10 | EventID | Duplicate filter |

No position. Stored in `repeater_events` — which no endpoint currently reads, so repeater
health is invisible in the UI. A repeater whose battery dies takes a coverage area dark and
makes every rescuer behind it appear to go silent at once.

## Cmd=1 — ACK (server → device)

```text
##1,MsgId@<CRC>\r\n
```

Built by `make_confirm()` and sent **after** a frame has been handled successfully, so a
frame that fails to persist is left unacknowledged and may be retransmitted. That gives an
at-least-once property worth preserving if this code is touched.

## Before a device appears on the map

An admin must register it in the Devices page with the matching `DevSN`. Until that row
exists the reader logs:

```text
Unknown or inactive device dev_sn=<N> — register it first
```

Grep the backend log for that line first when a device is not showing up.

Note that the Devices page's green **Active** badge reflects only `devices.is_active` —
whether the row is enabled. It says nothing about whether that `DevSN` exists in the real
world or has ever transmitted. A typo'd serial number looks identical to a real one.

## Debugging checklist

| Symptom | Where to look |
| --- | --- |
| No frames at all | `GET /api/serial/status` — is the gateway connected, is `frames_received` climbing? |
| Frames arriving, nothing on the map | Backend log for `Unknown or inactive device dev_sn=` — the registered `DevSN` doesn't match the hardware |
| Every frame rejected | CRC: marker inclusion and decimal encoding (see above). The HID reader logs `HID frame extracted:` with the raw frame |
| Positions stop updating but device is fine | Radio range. RSSI would show this coming — it isn't captured yet |
| Tracker greys out / shows an age | Working as intended: freshness is judged on server receive time, see `frontend/src/lib/freshness.js` |
