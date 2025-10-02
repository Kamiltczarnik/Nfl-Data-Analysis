## Data Contracts

### Modeling Table (team-game grain)

- Required keys: `game_id` (str), `season` (int), `week` (int), `team` (str), `opponent` (str), `home` (int), `neutral` (int)
- Market: `spread_close`, `total_close`, `moneyline_close` (float)
- Rolling: `off_epa_play_l3`, `def_epa_play_allowed_l3`, `early_down_pass_epa_l3` (float)
- Strategy: `proe_l5`, `early_down_pass_rate_l5` (float)
- QB: `qb_epa_cpoe_l6`, `adot_l5` (float)
- Trenches: `pressure_allowed_l5`, `pressure_created_l5`, `sack_rate_oe_l5` (float)
- Drives: `points_per_drive_l5`, `scores_per_drive_l5`, `st_start_fp_l5` (float)
- Situational: `penalty_rate_l5`, `rest_days`, `short_week`, `primetime`, `roof`, `surface`, `wx_*` (mixed)
- Injuries: `inj_out_count`, `inj_q_count`, `ol_continuity_index` (mixed)
- Training only: `label_win` (int)

### Starters Table (weekly)

- Keys: `season` (int), `week` (int), `team` (str), `position` (str), `player_id` (str)
- Fields: `is_starter` (bool), `source` (enum: depth_chart|snaps|override), `as_of` (timestamp)

### Window Metadata

- Stored with modeling outputs or as sidecar JSON: `window_type` (L3|L5|EWMA), `ewma_alpha` (float), `history_weeks_available` (int), `sos_adjusted` (bool)

### Schedules with markets

- Must include: `game_id`, `season`, `week`, `home_team`, `away_team`, `spread_line`, `total_line`, `moneyline`

### PBP minimal columns

- Include EPA (`epa`), WP (`wp`), completion probability (`cp`) and standard play context fields used for PROE.


