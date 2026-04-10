class EvalGateError(Exception):
    """Base error for expected evaluation failures."""


class UnsupportedPolicyError(EvalGateError):
    def __init__(self, policy_name: str) -> None:
        super().__init__(f"Unsupported policy: {policy_name}")
        self.policy_name = policy_name


class UnknownReleaseError(EvalGateError):
    def __init__(self, release_id: str) -> None:
        super().__init__(f"Unknown release_id: {release_id}")
        self.release_id = release_id
