import base64,hashlib,hmac,logging
from cryptography.fernet import Fernet
from app.core.config import settings
logger=logging.getLogger(__name__)
class VinProtector:
    def __init__(self):
        key_material=settings.vin_encryption_key or f"{settings.development_secret}:vin-encryption"
        key=key_material.encode()
        try: self.fernet=Fernet(key)
        except ValueError: self.fernet=Fernet(base64.urlsafe_b64encode(hashlib.sha256(key).digest()))
        self.secret=(settings.vin_fingerprint_secret or f"{settings.development_secret}:vin-fingerprint").encode()
        self.using_development_keys=not(settings.vin_encryption_key and settings.vin_fingerprint_secret)
    def encrypt(self,vin:str)->str: return self.fernet.encrypt(vin.encode()).decode()
    def decrypt(self,value:str)->str: return self.fernet.decrypt(value.encode()).decode()
    def fingerprint(self,vin:str)->str: return hmac.new(self.secret,vin.encode(),hashlib.sha256).hexdigest()
protector=VinProtector()
