# certificate_manager.py
import ssl
import logging
from pathlib import Path
from datetime import datetime, timedelta
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import ipaddress

logger = logging.getLogger(__name__)


class CertificateManager:
    def __init__(self):
        # Сертификаты храним в подпапке certificates
        from core.config_manager import get_app_data_dir
        app_data_dir = get_app_data_dir()
        certs_dir = app_data_dir / "certificates"
        certs_dir.mkdir(exist_ok=True)

        self.cert_path = certs_dir / "fake.crt"
        self.key_path = certs_dir / "fake.key"

    def generate_self_signed_certificate(self) -> bool:
        """Генерирует самоподписанный сертификат для localhost"""
        try:
            # Генерируем приватный ключ
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
            )

            # Создаем информацию о субъекте (владельце сертификата)
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Moscow"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Moscow"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Zenzefi"),
                x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
            ])

            # Создаем сертификат
            cert_builder = x509.CertificateBuilder().subject_name(
                subject
            ).issuer_name(
                issuer
            ).public_key(
                private_key.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.utcnow()
            ).not_valid_after(
                datetime.utcnow() + timedelta(days=365)
            )

            # Добавляем альтернативные имена
            san = x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.DNSName("127.0.0.1"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ])

            cert_builder = cert_builder.add_extension(san, critical=False)

            # Подписываем сертификат
            cert = cert_builder.sign(private_key, hashes.SHA256())

            # Сохраняем приватный ключ
            with open(self.key_path, "wb") as key_file:
                key_file.write(private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                ))

            # Сохраняем сертификат
            with open(self.cert_path, "wb") as cert_file:
                cert_file.write(cert.public_bytes(
                    encoding=serialization.Encoding.PEM
                ))

            logger.info(f"✅ Самоподписанный сертификат создан: {self.cert_path}")
            logger.info(f"✅ Приватный ключ создан: {self.key_path}")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка генерации сертификата: {e}")
            return False

    def check_certificates_exist(self) -> bool:
        """Проверяет существование сертификатов"""
        return self.cert_path.exists() and self.key_path.exists()

    def ensure_certificates_exist(self) -> bool:
        """Убеждается, что сертификаты существуют, и создает их при необходимости"""
        if not self.check_certificates_exist():
            logger.warning("Сертификаты не найдены, генерируем новые...")
            return self.generate_self_signed_certificate()
        return True

    def get_certificate_info(self) -> dict:
        """Возвращает информацию о сертификате"""
        if not self.cert_path.exists():
            return {"error": "Сертификат не найден"}

        try:
            with open(self.cert_path, "rb") as cert_file:
                cert_data = cert_file.read()
                cert = x509.load_pem_x509_certificate(cert_data)

                # Преобразуем subject и issuer в читаемый формат
                subject_dict = {}
                for attr in cert.subject:
                    subject_dict[attr.oid._name] = attr.value

                issuer_dict = {}
                for attr in cert.issuer:
                    issuer_dict[attr.oid._name] = attr.value

                # Используем новые свойства с UTC временем вместо устаревших
                return {
                    "subject": subject_dict,
                    "issuer": issuer_dict,
                    "not_valid_before_utc": cert.not_valid_before_utc.isoformat(),
                    "not_valid_after_utc": cert.not_valid_after_utc.isoformat(),
                    "serial_number": str(cert.serial_number),
                    "version": f"v{cert.version.value}",
                }
        except Exception as e:
            return {"error": f"Ошибка чтения сертификата: {e}"}

    def get_certificate_days_remaining(self) -> int:
        """Возвращает количество дней до истечения срока действия сертификата"""
        if not self.cert_path.exists():
            return -1

        try:
            with open(self.cert_path, "rb") as cert_file:
                cert_data = cert_file.read()
                cert = x509.load_pem_x509_certificate(cert_data)

                # Используем UTC время для обоих значений
                now = datetime.utcnow().replace(tzinfo=None)
                expiration = cert.not_valid_after_utc.replace(tzinfo=None)

                days_remaining = (expiration - now).days
                return max(0, days_remaining)

        except Exception as e:
            logger.error(f"Ошибка проверки срока действия сертификата: {e}")
            return -1