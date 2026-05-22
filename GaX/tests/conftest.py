import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-32-characters-long")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret-minimum-32-chars")
os.environ.setdefault("WALLET_ENCRYPTION_KEY", "test-wallet-encryption-key-32-chars-min")
os.environ.setdefault("ENV", "development")
