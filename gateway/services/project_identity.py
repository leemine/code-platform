"""Private adapter for the existing account authority; never a wire identity."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ProjectIdentity:
    authority: str
    actor_id: str

    @property
    def subject_id(self):
        return self.actor_id

class ProjectPrincipal:
    def __init__(self, principal):
        self.principal = principal

    def identity(self):
        principal = self.principal
        value = principal.accounts.session(principal.token)
        if value['authority'] != principal.authority or value['user_id'] != principal.user_id:
            raise PermissionError('PROJECT_ACCOUNT_CHANGED')
        return ProjectIdentity(principal.authority, principal.user_id)
