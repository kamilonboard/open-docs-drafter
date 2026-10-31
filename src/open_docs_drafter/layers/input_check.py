"""Layer 1: Input check.

Cross-checks the pull request description against the actual diff and strips
embedded instructions. On failure: discard the description and use the diff only.
"""

LAYER = 1
AI_INVOLVED = False
