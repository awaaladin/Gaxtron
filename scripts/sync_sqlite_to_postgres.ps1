# Copy merchants from SQLite (gaxtron_dev.db) into Postgres when switching databases
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot | Split-Path -Parent
$GaX = Join-Path $Root "GaX"
$sqlite = "sqlite:///$((Join-Path $GaX 'gaxtron_dev.db').Replace('\','/'))"
$pg = "postgresql://gaxtron:gaxtron_secret@127.0.0.1:5433/gaxtron_db"

Push-Location $GaX
python -c @"
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models.user import User
import app.db.models  # noqa

Se = create_engine('$sqlite')
Pe = create_engine('$pg')
src = sessionmaker(bind=Se)()
dst = sessionmaker(bind=Pe)()
n = 0
for u in src.query(User).all():
    if dst.query(User).filter(User.email == u.email).first():
        continue
    dst.add(User(
        email=u.email, username=u.username, hashed_password=u.hashed_password,
        is_active=u.is_active, is_superadmin=u.is_superadmin, created_at=u.created_at,
    ))
    n += 1
dst.commit()
print(f'Synced {n} user(s) to Postgres')
"@
Pop-Location
