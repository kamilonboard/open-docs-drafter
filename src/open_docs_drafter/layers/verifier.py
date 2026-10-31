"""Layer 6: Independent verifier.

A second model, ideally from another provider, checks each claim against the
evidence without seeing the drafter's reasoning. On failure: drop or escalate the claim.
"""

LAYER = 6
AI_INVOLVED = True
