import os

import bcrypt
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()
_fernet = Fernet(os.environ["DATA_KEY"].encode())


def encrypt_text(text):
    # Plain text in, scrambled text out
    return _fernet.encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_text(token):
    # Scrambled text in, plain text out (fails if the key is wrong)
    return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")


def hash_password(password):
    # One-way: the password cannot be recovered from the hash
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))