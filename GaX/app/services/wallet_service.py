import logging

from decimal import Decimal



from sqlalchemy.orm import Session



from app.db.models.wallet import Wallet

from app.services.payment_processor import get_payment_processor



logger = logging.getLogger(__name__)





class WalletService:

    @staticmethod

    def generate_wallet(

        db: Session,

        chain: str,

        currency: str,

        user_id: int | None = None,

        payment_id: int | None = None,

    ) -> Wallet:

        processor = get_payment_processor()

        created = processor.create_payment_wallet(chain, currency)



        wallet = Wallet(

            user_id=user_id,

            payment_id=payment_id,

            address=created.address,

            encrypted_private_key=created.encrypted_private_key,

            chain=created.chain,

            currency=created.currency,

            balance=Decimal("0"),

        )

        db.add(wallet)

        db.flush()

        logger.info("Generated %s wallet %s for %s", chain, created.address, currency)

        return wallet



    @staticmethod

    def get_balance(db: Session, address: str) -> Decimal:

        wallet = db.query(Wallet).filter(Wallet.address == address).first()

        return wallet.balance if wallet else Decimal("0")


