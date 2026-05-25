from enum import Enum


class ChallengeResult(str, Enum):

    # -----------------------------
    # WIN CONDITIONS
    # -----------------------------
    WON = "won"

    # Persona agreed to challenge objective
    WON_OBJECTIVE_COMPLETED = "won_objective_completed"

    # -----------------------------
    # LOSE CONDITIONS
    # -----------------------------
    LOST_TIMEOUT = "lost_timeout"

    # Persona explicitly rejected objective
    LOST_REJECTED = "lost_rejected"

    # Persona got angry / blocked user
    LOST_BLOCKED = "lost_blocked"

    # User violated challenge rules
    LOST_RULE_VIOLATION = "lost_rule_violation"

    # -----------------------------
    # OTHER STATES
    # -----------------------------
    ABANDONED = "abandoned"

    ACTIVE = "active"