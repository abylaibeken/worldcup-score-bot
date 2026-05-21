def calculate_points(pred_home, pred_away, real_home, real_away):

    if pred_home == real_home and pred_away == real_away:
        return 5

    pred_diff = pred_home - pred_away
    real_diff = real_home - real_away

    if pred_diff == real_diff:
        return 3

    pred_outcome = (pred_diff > 0) - (pred_diff < 0)
    real_outcome = (real_diff > 0) - (real_diff < 0)

    if pred_outcome == real_outcome:
        return 2

    return 0