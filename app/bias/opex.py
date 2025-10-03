from datetime import date, timedelta


def third_friday(year, month):
d = date(year, month, 15)
while d.weekday() != 4: # 0=Mon
d += timedelta(days=1)
return d


def is_opex_week(d: date) -> bool:
tf = third_friday(d.year, d.month)
# if Friday holiday (rare), exchanges shift to Thu; simple rule keeps Fri
start = tf - timedelta(days=tf.weekday()) # Monday of that week
end = start + timedelta(days=4)
return start <= d <= end
