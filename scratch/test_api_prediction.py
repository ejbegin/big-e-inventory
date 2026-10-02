import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))

from app import app, get_allowed_users

def test_api():
    client = app.test_client()
    allowed = get_allowed_users()
    test_email = list(allowed)[0] if allowed else 'ejbegin@gmail.com'
    
    with client.session_transaction() as sess:
        sess['user'] = {'email': test_email}

    payload = {
        'start_date': '2026-09-12',
        'end_date': '2026-10-04',
        'location': 'West Springfield, MA',
        'awareness_growth': 1.15,
        'price_sensitivity': -0.5
    }
    
    print(f"Calling /api/prediction_data with logged in user ({test_email})...")
    response = client.post('/api/prediction_data', json=payload)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code != 200:
        print(f"Response Error: {response.data.decode()[:500]}")
        return False
        
    data = response.get_json()
    predictions = data.get('predictions', [])
    print(f"Total Predictions Returned: {len(predictions)}")
    
    if predictions:
        sample = predictions[0]
        print("\nSample Item Prediction:")
        print(f"  Name: {sample.get('name')}")
        print(f"  Baseline Multi-Year: {sample.get('baseline_multi_year')}")
        print(f"  2026 Actuals: {sample.get('actuals')}")
        print(f"  Predicted Remainder: {sample.get('predicted_remainder')}")
        print(f"  Baseline Remainder (Unadjusted): {sample.get('baseline_remainder_unadjusted')}")
        print(f"  Momentum Multiplier: {sample.get('momentum_multiplier')}")
        print(f"  Pace Pct: {sample.get('pace_pct')}")
        print(f"  Trend Status: {sample.get('trend_status')}")
        print(f"  Status: {sample.get('status')}")
        
        # Verify required keys exist
        for key in ['momentum_multiplier', 'trend_status', 'pace_pct', 'baseline_remainder_unadjusted']:
            assert key in sample, f"Missing key '{key}' in sample item!"
            
    factors = data.get('factors', {})
    print(f"\nFactors: {factors}")
    assert 'surging_count' in factors, "Missing 'surging_count' in factors"
    assert 'trending_up_count' in factors, "Missing 'trending_up_count' in factors"
    
    # Check if any surging / trending / new items exist in dataset
    surging_items = [p for p in predictions if p.get('trend_status') in ['SURGING', 'NEW_HOT']]
    trending_items = [p for p in predictions if p.get('trend_status') == 'TRENDING_UP']
    print(f"\nIdentified Surging Items ({len(surging_items)}):")
    for s in surging_items[:5]:
        print(f"  • {s['name']}: {s['pace_pct']} (Momentum: {s['momentum_multiplier']}x, Remainder: {s['predicted_remainder']})")
    
    print("\nAPI TEST PASSED!")
    return True

if __name__ == '__main__':
    success = test_api()
    if not success:
        sys.exit(1)
