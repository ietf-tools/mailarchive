# Timezones

## Summary
In July 2023, in preparation for migration to Postgres, enabled support for time zones (USE_TZ = True). When importing a message several different headers are checked to determine the datetime of the message. In nearly all cases a time zone aware datetime is returned. The datetime is converted to UTC and saved in the database using UTC time zone. In rare cases a naive date time is returned it is saved in the database as is, with UTC time zone assigned. In various cases where dates / datetimes are input, in search forms, reports, management commands, etc, the value is interpreted as UTC time zone. Message times are always displayed as UTC times.

From https://docs.djangoproject.com/en/4.2/topics/i18n/timezones/:
"The PostgreSQL backend stores datetimes as timestamp with time zone. In practice, this means it converts datetimes from the connection’s time zone to UTC on storage, and from UTC to the connection’s time zone on retrieval."
