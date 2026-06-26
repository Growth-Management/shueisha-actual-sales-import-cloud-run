# Provider mapping for payload v1.0

## Apple

- `provider`: `apple`
- Drive folder: `https://drive.google.com/drive/folders/1MSyU3QZZszTqZO55z2iVe_3JcMvwWbDu`
- staging dataset: `ice-sh.ice_sh_source_staging`
- staging table: `sh_actual_apple_data_stg`
- production dataset: `ice-sh.ice_sh_source`
- production table: `sh_actual_apple_data`
- delivery types: `ICE納品`, `J+分`

Apple files with `ICE納品` and `J+分` share the same schema and are loaded into the Apple production table. If both exist in the same `sales_yyyymm`, rebuild the month as one target group.

## Google Play

- `provider`: `googleplay`
- Drive folder: `https://drive.google.com/drive/folders/16_rLnV3HWoQJzbGmdXEN1Mg16vCAsW4l`
- staging dataset: `ice-sh.ice_sh_source_staging`
- staging table: `sh_actual_googleplay_data_stg`
- production dataset: `ice-sh.ice_sh_source`
- production table: `sh_actual_googleplay_data`
- delivery type: `monthly_split`

Google Play split files such as `(その1)` are handled as one active file group per `sales_yyyymm`.

## Manifest

- table: `ice-sh.ice_sh_process.drive_sales_import_manifest`
- file identity should be based on checksum and manifest state when available.
- file name alone is not enough to determine duplicate or revision status.
