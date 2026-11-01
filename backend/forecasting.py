from datetime import datetime, timedelta

def calculate_statistical_demand_forecast(history_records: list, expected_override: float = None) -> dict:
    """
    Computes baseline statistical demand forecast using weighted moving averages:
    Prediction = (0.5 * historical_avg) + (0.3 * recent_avg) + (0.2 * expected_avg)
    
    Identified strictly as a baseline statistical method, not a trained ML model.
    """
    if not history_records:
        # Default fallback values for demonstration if NGO has no records
        return {
            "predicted_meals": 100,
            "historical_avg": 100.0,
            "recent_avg": 100.0,
            "expected_avg": 100.0,
            "methodology": "Baseline Statistical Weighted Moving Average (0.5 Historical + 0.3 Recent + 0.2 Expected)",
            "trend": "Stable",
            "trend_percentage": 0.0,
            "disclaimer": "Baseline statistical estimate based on sample historical records. Not a trained machine learning model.",
            "forecast_series": [],
            "history_series": []
        }

    # Sort history chronologically
    sorted_history = sorted(history_records, key=lambda x: str(x.get("date", "")))
    demand_values = [float(r.get("meals_demanded", 0)) for r in sorted_history]

    # Historical average (all days)
    historical_avg = sum(demand_values) / len(demand_values)

    # Recent average (last 7 days or last 25% of records)
    recent_slice = demand_values[-7:] if len(demand_values) >= 7 else demand_values
    recent_avg = sum(recent_slice) / len(recent_slice)

    # Expected average: day-of-week contextual estimate or manual override
    if expected_override is not None:
        expected_avg = float(expected_override)
    else:
        # Check day-of-week weighting (e.g. weekend boost of +10% if tomorrow is weekend)
        tomorrow = datetime.now() + timedelta(days=1)
        is_weekend = tomorrow.weekday() in (5, 6) # Saturday or Sunday
        expected_avg = recent_avg * 1.10 if is_weekend else recent_avg * 0.98

    # Apply required formula:
    # Prediction = (0.5 * historical) + (0.3 * recent) + (0.2 * expected)
    predicted_val = (0.5 * historical_avg) + (0.3 * recent_avg) + (0.2 * expected_avg)
    predicted_meals = int(round(predicted_val))

    # Trend detection
    if historical_avg > 0:
        trend_pct = round(((recent_avg - historical_avg) / historical_avg) * 100.0, 1)
    else:
        trend_pct = 0.0

    if trend_pct > 5.0:
        trend_label = "Increasing Demand"
    elif trend_pct < -5.0:
        trend_label = "Decreasing Demand"
    else:
        trend_label = "Stable Demand"

    # Generate 7-day forward projection for visualization
    forecast_series = []
    base_date = datetime.now().date()
    for day_offset in range(1, 8):
        future_date = base_date + timedelta(days=day_offset)
        # Factor minor weekday variation (weekend surge +8%)
        day_mult = 1.08 if future_date.weekday() in (5, 6) else 0.98
        day_pred = int(round(predicted_val * day_mult))
        forecast_series.append({
            "date": future_date.strftime("%Y-%m-%d"),
            "day": future_date.strftime("%a"),
            "predicted_meals": day_pred
        })

    explanation = (
        f"Statistical Baseline Forecast predicts {predicted_meals} meals required tomorrow. "
        f"Computed via (0.5 × {round(historical_avg, 1)} [Historical Avg]) + "
        f"(0.3 × {round(recent_avg, 1)} [Recent 7-Day Avg]) + "
        f"(0.2 × {round(expected_avg, 1)} [Expected Baseline]). "
        f"Trend indicates {trend_label} ({'+' if trend_pct > 0 else ''}{trend_pct}% vs historical average)."
    )

    return {
        "predicted_meals": predicted_meals,
        "historical_avg": round(historical_avg, 1),
        "recent_avg": round(recent_avg, 1),
        "expected_avg": round(expected_avg, 1),
        "trend": trend_label,
        "trend_percentage": trend_pct,
        "methodology": "Baseline Statistical Weighted Moving Average (0.5*Hist + 0.3*Recent + 0.2*Exp)",
        "explanation": explanation,
        "disclaimer": "This prediction is generated using a baseline weighted statistical moving-average formula. It is strictly a baseline statistical method and not a trained machine learning model.",
        "forecast_series": forecast_series,
        "history_series": sorted_history[-14:] # Return last 14 days for chart comparison
    }
