# debug_cookie.py  ──────────────
import os, json, base64, hashlib
from itsdangerous import URLSafeSerializer
from dotenv import load_dotenv

# Carica .env
load_dotenv()
SECRET = os.getenv("SESSION_SECRET")

print("\n=== ENVIRONMENT DEBUG ===")
print(f"SESSION_SECRET from env: {SECRET}")
print(f"SESSION_SECRET length: {len(SECRET) if SECRET else 'N/A'}")

# Implementazione locale di JSONSerializer
class JSONSerializer:
    def dumps(self, obj):
        return json.dumps(obj, separators=(",", ":"))
    def loads(self, data):
        return json.loads(data)

RAW = "eyJ1c2VyX2lkIjogIjY4MWEwODVhYmNlOWUzYmZhN2Q3NDViOSJ9.aFuqpw.tl0xz6tR4AHkdFP6Y8IChGmzliA"
SALT = "starlette.sessions"

print("\n=== COOKIE DEBUG ===")
print(f"Cookie: {RAW}")
parts = RAW.split('.')
print(f"Parts ({len(parts)}):")
for i, part in enumerate(parts):
    print(f"  {i+1}. {part}")

if len(parts) >= 1:
    try:
        payload = base64.urlsafe_b64decode(parts[0] + "=" * (-len(parts[0]) % 4))
        print(f"\nDecoded payload: {payload.decode('utf-8')}")
    except Exception as e:
        print(f"Error decoding payload: {e}")

print("\n=== SERIALIZER TEST ===")
s = URLSafeSerializer(
    SECRET,
    salt=SALT,
    serializer=JSONSerializer(),
    signer_kwargs={
        "key_derivation": "hmac",
        "digest_method": hashlib.sha1,
    }
)

print(f"Signer class: {s.signer.__name__}")
print("Trying loads()...")
try:
    data = s.loads(RAW)
    print(f"Success! Data: {data}")
except Exception as e:
    print(f"Error: {str(e)}")
    print(f"Cookie: {RAW}") 