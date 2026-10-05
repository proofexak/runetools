"""
Encrypted login store: data/vault.json (gitignored), one entry per account
display name — {"email", "password", "notes"}.

The key comes from a master password via scrypt and is never written anywhere;
the entries are one Fernet token (AES-128-CBC + HMAC-SHA256). A wrong master
password fails the HMAC — there is no separate password hash to attack.
Losing the master password loses the logins: there is no recovery.

Nothing in the suite reads this; logging in uses RuneLite's saved Jagex session.
"""
import base64, hashlib, json, os

from cryptography.fernet import Fernet, InvalidToken

SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1}   # ~0.1 s, 32 MiB per unlock
MIN_MASTER = 8


class WrongPassword(Exception):
    pass


def default_path():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "data", "vault.json")


def derive_key(master, salt, n, r, p):
    raw = hashlib.scrypt(master.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                         maxmem=128 * 1024 * 1024, dklen=32)
    return base64.urlsafe_b64encode(raw)


class Vault:
    def __init__(self, path=None):
        self.path = path or default_path()
        self._fernet = None      # set while unlocked
        self._params = None      # salt + scrypt params of the file in use

    def exists(self):
        return os.path.exists(self.path)

    @property
    def unlocked(self):
        return self._fernet is not None

    def unlock(self, master):
        """Open the vault, or create an empty one if none exists yet."""
        if not self.exists():
            if len(master) < MIN_MASTER:
                raise WrongPassword(f"master password must be at least {MIN_MASTER} characters")
            self._new_key(master)
            self._write({})
            return
        with open(self.path, encoding="utf-8") as f:
            doc = json.load(f)
        params = {"salt": base64.b64decode(doc["salt"]), **{k: doc[k] for k in ("n", "r", "p")}}
        fernet = Fernet(derive_key(master, params["salt"], params["n"], params["r"], params["p"]))
        try:
            fernet.decrypt(doc["token"].encode())
        except InvalidToken:
            raise WrongPassword("wrong master password") from None
        self._fernet, self._params = fernet, params

    def lock(self):
        self._fernet = self._params = None

    def entries(self):
        if not self.unlocked:
            raise WrongPassword("vault is locked")
        with open(self.path, encoding="utf-8") as f:
            doc = json.load(f)
        return json.loads(self._fernet.decrypt(doc["token"].encode()))

    def set(self, account, email, password=None, notes=""):
        """password=None keeps the stored one."""
        data = self.entries()
        if password is None:
            password = data.get(account, {}).get("password", "")
        data[account] = {"email": email, "password": password, "notes": notes}
        self._write(data)

    def delete(self, account):
        data = self.entries()
        if data.pop(account, None) is not None:
            self._write(data)

    def rename(self, old, new):
        data = self.entries()
        if old in data:
            data[new] = data.pop(old)
            self._write(data)

    def change_master(self, new_master):
        if len(new_master) < MIN_MASTER:
            raise WrongPassword(f"master password must be at least {MIN_MASTER} characters")
        data = self.entries()
        self._new_key(new_master)   # fresh salt too
        self._write(data)

    def _new_key(self, master):
        salt = os.urandom(16)
        self._params = {"salt": salt, **SCRYPT}
        self._fernet = Fernet(derive_key(master, salt, **SCRYPT))

    def _write(self, data):
        doc = {"v": 1, "salt": base64.b64encode(self._params["salt"]).decode(),
               **{k: self._params[k] for k in ("n", "r", "p")},
               "token": self._fernet.encrypt(json.dumps(data).encode()).decode()}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        os.replace(tmp, self.path)
