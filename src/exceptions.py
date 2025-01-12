from db import models


class RolesAreRequired(Exception):
    def __init__(self, roles: list[models.Role]):
        super().__init__(self, f"Roles {roles} are required for this action")
