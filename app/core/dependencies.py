"""
Shared FastAPI Depends() functions go here. Empty for now — routes don't
need auth, a DB session, or a Firestore client yet because every service
below them returns fake in-memory data.
"""

# STUB: once M7/M9 persist real data, add something like
# `def get_firestore_client(): ...` here and Depends() it into the
# outcome-log and retailer routes instead of hitting in-memory fixtures.
