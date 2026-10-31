"""Layer 2: Triage and tiering.

Classifies a change as green, amber or red. Paths and keywords from the project
profile can only raise the tier, never lower it. On failure: default to the higher tier.
"""

LAYER = 2
AI_INVOLVED = True
