IMP: reminder interval is now tracked by each forward port

Previously it was tracked on the source, which made sense when the notification
was on the source, but not since the reminder is per-forward-port. However this
also means brand new forward ports start at 0 instead of wherever the reminder
source PR last got from their predecessors.
