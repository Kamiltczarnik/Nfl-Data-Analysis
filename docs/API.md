# NFL Data Analysis API Documentation

## Overview

The NFL Data Analysis API provides access to NFL game data, player statistics, and prediction capabilities. This is a FastAPI-based REST API that serves as the interface between data sources and client applications.

**Version**: 1.0.0  
**Base URL**: `http://localhost:8000`  
**Documentation**: `http://localhost:8000/docs` (Swagger UI)  
**ReDoc**: `http://localhost:8000/redoc` (Alternative documentation)

## Authentication

Currently, the API does not require authentication. In production, implement appropriate authentication mechanisms.

## Base Endpoints

### Root Endpoint
- **GET** `/` - API information and status

### API Information
- **GET** `/api/v1/info` - Detailed API information including available data sources and endpoints

## Health Check Endpoints

### Basic Health Check
- **GET** `/api/v1/health` - Basic health status
- **GET** `/api/v1/health/detailed` - Detailed health check with data availability
- **GET** `/api/v1/health/data` - Data-specific health check
- **GET** `/api/v1/health/ready` - Readiness check for deployment

## Game Data Endpoints

### Schedules
- **GET** `/api/v1/games/schedules` - NFL game schedules with market data
  - Query Parameters:
    - `season` (optional): NFL season year
    - `week` (optional): Specific week
    - `limit` (default: 100): Maximum records to return

### Play-by-Play Data
- **GET** `/api/v1/games/pbp` - Play-by-play data with EPA/WP/cp
  - Query Parameters:
    - `season` (optional): NFL season year
    - `week` (optional): Specific week
    - `game_id` (optional): Specific game ID
    - `limit` (default: 1000): Maximum records to return

### Weekly Statistics
- **GET** `/api/v1/games/weekly` - Weekly player statistics
  - Query Parameters:
    - `season` (optional): NFL season year
    - `week` (optional): Specific week
    - `position` (optional): Player position
    - `limit` (default: 500): Maximum records to return

### Starters
- **GET** `/api/v1/games/starters` - Weekly starter tables
  - Query Parameters:
    - `season` (optional): NFL season year
    - `week` (optional): Specific week
    - `team` (optional): Team abbreviation
    - `position` (optional): Player position
    - `limit` (default: 200): Maximum records to return

### Injuries
- **GET** `/api/v1/games/injuries` - Injury reports
  - Query Parameters:
    - `season` (optional): NFL season year
    - `week` (optional): Specific week
    - `team` (optional): Team abbreviation
    - `limit` (default: 200): Maximum records to return

### Snap Counts
- **GET** `/api/v1/games/snap-counts` - Player snap counts
  - Query Parameters:
    - `season` (optional): NFL season year
    - `week` (optional): Specific week
    - `team` (optional): Team abbreviation
    - `limit` (default: 500): Maximum records to return

### Depth Charts
- **GET** `/api/v1/games/depth-charts` - Team depth charts
  - Query Parameters:
    - `season` (optional): NFL season year
    - `week` (optional): Specific week
    - `team` (optional): Team abbreviation
    - `limit` (default: 500): Maximum records to return

### Rosters
- **GET** `/api/v1/games/rosters` - Team rosters
  - Query Parameters:
    - `season` (optional): NFL season year
    - `week` (optional): Specific week
    - `team` (optional): Team abbreviation
    - `limit` (default: 200): Maximum records to return

## Prediction Endpoints

### Game Prediction
- **POST** `/api/v1/predict/game` - Predict game outcome
  - Request Body:
    ```json
    {
      "season": 2024,
      "week": 1,
      "home_team": "KC",
      "away_team": "BUF",
      "spread_line": -3.5,
      "total_line": 47.5,
      "moneyline": -180
    }
    ```
  - Response:
    ```json
    {
      "game_id": "2024_01_KC_BUF",
      "season": 2024,
      "week": 1,
      "home_team": "KC",
      "away_team": "BUF",
      "home_win_probability": 0.620,
      "away_win_probability": 0.380,
      "spread_line": -3.5,
      "total_line": 47.5,
      "moneyline": -180,
      "prediction_timestamp": "2024-01-01T12:00:00Z",
      "model_version": "scaffold"
    }
    ```

### Feature Extraction
- **POST** `/api/v1/predict/features` - Get features for prediction
  - Request Body:
    ```json
    {
      "season": 2024,
      "week": 1,
      "team": "KC",
      "opponent": "BUF"
    }
    ```
  - Response:
    ```json
    {
      "season": 2024,
      "week": 1,
      "team": "KC",
      "opponent": "BUF",
      "features": {
        "spread_close": -3.5,
        "total_close": 47.5,
        "moneyline_close": -180,
        "off_epa_play_l3": 0.12,
        "def_epa_play_allowed_l3": -0.08,
        "early_down_pass_epa_l3": 0.18,
        "proe_l5": 0.02,
        "early_down_pass_rate_l5": 0.58,
        "qb_epa_cpoe_l6": 0.25,
        "adot_l5": 8.2,
        "pressure_allowed_l5": 0.22,
        "pressure_created_l5": 0.28,
        "sack_rate_oe_l5": 0.05,
        "points_per_drive_l5": 2.1,
        "scores_per_drive_l5": 0.35,
        "st_start_fp_l5": 0.12,
        "penalty_rate_l5": 0.08,
        "rest_days": 7,
        "short_week": 0,
        "primetime": 0,
        "roof": "outdoor",
        "surface": "grass",
        "inj_out_count": 2,
        "inj_q_count": 3,
        "ol_continuity_index": 0.85
      },
      "feature_timestamp": "2024-01-01T12:00:00Z"
    }
    ```

### Available Models
- **GET** `/api/v1/predict/models` - List available prediction models
  - Response:
    ```json
    {
      "models": [
        {
          "name": "baseline",
          "type": "logistic_regression",
          "version": "1.0.0",
          "accuracy": 0.625,
          "log_loss": 0.68,
          "roc_auc": 0.67,
          "features": 42,
          "last_trained": "2024-01-01T12:00:00Z"
        },
        {
          "name": "neural_network",
          "type": "multi_branch_deep_network",
          "version": "1.0.0",
          "accuracy": 0.675,
          "log_loss": 0.62,
          "roc_auc": 0.72,
          "features": 42,
          "architecture": "rolling_branch(64→32→16) + situational_branch(16→8) + combined(32→16→1)",
          "last_trained": "2024-01-01T12:00:00Z"
        }
      ]
    }
    ```

### Feature Schema
- **GET** `/api/v1/predict/features/schema` - Get feature schema for model inputs

### Calibration Information
- **GET** `/api/v1/predict/calibration` - Get model calibration information

## Data Models

### Schedules Data
```json
{
  "game_id": "2024_01_KC_BUF",
  "season": 2024,
  "week": 1,
  "home_team": "KC",
  "away_team": "BUF",
  "spread_line": -3.5,
  "total_line": 47.5,
  "moneyline": -180,
  "home_score": 24,
  "away_score": 21,
  "result": 1
}
```

### Play-by-Play Data (Enhanced with Matchup Information)
```json
{
  "game_id": "2024_01_KC_BUF",
  "play_id": 1,
  "posteam": "KC",
  "defteam": "BUF",
  "epa": 0.5,
  "wp": 0.52,
  "cp": 0.65,
  "down": 1,
  "distance": 10,
  "yardline_100": 75,
  "score_differential": 0,
  "game_seconds_remaining": 3600,
  "posteam_score": 0,
  "defteam_score": 0,
  
  "passer_player_id": "00-0019596",
  "passer_player_name": "Patrick Mahomes",
  "receiver_player_id": "00-0033873",
  "receiver_player_name": "Travis Kelce",
  "rusher_player_id": null,
  "rusher_player_name": null,
  
  "sack_player_id": null,
  "sack_player_name": null,
  "qb_hit_1_player_id": null,
  "qb_hit_1_player_name": null,
  "interception_player_id": null,
  "interception_player_name": null,
  
  "air_yards": 8.5,
  "pass_location": "middle",
  "yards_gained": 12,
  "pass_touchdown": 0,
  "rush_touchdown": 0,
  "interception": 0,
  "sack": 0,
  "qb_hit": 0
}
```

### Weekly Statistics
```json
{
  "player_id": "00-0019596",
  "player_name": "Patrick Mahomes",
  "team": "KC",
  "season": 2024,
  "week": 1,
  "position": "QB",
  "passing_yards": 258,
  "passing_tds": 2,
  "passing_interceptions": 0,
  "passing_epa": 8.5,
  "passing_cpoe": 0.12
}
```

### Starters Data
```json
{
  "season": 2024,
  "week": 1,
  "team": "KC",
  "position": "QB",
  "player_id": "00-0019596",
  "is_starter": true,
  "source": "depth_chart",
  "as_of": "2024-01-01T12:00:00Z"
}
```

### Injuries Data
```json
{
  "season": 2024,
  "week": 1,
  "team": "KC",
  "gsis_id": "00-0019596",
  "position": "QB",
  "full_name": "Patrick Mahomes",
  "report_status": "probable",
  "practice_status": "full"
}
```

## Error Handling

The API uses standard HTTP status codes:

- **200**: Success
- **400**: Bad Request (invalid parameters)
- **404**: Not Found (resource doesn't exist)
- **500**: Internal Server Error

Error responses include a JSON object with error details:

```json
{
  "detail": "Error description",
  "error": "Detailed error message"
}
```

## Rate Limiting

Currently, no rate limiting is implemented. In production, implement appropriate rate limiting based on usage patterns.

## CORS

CORS is enabled for all origins. In production, configure CORS appropriately for your domain.

## Data Sources

The API provides access to the following data sources:

1. **Schedules**: NFL game schedules with market data (spread, total, moneyline)
2. **Play-by-Play**: Detailed play data with EPA, WP, and completion probability
3. **Weekly Stats**: Player performance statistics by week
4. **Rosters**: Team roster information
5. **Injuries**: Player injury reports and status
6. **Snap Counts**: Player snap count data
7. **Depth Charts**: Team depth chart information
8. **Starters**: Weekly starter determination tables
9. **Players**: Player information and ID mapping
10. **Teams**: Team information and ID mapping

## Feature Engineering

The API supports feature extraction for machine learning models:

### Market Features
- `spread_close`: Closing spread line
- `total_close`: Closing total line
- `moneyline_close`: Closing moneyline

### Rolling Features
- `off_epa_play_l3`: Offensive EPA per play (last 3 games)
- `def_epa_play_allowed_l3`: Defensive EPA allowed per play (last 3 games)
- `early_down_pass_epa_l3`: Early down pass EPA (last 3 games)

### Strategy Features
- `proe_l5`: Pass rate over expected (last 5 games)
- `early_down_pass_rate_l5`: Early down pass rate (last 5 games)

### QB Features
- `qb_epa_cpoe_l6`: QB EPA + CPOE (last 6 games)
- `adot_l5`: Average depth of target (last 5 games)

### Trenches Features
- `pressure_allowed_l5`: Pressure allowed rate (last 5 games)
- `pressure_created_l5`: Pressure created rate (last 5 games)
- `sack_rate_oe_l5`: Sack rate over expected (last 5 games)

### Drives Features
- `points_per_drive_l5`: Points per drive (last 5 games)
- `scores_per_drive_l5`: Scores per drive (last 5 games)
- `st_start_fp_l5`: Starting field position (last 5 games)

### Situational Features
- `penalty_rate_l5`: Penalty rate (last 5 games)
- `rest_days`: Days of rest
- `short_week`: Short week indicator
- `primetime`: Primetime game indicator
- `roof`: Stadium roof type
- `surface`: Playing surface type

### Injury Features
- `inj_out_count`: Players out due to injury
- `inj_q_count`: Players questionable
- `ol_continuity_index`: Offensive line continuity

## Model Information

### Available Models

1. **Baseline Logistic**: Simple logistic regression model
2. **GBM Ensemble**: Gradient boosting ensemble model
3. **Stacked Ensemble**: Stacked ensemble of multiple models

### Calibration

Models are calibrated using:
- **Platt Scaling**: For logistic regression models
- **Isotonic Regression**: For ensemble models
- **Ensemble Calibration**: For stacked models

## Usage Examples

### Get Game Schedules
```bash
curl "http://localhost:8000/api/v1/games/schedules?season=2024&week=1&limit=10"
```

### Get Play-by-Play Data
```bash
curl "http://localhost:8000/api/v1/games/pbp?season=2024&week=1&game_id=2024_01_KC_BUF&limit=100"
```

### Predict Game Outcome
```bash
curl -X POST "http://localhost:8000/api/v1/predict/game" \
  -H "Content-Type: application/json" \
  -d '{
    "season": 2024,
    "week": 1,
    "home_team": "KC",
    "away_team": "BUF",
    "spread_line": -3.5,
    "total_line": 47.5,
    "moneyline": -180
  }'
```

### Get Team Features
```bash
curl -X POST "http://localhost:8000/api/v1/predict/features" \
  -H "Content-Type: application/json" \
  -d '{
    "season": 2024,
    "week": 1,
    "team": "KC",
    "opponent": "BUF"
  }'
```

## Neural Network Models

### Multi-Branch Deep Network Architecture

The neural network model uses a sophisticated multi-branch architecture optimized for NFL predictions:

#### Architecture Components

1. **Rolling Features Branch** (36 features)
   - Input: L3/L5/L6/EWMA windows for EPA and success rates
   - Layers: Dense(64) → BatchNorm → Dropout(0.3) → Dense(32) → BatchNorm → Dropout(0.2) → Dense(16)
   - Purpose: Capture complex time-series patterns and team performance trends

2. **Situational Features Branch** (6 features)
   - Input: Home field, rest days, spread, opponent metrics, strength of schedule
   - Layers: Dense(16) → BatchNorm → Dropout(0.2) → Dense(8)
   - Purpose: Process contextual and market information

3. **Combined Processing**
   - Input: Concatenated outputs from both branches (24 features)
   - Layers: Dense(32) → BatchNorm → Dropout(0.3) → Dense(16) → BatchNorm → Dropout(0.2) → Dense(1)
   - Output: Sigmoid activation for win probability
   - Purpose: Learn complex interactions between rolling and situational features

#### Performance Targets

- **Accuracy**: 65-70% (vs 60-65% logistic regression baseline)
- **Log-Loss**: <0.65 (vs 0.68-0.70 baseline)
- **ROC-AUC**: >0.70 (vs 0.65-0.67 baseline)
- **Calibration**: Better probability estimates than linear models

#### Key Advantages

1. **Non-Linear Relationships**: Captures complex feature interactions
2. **Automatic Feature Learning**: Discovers important patterns automatically
3. **Contextual Adaptation**: Different strategies for different game types
4. **Rich Interactions**: Learns interactions between all 42 features
5. **Temporal Patterns**: Better understanding of team performance trends

## Development

### Running the API

```bash
# Install dependencies
pip install -r requirements.txt

# Run the API
python -m uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000
```

### Testing

```bash
# Run tests
pytest tests/

# Test specific endpoint
curl "http://localhost:8000/api/v1/health"
```

## Production Considerations

1. **Authentication**: Implement proper authentication mechanisms
2. **Rate Limiting**: Add rate limiting based on usage patterns
3. **CORS**: Configure CORS for production domains
4. **Logging**: Implement comprehensive logging and monitoring
5. **Error Handling**: Enhance error handling and user feedback
6. **Caching**: Implement caching for frequently accessed data
7. **Security**: Add security headers and input validation
8. **Documentation**: Keep API documentation up to date
9. **Versioning**: Implement API versioning strategy
10. **Monitoring**: Add health checks and performance monitoring

## Support

For questions or issues with the API, please refer to the project documentation or contact the development team.