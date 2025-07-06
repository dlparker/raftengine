

I want the server method "advance_time" to check to see if the
requested time update will cross the boundary between midnight on the
last day of a month and the first day of the next month. Naive datetimes
are fine for this.

If it crosses the boundary I want it to prepare a new Statement dataclass for each
account and persist it in the DB. This will contain the starting and ending balances for the month, and
the total credits and total debits for the period, and a field that is "statement_date"
which is the date of the end of the month.

Then I want the server's "list_statements" method to return a list of statement
dates for that account.
