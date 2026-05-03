# Packet Format

RangeIQ currently supports two compact telemetry packet styles for ranch stations.

## Compact JSON

```json
{"n":"NP1","t":91.4,"h":22,"p":1007,"r":0.0,"s10":13.2,"s30":18.5,"w":73,"b":3.91}
```

## Pipe-Delimited Text

```text
NP1|91.4|22|1007|0.00|13.2|18.5|73|3.91
```

## Compact key mapping

- `n` = `station_id`
- `t` = `air_temp_f`
- `h` = `humidity_pct`
- `p` = `pressure_hpa`
- `r` = `rainfall_in`
- `s10` = `soil_moisture_10cm`
- `s30` = `soil_moisture_30cm`
- `s60` = `soil_moisture_60cm`
- `st` = `soil_temp_f`
- `w` = `water_tank_pct`
- `tr` = `trough_level_pct`
- `b` = `battery_voltage`
- `sv` = `solar_voltage`
- `rs` = `rssi`
- `sn` = `snr`
- `hp` = `hop_count`

The parser expands these short keys into normalized RangeIQ sensor-reading fields.
