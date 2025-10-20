"""
Matchup feature validation script.

Recomputes ground-truth matchup metrics directly from play-by-play data and
compares them against the outputs from MatchupFeatureCalculator for specified
season/week pairs. Emits a structured report and pass/fail status per metric.
"""

import argparse
import logging
from typing import Dict, Any, List

import pandas as pd

from src.data.readers import PBPReader
from src.features.matchup import MatchupFeatureCalculator

logger = logging.getLogger(__name__)


def compute_ground_truth_matchups(season: int, week: int) -> pd.DataFrame:
    """
    Recompute the three MVP matchup metrics directly from PBP with the same logic as
    MatchupFeatureCalculator, strictly using weeks < target week.
    Returns one row per team with columns:
      ['season','week','team','wr_vs_cb_target_share_l3','ol_vs_dl_pressure_rate_l3','qb_vs_secondary_completion_rate_l3']
    """
    pbp_reader = PBPReader()
    pbp = pbp_reader.load_pbp(season, week=None, use_cache=True, mvp_only=True)
    pbp = pbp[pbp['week'] < week].copy()

    if pbp.empty:
        return pd.DataFrame(columns=[
            'season', 'week', 'team',
            'wr_vs_cb_target_share_l3',
            'ol_vs_dl_pressure_rate_l3',
            'qb_vs_secondary_completion_rate_l3'
        ])

    pbp['is_pass'] = pbp['pass'] == 1 if 'pass' in pbp.columns else False
    pbp['is_dropback'] = pbp['is_pass'] | pbp.get('qb_scramble', pd.Series(False, index=pbp.index)).astype(bool)

    team_game = (
        pbp.groupby(['posteam', 'season', 'week', 'game_id'], dropna=False)
           .agg(
               targets=('receiver_player_id', lambda s: s.notna().sum()),
               sacks=('sack', lambda s: s.fillna(0).astype(int).sum() if 'sack' in pbp.columns else 0),
               qb_hits=('qb_hit', lambda s: s.fillna(0).astype(int).sum() if 'qb_hit' in pbp.columns else 0),
               dropbacks=('is_dropback', 'sum'),
               mean_cp=('cp', 'mean')
           )
           .reset_index()
           .rename(columns={'posteam': 'team'})
    )

    recv_counts = (
        pbp[pbp['receiver_player_id'].notna()]
        .groupby(['posteam', 'season', 'week', 'game_id', 'receiver_player_id'], dropna=False)
        .size()
        .reset_index(name='receiver_targets')
        .rename(columns={'posteam': 'team'})
    )

    top_recv = (
        recv_counts.sort_values(['team', 'season', 'week', 'game_id', 'receiver_targets'], ascending=[True, True, True, True, False])
        .groupby(['team', 'season', 'week', 'game_id'], as_index=False, dropna=False)
        .first()[['team', 'season', 'week', 'game_id', 'receiver_targets']]
        .rename(columns={'receiver_targets': 'top_receiver_targets'})
    )

    team_game = team_game.merge(top_recv, on=['team', 'season', 'week', 'game_id'], how='left')
    team_game['wr_target_share'] = team_game.apply(
        lambda r: (r['top_receiver_targets'] / r['targets']) if r['targets'] and r['targets'] > 0 else pd.NA,
        axis=1
    )

    team_game = team_game.sort_values(['team', 'season', 'week'])

    def rolling_mean(series: pd.Series, window: int) -> pd.Series:
        return series.rolling(window=window, min_periods=1).mean()

    l3 = (
        team_game
        .groupby('team', group_keys=False)
        .apply(lambda g: pd.DataFrame({
            'season': g['season'],
            'week': g['week'],
            'game_id': g['game_id'],
            'wr_vs_cb_target_share_l3': rolling_mean(g['wr_target_share'], 3),
            'ol_vs_dl_pressure_rate_l3': rolling_mean((g['sacks'] + g['qb_hits']) / g['dropbacks'].where(g['dropbacks'] > 0, pd.NA), 3),
            'qb_vs_secondary_completion_rate_l3': rolling_mean(g['mean_cp'], 3)
        }).assign(team=g['team'].values))
        .reset_index(drop=True)
    )

    latest = (
        l3.sort_values(['team', 'season', 'week'])
          .groupby('team', as_index=False, dropna=False)
          .tail(1)
          .reset_index(drop=True)
    )

    latest = latest.drop(columns=['season', 'week', 'game_id'], errors='ignore')
    latest['season'] = season
    latest['week'] = week

    cols = ['season', 'week', 'team',
            'wr_vs_cb_target_share_l3',
            'ol_vs_dl_pressure_rate_l3',
            'qb_vs_secondary_completion_rate_l3']
    return latest[cols]


def compare_frames(gt: pd.DataFrame, calc: pd.DataFrame, atol: float = 1e-6, rtol: float = 1e-3) -> pd.DataFrame:
    """
    Compare ground truth vs calculated metrics for matching teams.
    Returns a DataFrame with per-team deltas and pass/fail flags.
    """
    merged = gt.merge(calc, on=['season', 'week', 'team'], suffixes=('_gt', '_calc'), how='inner')

    for col in [
        'wr_vs_cb_target_share_l3',
        'ol_vs_dl_pressure_rate_l3',
        'qb_vs_secondary_completion_rate_l3'
    ]:
        gtc = f"{col}_gt"
        cc = f"{col}_calc"
        merged[f'{col}_delta'] = (merged[cc] - merged[gtc]).abs()
        merged[f'{col}_pass'] = (merged[f'{col}_delta'] <= (atol + rtol * merged[gtc].abs().fillna(0)))

    merged['all_pass'] = merged[[
        'wr_vs_cb_target_share_l3_pass',
        'ol_vs_dl_pressure_rate_l3_pass',
        'qb_vs_secondary_completion_rate_l3_pass'
    ]].all(axis=1)

    return merged


def validate_matchups(season: int, week: int) -> Dict[str, Any]:
    calc = MatchupFeatureCalculator().calculate_matchup_features(season, week)
    gt = compute_ground_truth_matchups(season, week)

    comp = compare_frames(gt, calc)
    totals = {
        'teams_compared': len(comp),
        'all_pass_count': int(comp['all_pass'].sum()),
        'all_pass_rate': float((comp['all_pass'].mean() if len(comp) else 0.0))
    }

    # Aggregate per-metric pass rates
    for metric in [
        'wr_vs_cb_target_share_l3',
        'ol_vs_dl_pressure_rate_l3',
        'qb_vs_secondary_completion_rate_l3'
    ]:
        totals[f'{metric}_pass_rate'] = float(comp[f'{metric}_pass'].mean() if len(comp) else 0.0)

    return {
        'season': season,
        'week': week,
        'summary': totals,
        'details': comp
    }


def main():
    parser = argparse.ArgumentParser(description='Validate matchup features against ground truth PBP aggregates')
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--weeks', type=int, nargs='+', required=True, help='One or more target weeks to validate')
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    reports: List[Dict[str, Any]] = []
    for wk in args.weeks:
        report = validate_matchups(args.season, wk)
        reports.append(report)

        summary = report['summary']
        print(f"Season {args.season} Week {wk}: compared {summary['teams_compared']} teams | all-pass {summary['all_pass_rate']:.1%}")
        print(f"  wr_vs_cb_target_share_l3 pass: {summary['wr_vs_cb_target_share_l3_pass_rate']:.1%}")
        print(f"  ol_vs_dl_pressure_rate_l3 pass: {summary['ol_vs_dl_pressure_rate_l3_pass_rate']:.1%}")
        print(f"  qb_vs_secondary_completion_rate_l3 pass: {summary['qb_vs_secondary_completion_rate_l3_pass_rate']:.1%}")

    # Overall result: require 100% pass for strict correctness
    overall_pass = all(r['summary']['all_pass_rate'] == 1.0 for r in reports if r['summary']['teams_compared'] > 0)
    exit(0 if overall_pass else 1)


if __name__ == '__main__':
    main()



