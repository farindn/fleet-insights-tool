from pydantic import BaseModel


class AuthRequest(BaseModel):
    username: str
    password: str
    database: str
    server: str = "my.geotab.com"


class AuthResponse(BaseModel):
    token: str
    username: str
    database: str
    currency: str = "USD"
