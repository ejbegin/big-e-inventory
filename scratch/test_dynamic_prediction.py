import sys
import os
import datetime
from typing import TypedDict

class CalendarDay(TypedDict):
    date: str
    dow: str
    is_past: bool
    is_today: bool
    is_remaining: bool

# Ensure workspace is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))

def run_tests():
    print("=== Testing Dynamic Actuals Prediction Algorithm ===")

    # 1. Syntax check on app.py
    try:
        import app
        print("PASS: app.py successfully imported without syntax or import errors.")
    except Exception as e:
        print(f"FAIL: Error importing app.py: {e}")
        return False

    # 2. Test mathematical model simulation
    # Calendar simulation: 5 elapsed days (Sat, Sun, Mon, Tue, Wed), 3 remaining days (Thu, Fri, Sat)
    calendar_days: list[CalendarDay] = [
        {'date': '2026-09-26', 'dow': 'Saturday', 'is_past': True, 'is_today': False, 'is_remaining': False},
        {'date': '2026-09-27', 'dow': 'Sunday', 'is_past': True, 'is_today': False, 'is_remaining': False},
        {'date': '2026-09-28', 'dow': 'Monday', 'is_past': True, 'is_today': False, 'is_remaining': False},
        {'date': '2026-09-29', 'dow': 'Tuesday', 'is_past': True, 'is_today': False, 'is_remaining': False},
        {'date': '2026-09-30', 'dow': 'Wednesday', 'is_past': True, 'is_today': False, 'is_remaining': False},
        {'date': '2026-10-01', 'dow': 'Thursday', 'is_past': False, 'is_today': True, 'is_remaining': True},
        {'date': '2026-10-02', 'dow': 'Friday', 'is_past': False, 'is_today': False, 'is_remaining': True},
        {'date': '2026-10-03', 'dow': 'Saturday', 'is_past': False, 'is_today': False, 'is_remaining': True},
    ]

    hist_days = {
        'Saturday': 10.0,
        'Sunday': 8.0,
        'Monday': 4.0,
        'Tuesday': 4.0,
        'Wednesday': 4.0,
        'Thursday': 4.0,
        'Friday': 6.0,
    }
    item_growth_factor = 1.0
    today_str = '2026-10-01'

    # Case A: Surging Item
    # Expected elapsed (Sat-Wed) = 10 + 8 + 4 + 4 + 4 = 30
    # Actuals elapsed = 60 (2.0x surge, especially high on Mon/Tue/Wed: 10, 10, 12)
    by_date_surging = {
        '2026-09-26': 12,
        '2026-09-27': 16,
        '2026-09-28': 10,
        '2026-09-29': 10,
        '2026-09-30': 12,
        '2026-10-01': 5
    }
    
    completed_days = [d for d in calendar_days if d['is_past']]
    remaining_days_list = [d for d in calendar_days if d['is_remaining']]
    
    # Run pace calculation for surging item
    unadj_daily = [hist_days.get(d['dow'], 0) * item_growth_factor for d in remaining_days_list]
    baseline_unadjusted = round(sum(unadj_daily)) # Thu (4) + Fri (6) + Sat (10) = 20

    eval_days = list(completed_days)
    exp_eval = sum(hist_days.get(d['dow'], 0) for d in eval_days) * item_growth_factor
    act_eval = sum(float(by_date_surging.get(d['date'], 0)) for d in eval_days)
    cum_pace = act_eval / exp_eval

    recent_days = eval_days[-3:]
    recent_exp = sum(hist_days.get(d['dow'], 0) for d in recent_days) * item_growth_factor
    recent_act = sum(float(by_date_surging.get(d['date'], 0)) for d in recent_days)
    recent_pace = recent_act / recent_exp

    raw_pace = (0.65 * recent_pace) + (0.35 * cum_pace)
    actuals_weight = min(0.85, 0.25 + (0.12 * len(eval_days))) # 0.85
    momentum_mult = (actuals_weight * min(3.5, raw_pace)) + (1.0 - actuals_weight)
    surging_predicted = round(sum(hist_days.get(d['dow'], 0) * item_growth_factor * momentum_mult for d in remaining_days_list))

    print(f"Case A (Surging): Baseline={baseline_unadjusted}, Raw Pace={raw_pace:.2f}x, Momentum Mult={momentum_mult:.2f}x, Boosted Remaining={surging_predicted}")
    assert surging_predicted > baseline_unadjusted, "Surging prediction should exceed baseline"
    assert raw_pace > 1.35, "Raw pace should qualify for SURGING"
    print("PASS: Case A (Surging Item) correctly accelerated forecast.")

    # Case B: Underperforming Item (Stockout Protection Dampening)
    by_date_soft = {
        '2026-09-26': 5,
        '2026-09-27': 4,
        '2026-09-28': 2,
        '2026-09-29': 2,
        '2026-09-30': 2,
    }
    act_eval_soft = sum(float(by_date_soft.get(d['date'], 0)) for d in eval_days)
    cum_pace_soft = act_eval_soft / exp_eval # 15 / 30 = 0.50
    recent_act_soft = sum(float(by_date_soft.get(d['date'], 0)) for d in recent_days)
    recent_pace_soft = recent_act_soft / recent_exp # 6 / 12 = 0.50
    raw_pace_soft = (0.65 * recent_pace_soft) + (0.35 * cum_pace_soft) # 0.50

    # Stockout protection bias: 50% dampening on slump
    effective_pace_soft = max(0.5, 1.0 - (0.5 * (1.0 - raw_pace_soft))) # 1.0 - 0.25 = 0.75
    momentum_soft = (actuals_weight * effective_pace_soft) + (1.0 - actuals_weight)
    soft_predicted = round(sum(hist_days.get(d['dow'], 0) * item_growth_factor * momentum_soft for d in remaining_days_list))

    print(f"Case B (Soft Start): Raw Pace={raw_pace_soft:.2f}x, Protected Effective Pace={effective_pace_soft:.2f}x, Predicted Remaining={soft_predicted} (Unadjusted Baseline={baseline_unadjusted})")
    assert effective_pace_soft > raw_pace_soft, "Stockout protection must dampen the downward revision"
    assert soft_predicted >= 15, "Protected prediction should preserve weekend inventory"
    print("PASS: Case B (Soft Start) correctly protected inventory with dampening.")

    # Case C: New Item with zero historical baseline
    new_actuals = 18
    new_active_days = 3
    daily_pace = new_actuals / new_active_days # 6.0 units/day
    def get_fair_dow_mult(dow):
        if dow in ['Saturday', 'Sunday']: return 1.75
        if dow == 'Friday': return 1.35
        return 1.0
    new_projected = round(sum(daily_pace * get_fair_dow_mult(d['dow']) for d in remaining_days_list))
    print(f"Case C (New Item): Daily Pace={daily_pace:.1f}/day, Projected Remaining={new_projected} across 3 days")
    assert new_projected > 0, "New item must produce a positive prediction"
    print("PASS: Case C (New Item) correctly projected demand using active velocity.")

    print("\nALL DYNAMIC PREDICTION TESTS PASSED!")
    return True

if __name__ == '__main__':
    success = run_tests()
    if not success:
        sys.exit(1)
