# app/bias/opex.py
from datetime import date, timedelta

def third_friday(year: int, month: int) -> date:
    """
    Return the 3rd Friday of a given month.
    """
    d = date(year, month, 15)
    while d.weekday() != 4:  # 0=Mon, 4=Fri
        d += timedelta(days=1)
    return d

def is_opex_week(d: date) -> bool:
    """
    True if the given date is in options expiration week (Mon–Fri with 3rd Friday).
    """
    tf = third_friday(d.year, d.month)
    # Monday of that week:
    start = tf - timedelta(days=tf.weekday())
    end = start + timedelta(days=4)
    return start <= d <= end
