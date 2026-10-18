import pandas as pd
from pulse.clean import clean_reviews, mask_pii

def test_masks():
    t = mask_pii("call 9876543210 or mail a.b@x.com, PAN ABCDE1234F, client id AB12345, ticket no 98765432")
    for leak in ["9876543210", "a.b@x.com", "ABCDE1234F", "AB12345", "98765432"]:
        assert leak not in t, t

def test_keeps_money_and_percent():
    t = mask_pii("charged Rs 20 brokerage and 0.1% exit load on 5000")
    assert t == "charged Rs 20 brokerage and 0.1% exit load on 5000"

def test_clean_filters():
    df = pd.DataFrame([
        {"date": "2026-10-01", "source": "google_play", "rating": 1, "review_text": "Why did they deduct DP charges when I sold?"},
        {"date": "2026-10-01", "source": "google_play", "rating": 5, "review_text": "good"},            # too short
        {"date": "2026-10-02", "source": "google_play", "rating": 2, "review_text": "बहुत खराब ऐप है पैसे कट गए"},  # non-Latin
        {"date": "2026-10-03", "source": "app_store", "rating": 1, "review_text": "Why did they deduct DP charges when I sold?"},  # duplicate
    ])
    out = clean_reviews(df)
    assert len(out) == 1
