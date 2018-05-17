from smfrcore.models.sqlmodels import User
from werkzeug.security import safe_str_cmp


def authenticate(email, password):
    user = User.query.get(email=email)
    if user and safe_str_cmp(user.password_hash.encode('utf-8'), User.hash_password(password.encode('utf-8'))):
        return user


def identity(payload):
    user_id = payload['identity']
    return User.query.get(id=user_id)
