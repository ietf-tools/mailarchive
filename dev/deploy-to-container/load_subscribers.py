import os
import sys
import django

sys.path.insert(0, '/workspace/backend')
django_settings = 'mlarchive.settings.settings_sandbox'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', django_settings)
django.setup()

# ==================================

from datetime import date, timedelta

from mlarchive.archive.models import EmailList, Subscriber

# Start and end dates for May 2024
start_date = date(2024, 5, 1)
end_date = date(2024, 5, 31)

# Generate all dates in May 2024
current_date = start_date
dates_in_may = []

while current_date <= end_date:
    dates_in_may.append(current_date)
    current_date += timedelta(days=1)


for name, count in [('curdle', 148), ('mtgvenue', 110), ('yang-doctors', 19)]:
    elist = EmailList.objects.get(name=name)
    for d in dates_in_may:
        Subscriber.objects.create(email_list=elist, date=d, count=count)
