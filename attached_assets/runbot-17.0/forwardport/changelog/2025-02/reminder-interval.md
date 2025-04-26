IMP: the reminder interval has been capped at ~1 month, but increased in the initial phase

Previously the reminder interval would start at 1 day for about a week, then
double every time, quickly increasing to less than yearly.

The reminder interval is now weekly for the first month, then monthly.
