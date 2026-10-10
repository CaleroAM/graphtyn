# RF07 mixed profile — 1,000 records (2026-10-09)

The mixed profile ran one normal and one degraded-without-embeddings pass over
283 queries: 90 exact controls, 90 Spanish questions, 90 identifier-free
paraphrases, 10 identifier negatives and 3 natural negatives. Both modes
reported Recall@5, MRR, nDCG@10, attribution and negative accuracy of `1.0`,
with zero query errors.

The identifier-free positives do not contain `scaleanchor`; they use the
decision vocabulary stored in the corresponding records. The natural negatives
contain no fixture vocabulary and must return no memory. Per-kind metrics and
raw samples are in [`mixed_1000.json`](mixed_1000.json).

This is a 1,000-record quality probe. RF07 capacity evidence remains the
separate five-repetition runs at 1,000, 10,000 and 50,000 records in
[`REPORT.md`](REPORT.md).
