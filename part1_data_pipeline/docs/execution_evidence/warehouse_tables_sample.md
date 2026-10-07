# Warehouse row counts and samples (run 20261007T050603Z)

| table | rows |
|---|---|
| agg_accidents_by_day | 731 |
| agg_accidents_by_hour | 336 |
| agg_accidents_by_road | 331 |
| agg_condition_impact | 57 |
| agg_vehicle_casualty | 73 |
| dim_date | 731 |
| dim_location | 1,071 |
| dim_road | 2,071 |
| dim_severity | 3 |
| dim_time | 24 |
| dim_weather | 2,743 |
| dq_rejected_records | 46 |
| etl_ingestion_log | 130 |
| etl_run_log | 18 |
| fact_accident | 205,173 |
| fact_casualty | 261,236 |
| fact_vehicle | 373,308 |
| mart_location_hotspots | 8,660 |
| ml_accident_features | 205,173 |

## fact_accident (first 5 rows)

| collision_index | date_key | hour_key | location_key | road_key | weather_key | severity_key | collision_datetime | latitude | longitude | lsoa_code | number_of_vehicles | number_of_casualties | n_pedestrian_casualties | n_fatal_casualties | n_serious_casualties | n_child_casualties | involves_pedal_cycle | involves_motorcycle | involves_car | involves_bus | involves_goods_vehicle | mean_driver_age | youngest_driver_age | weather_matched | temperature_c | precipitation_mm | rain_mm | snowfall_cm | wind_speed_kmh | wind_gusts_kmh | cloud_cover_pct | humidity_pct | wmo_weather_code | police_attended_label |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2023170M20483 | 20230304 | 12 | 171 | 1842 | 437 | 3 | 2023-03-04 12:10:00.000000 | 54.565548 | -1.210024 | E01012077 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | nan | nan | 1 | 5.7 | 0.1 | 0.1 | 0.0 | 26.0 | 33.1 | 100.0 | 80.0 | 51.0 | No |
| 2023170M10633 | 20230416 | 20 | 171 | 366 | 301 | 2 | 2023-04-16 20:54:00.000000 | 54.562855 | -1.224443 | E01012026 | 2 | 1 | 0 | 0 | 1 | 0 | 0 | 1 | 1 | 0 | 0 | 27.0 | 27.0 | 1 | 8.2 | 0.0 | 0.0 | 0.0 | 21.5 | 28.4 | 100.0 | 91.0 | 3.0 | Yes |
| 2023170S11103 | 20230627 | 9 | 178 | 1279 | 420 | 3 | 2023-06-27 09:30:00.000000 | 54.561334 | -1.329383 | E01012217 | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 67.0 | 67.0 | 1 | 15.4 | 0.1 | 0.1 | 0.0 | 14.9 | 19.8 | 100.0 | 85.0 | 51.0 | No |
| 2023111343936 | 20230814 | 9 | 104 | 309 | 1752 | 2 | 2023-08-14 09:03:00.000000 | 54.549692 | -1.587814 | E01033481 | 1 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 18.0 | 18.0 | 1 | 13.9 | 0.6 | 0.6 | 0.0 | 6.1 | 12.2 | 100.0 | 90.0 | 53.0 | Yes |
| 2023070054936 | 20230119 | 8 | 925 | 1827 | 518 | 3 | 2023-01-19 08:45:00.000000 | 53.432995 | -2.581866 | E01012468 | 2 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 27.0 | 27.0 | 1 | 0.1 | 0.0 | 0.0 | 0.0 | 10.8 | 22.0 | 16.0 | 88.0 | 0.0 | No |

## dim_road (first 5 rows)

| road_key | first_road_class_label | road_type_label | speed_limit_label | junction_detail_label | junction_control_label |
|---|---|---|---|---|---|
| 1 | A | Dual carriageway | 20 | Junction - unknown type | Authorised person |
| 2 | A | Dual carriageway | 20 | Junction - unknown type | Auto traffic signal |
| 3 | A | Dual carriageway | 20 | Junction - unknown type | Give way or uncontrolled |
| 4 | A | Dual carriageway | 20 | Junction - unknown type | Stop sign |
| 5 | A | Dual carriageway | 20 | Junction - unknown type | Unknown |

## dim_weather (first 5 rows)

| weather_key | weather_conditions_label | road_surface_label | light_conditions_label | temperature_band | precipitation_band | wind_band |
|---|---|---|---|---|---|---|
| 1 | Fine + high winds | Dry | Darkness - lighting unknown | 0-5C | Dry (0 mm/h) | Moderate (20-40 km/h) |
| 2 | Fine + high winds | Dry | Darkness - lighting unknown | 15-20C | Dry (0 mm/h) | Calm/light (<20 km/h) |
| 3 | Fine + high winds | Dry | Darkness - lighting unknown | 15-20C | Dry (0 mm/h) | Moderate (20-40 km/h) |
| 4 | Fine + high winds | Dry | Darkness - lighting unknown | 5-10C | Dry (0 mm/h) | Calm/light (<20 km/h) |
| 5 | Fine + high winds | Dry | Darkness - lighting unknown | 5-10C | Dry (0 mm/h) | Moderate (20-40 km/h) |

## agg_condition_impact (first 5 rows)

| factor | level | accidents | fatal | serious | slight | casualties | ksi_rate |
|---|---|---|---|---|---|---|---|
| Weather condition (police) | Fine + high winds | 1912 | 47 | 527 | 1338 | 2482 | 0.3002 |
| Weather condition (police) | Fine no high winds | 161620 | 2466 | 37809 | 121345 | 206235 | 0.2492 |
| Weather condition (police) | Fog or mist | 807 | 15 | 204 | 588 | 1141 | 0.2714 |
| Weather condition (police) | Other | 6133 | 47 | 1249 | 4837 | 7521 | 0.2113 |
| Weather condition (police) | Raining + high winds | 2349 | 68 | 575 | 1706 | 3123 | 0.2737 |

## mart_location_hotspots (first 5 rows)

| hotspot_id | hotspot_lat | hotspot_lon | accidents | fatal | serious | slight | casualties | ksi_rate | police_force_name |
|---|---|---|---|---|---|---|---|---|---|
| 49.925_-6.325 | 49.925 | -6.325 | 4 | 0 | 3 | 1 | 4 | 0.75 | Devon and Cornwall |
| 49.925_-6.275 | 49.925 | -6.275 | 1 | 0 | 0 | 1 | 2 | 0.0 | Devon and Cornwall |
| 49.975_-5.225 | 49.975 | -5.225 | 3 | 0 | 1 | 2 | 5 | 0.3333 | Devon and Cornwall |
| 50.025_-5.275 | 50.025 | -5.275 | 1 | 0 | 1 | 0 | 1 | 1.0 | Devon and Cornwall |
| 50.025_-5.225 | 50.025 | -5.225 | 9 | 1 | 3 | 5 | 15 | 0.4444 | Devon and Cornwall |

## ml_accident_features (first 5 rows)

| collision_index | collision_datetime | year | month | weekday | hour | latitude | longitude | weather_cell_id | police_force | nation | local_authority_ons_district | urban_or_rural | first_road_class | road_type | speed_limit | junction_detail | junction_control | light_conditions | weather_conditions | road_surface_conditions | special_conditions_at_site | carriageway_hazards | number_of_vehicles | number_of_casualties | temperature_c | precipitation_mm | snowfall_cm | wind_speed_kmh | wind_gusts_kmh | cloud_cover_pct | humidity_pct | weather_matched | involves_pedal_cycle | involves_motorcycle | involves_car | involves_bus | involves_goods_vehicle | pedestrian_involved | mean_driver_age | youngest_driver_age | severity | severity_label |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2023340NN0022 | 2023-01-01 00:10:00.000000 | 2023 | 1 | Sunday | 0 | 52.298654 | -0.708817 | 52.00_-1.00 | Northamptonshire | England | E06000061 | Urban | A | Single carriageway | 30.0 | Junction - unknown type | Give way or uncontrolled | Darkness - lights lit | Other | Wet or damp | None | None | 2 | 1 | 10.3 | 0.1 | 0.0 | 26.2 | 50.4 | 100.0 | 89.0 | 1 | 0 | 0 | 1 | 0 | 1 | 0 | 53.0 | 49.0 | 2 | Serious |
| 2023131258653 | 2023-01-01 00:11:00.000000 | 2023 | 1 | Sunday | 0 | 53.79971 | -1.752399 | 54.00_-2.00 | West Yorkshire | England | E08000032 | Urban | A | Dual carriageway | 30.0 | Unknown (code 16) | Auto traffic signal | Darkness - lights lit | Raining no high winds | Dry | None | None | 1 | 1 | 5.8 | 1.3 | 0.0 | 16.2 | 33.1 | 100.0 | 95.0 | 1 | 0 | 0 | 1 | 0 | 0 | 1 | 21.0 | 21.0 | 3 | Slight |
| 2023471258639 | 2023-01-01 00:20:00.000000 | 2023 | 1 | Sunday | 0 | 50.824653 | -0.136838 | 51.00_0.00 | Sussex | England | E06000043 | Urban | A | Single carriageway | 20.0 | Not at junction | Unknown | Darkness - lights lit | Fine + high winds | Wet or damp | None | None | 1 | 1 | 11.6 | 1.3 | 0.0 | 39.7 | 74.5 | 100.0 | 94.0 | 1 | 0 | 0 | 1 | 0 | 0 | 1 | 25.0 | 25.0 | 3 | Slight |
| 2023101258638 | 2023-01-01 00:21:00.000000 | 2023 | 1 | Sunday | 0 | 55.406183 | -1.681554 | 55.00_-2.00 | Northumbria | England | E06000057 | Rural | A | Dual carriageway | 70.0 | Not at junction | Unknown | Darkness - no lighting | Raining no high winds | Wet or damp | None | None | 1 | 1 | 5.1 | 0.8 | 0.0 | 16.4 | 33.5 | 100.0 | 95.0 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 19.0 | 19.0 | 3 | Slight |
| 2023221273870 | 2023-01-01 00:30:00.000000 | 2023 | 1 | Sunday | 0 | 52.947475 | -2.665233 | 53.00_-3.00 | West Mercia | England | E06000051 | Rural | A | Dual carriageway | 70.0 | Not at junction | Unknown | Darkness - no lighting | Raining no high winds | Flood over 3cm deep | None | None | 1 | 1 | 8.5 | 0.1 | 0.0 | 20.8 | 41.4 | 98.0 | 90.0 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 18.0 | 18.0 | 3 | Slight |
