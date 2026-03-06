# Input: Django user object
# Output: {
#   "metrics": {...},
#   "representative_transactions": [ {date, amount, merchant, category, raw_desc}, ... ],
#   "sanitization_log": {...},
#   "meta": {"start_date": "...", "end_date": "..."}
# }